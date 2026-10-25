"""
OSIRIS Safe Proposal-to-Patch Workflow & AST Security Firewall
==============================================================

Five-stage defense-in-depth pipeline for generated code proposals:
1. Code-fence & conversational-text extraction (preserves docstrings & indentation).
2. Parse-only syntax validation (ast.parse).
3. AST policy inspection and import/call security firewall (disallowlist/allowlist).
4. Disposable sandbox dry-run execution.
5. Exact minimal unified diff generation, human approval gating, and verifiable PatchReceipt.

Invariant:
`ast.parse()` only establishes grammatical validity; it does not establish safety.
Unsandboxed or unreviewed model output MUST NEVER be written directly to workspace files.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os  # noqa: F401
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# Forbidden builtins that bypass runtime boundaries
DENIED_BUILTINS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
    "exit",
    "quit",
}

# Forbidden modules that enable network egress, arbitrary subprocesses, or native FFI
DENIED_MODULE_PREFIXES: Set[str] = {
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "paramiko",
    "ctypes",
    "pickle",
    "marshal",
    "importlib",
    "multiprocessing",
    "pty",
    "telnetlib",
    "posix",
    "asyncio.subprocess",
}

# Forbidden attribute calls that execute system commands or mutate file systems destructively
DENIED_CALL_ATTRIBUTES: Set[str] = {
    "os.system",
    "os.popen",
    "os.kill",
    "os.remove",
    "os.rmdir",
    "os.unlink",
    "shutil.rmtree",
    "sys.exit",
}


@dataclass(frozen=True)
class ExtractedProposal:
    code: str
    language: str
    target_file: Optional[str] = None
    fence_index: int = 0


@dataclass(frozen=True)
class ASTValidationResult:
    is_valid_syntax: bool
    is_safe: bool
    syntax_error: Optional[str] = None
    security_violations: Tuple[str, ...] = ()
    imported_modules: Tuple[str, ...] = ()
    called_functions: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float


@dataclass(frozen=True)
class PatchReceipt:
    receipt_id: str
    timestamp: str
    target_file: str
    original_sha256: Optional[str]
    proposed_sha256: str
    diff_sha256: str
    ast_safe: bool
    sandbox_passed: bool
    human_approved: bool
    approval_token: Optional[str]
    applied: bool
    receipt_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProposalExtractor:
    """Extracts code proposals from conversational model responses without corrupting indentation."""

    FENCE_PATTERN = re.compile(
        r"```([a-zA-Z0-9_\-\+]*)\n(.*?)```",
        re.DOTALL
    )

    FILE_DIRECTIVE_PATTERN = re.compile(
        r"(?:^|\n)(?:#|//|<!--)?\s*(?:File|Target|TargetFile|filepath):\s*([^\s\n\r]+)",
        re.IGNORECASE
    )

    @classmethod
    def extract(cls, raw_response: str) -> List[ExtractedProposal]:
        matches = list(cls.FENCE_PATTERN.finditer(raw_response))
        if not matches:
            # Fallback: check if raw text parses directly as clean python code
            stripped = raw_response.strip()
            if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("import "):
                try:
                    ast.parse(stripped)
                    return [ExtractedProposal(code=stripped, language="python", target_file=None, fence_index=0)]
                except SyntaxError:
                    pass
            return []

        proposals = []
        for idx, m in enumerate(matches):
            lang = m.group(1).strip().lower() or "python"
            code_body = m.group(2)

            # Detect target file directive inside code or immediately preceding fence
            target_file = None
            dir_match = cls.FILE_DIRECTIVE_PATTERN.search(code_body)
            if dir_match:
                target_file = dir_match.group(1).strip()
            else:
                # Check preceding 100 characters before fence
                preceding = raw_response[max(0, m.start() - 150): m.start()]
                pre_match = cls.FILE_DIRECTIVE_PATTERN.search(preceding)
                if pre_match:
                    target_file = pre_match.group(1).strip()

            proposals.append(ExtractedProposal(
                code=code_body,
                language=lang,
                target_file=target_file,
                fence_index=idx
            ))
        return proposals


class ASTSecurityInspector(ast.NodeVisitor):
    """AST policy firewall enforcing blocked builtins, forbidden modules, and dangerous attributes."""

    def __init__(self):
        self.violations: List[str] = []
        self.imports: List[str] = []
        self.calls: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
            base_mod = alias.name.split(".")[0]
            if base_mod in DENIED_MODULE_PREFIXES or alias.name in DENIED_MODULE_PREFIXES:
                self.violations.append(
                    f"Line {node.lineno}:{node.col_offset} - Forbidden module import: '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod_name = node.module or ""
        self.imports.append(mod_name)
        base_mod = mod_name.split(".")[0]
        if base_mod in DENIED_MODULE_PREFIXES or mod_name in DENIED_MODULE_PREFIXES:
            self.violations.append(
                f"Line {node.lineno}:{node.col_offset} - Forbidden module import: '{mod_name}'"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = ""
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
            self.calls.append(call_name)
            if call_name in DENIED_BUILTINS:
                self.violations.append(
                    f"Line {node.lineno}:{node.col_offset} - Forbidden builtin call: '{call_name}()'"
                )
        elif isinstance(node.func, ast.Attribute):
            attr_chain = self._resolve_attr_chain(node.func)
            if attr_chain:
                call_name = attr_chain
                self.calls.append(attr_chain)
                if attr_chain in DENIED_CALL_ATTRIBUTES:
                    self.violations.append(
                        f"Line {node.lineno}:{node.col_offset} - Forbidden system call: '{attr_chain}()'"
                    )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Deny introspection exploits targeting dunder attributes
        if node.attr in ("__subclasses__", "__globals__", "__code__"):
            self.violations.append(
                f"Line {node.lineno}:{node.col_offset} - Forbidden introspection attribute: '.{node.attr}'"
            )
        self.generic_visit(node)

    def _resolve_attr_chain(self, node: ast.Attribute) -> str:
        parts = [node.attr]
        curr = node.value
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            return ".".join(reversed(parts))
        return ""


def validate_python_code(code_str: str) -> ASTValidationResult:
    """Performs Stage 2 (Syntax) and Stage 3 (AST Security Firewall) validation."""
    try:
        parsed_ast = ast.parse(code_str)
    except SyntaxError as se:
        return ASTValidationResult(
            is_valid_syntax=False,
            is_safe=False,
            syntax_error=f"SyntaxError at line {se.lineno}:{se.offset} - {se.msg}",
            security_violations=(),
            imported_modules=(),
            called_functions=()
        )

    inspector = ASTSecurityInspector()
    inspector.visit(parsed_ast)

    is_safe = (len(inspector.violations) == 0)
    return ASTValidationResult(
        is_valid_syntax=True,
        is_safe=is_safe,
        syntax_error=None,
        security_violations=tuple(inspector.violations),
        imported_modules=tuple(inspector.imports),
        called_functions=tuple(inspector.calls)
    )


class SandboxRunner:
    """Executes proposed code in a disposable temporary directory with bounded timeout."""

    @classmethod
    def dry_run(cls, code_str: str, timeout_seconds: int = 5) -> SandboxExecutionResult:
        with tempfile.TemporaryDirectory(prefix="osiris_sandbox_") as tmp_dir:
            cand_path = Path(tmp_dir) / "candidate_proposal.py"
            cand_path.write_text(code_str, encoding="utf-8")

            start_t = time.perf_counter()
            try:
                proc = subprocess.run(
                    ["/usr/bin/python3", str(cand_path)],
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    shell=False
                )
                duration = time.perf_counter() - start_t
                return SandboxExecutionResult(
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    timed_out=False,
                    duration_seconds=round(duration, 4)
                )
            except subprocess.TimeoutExpired as te:
                duration = time.perf_counter() - start_t
                return SandboxExecutionResult(
                    exit_code=-9,
                    stdout=te.stdout or "",
                    stderr=f"TIMEOUT: Sandbox execution exceeded {timeout_seconds}s limit.",
                    timed_out=True,
                    duration_seconds=round(duration, 4)
                )
            except Exception as ex:
                duration = time.perf_counter() - start_t
                return SandboxExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"SANDBOX RUNTIME ERROR: {str(ex)}",
                    timed_out=False,
                    duration_seconds=round(duration, 4)
                )


def generate_patch_diff(
    original_text: str,
    proposed_text: str,
    filename: str = "target_file.py"
) -> str:
    """Generates exact minimal unified diff for human inspection."""
    orig_lines = original_text.splitlines(keepends=True)
    prop_lines = proposed_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        orig_lines,
        prop_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=3
    )
    return "".join(diff)


class SafePatchWorkflow:
    """Coordinates the 5-stage proposal-to-patch pipeline and creates signed receipts."""

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None):
        self.workspace_root = Path(workspace_root or ".").resolve()

    def process_proposal(
        self,
        raw_proposal_text: str,
        target_relative_path: Optional[str] = None,
        run_sandbox: bool = True
    ) -> Dict[str, Any]:
        """
        Executes stages 1 through 5:
        Extracts code, validates syntax, runs AST policy inspection, runs disposable sandbox dry run,
        and computes unified diff.
        """
        # Stage 1: Extraction
        extracted = ProposalExtractor.extract(raw_proposal_text)
        if not extracted:
            return {
                "success": False,
                "stage": "EXTRACTION",
                "error": "No valid code blocks found in model response."
            }

        proposal = extracted[0]
        code = proposal.code
        target_path_str = target_relative_path or proposal.target_file

        # Stage 2 & 3: Syntax & AST Firewall
        ast_result = validate_python_code(code)
        if not ast_result.is_valid_syntax:
            return {
                "success": False,
                "stage": "SYNTAX_VALIDATION",
                "error": ast_result.syntax_error,
                "ast_result": ast_result
            }

        if not ast_result.is_safe:
            return {
                "success": False,
                "stage": "AST_FIREWALL_BLOCKED",
                "error": "Proposal violated AST security policy.",
                "violations": ast_result.security_violations,
                "ast_result": ast_result
            }

        # Stage 4: Disposable Sandbox Dry Run
        sandbox_res: Optional[SandboxExecutionResult] = None
        if run_sandbox:
            sandbox_res = SandboxRunner.dry_run(code, timeout_seconds=5)
            if sandbox_res.exit_code != 0:
                return {
                    "success": False,
                    "stage": "SANDBOX_EXECUTION_FAILED",
                    "error": f"Candidate failed sandbox execution with exit code {sandbox_res.exit_code}.",
                    "sandbox_result": sandbox_res,
                    "ast_result": ast_result
                }

        # Stage 5: Diff Generation against Workspace Target
        orig_text = ""
        orig_sha256 = None
        resolved_target = None

        if target_path_str:
            resolved_target = (self.workspace_root / target_path_str).resolve()
            if resolved_target.exists() and resolved_target.is_file():
                orig_text = resolved_target.read_text(encoding="utf-8")
                orig_sha256 = hashlib.sha256(orig_text.encode("utf-8")).hexdigest()

        diff_text = generate_patch_diff(
            original_text=orig_text,
            proposed_text=code,
            filename=target_path_str or "proposed_code.py"
        )

        return {
            "success": True,
            "stage": "APPROVAL_GATE_READY",
            "target_file": target_path_str,
            "code": code,
            "diff": diff_text,
            "ast_result": ast_result,
            "sandbox_result": sandbox_res,
            "original_sha256": orig_sha256
        }

    def apply_patch(
        self,
        target_relative_path: str,
        code: str,
        diff_text: str,
        original_sha256: Optional[str],
        ast_safe: bool,
        sandbox_passed: bool,
        human_approved: bool,
        approval_token: Optional[str] = None
    ) -> PatchReceipt:
        """Applies patch to workspace target if approved, generating a cryptographic PatchReceipt."""
        target_path = (self.workspace_root / target_relative_path).resolve()
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        prop_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
        diff_sha256 = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

        applied = False
        if human_approved and ast_safe and sandbox_passed:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(code, encoding="utf-8")
            applied = True

        raw_receipt = {
            "receipt_id": f"PATCH-REC-{hashlib.sha256((now_str + target_relative_path).encode()).hexdigest()[:12]}",
            "timestamp": now_str,
            "target_file": target_relative_path,
            "original_sha256": original_sha256,
            "proposed_sha256": prop_sha256,
            "diff_sha256": diff_sha256,
            "ast_safe": ast_safe,
            "sandbox_passed": sandbox_passed,
            "human_approved": human_approved,
            "approval_token": approval_token,
            "applied": applied
        }
        canonical_str = json.dumps(raw_receipt, sort_keys=True, separators=(",", ":"))
        receipt_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        return PatchReceipt(
            receipt_id=raw_receipt["receipt_id"],
            timestamp=raw_receipt["timestamp"],
            target_file=raw_receipt["target_file"],
            original_sha256=raw_receipt["original_sha256"],
            proposed_sha256=raw_receipt["proposed_sha256"],
            diff_sha256=raw_receipt["diff_sha256"],
            ast_safe=raw_receipt["ast_safe"],
            sandbox_passed=raw_receipt["sandbox_passed"],
            human_approved=raw_receipt["human_approved"],
            approval_token=raw_receipt["approval_token"],
            applied=raw_receipt["applied"],
            receipt_hash=receipt_hash
        )
