"""
OSIRIS Process Doctor & Fork/Exec Reliability Engine
====================================================

Deterministic preflight inspection, path resolution, and error diagnosis for local process execution.
Enforces zero shell=True, strict argument arrays, and durable cryptographic diagnostics receipts.

Key Invariants:
- `argv` MUST always be processed and reported as an argument array (list[str]), never a concatenated shell string.
- Distinctly classifies POSIX errno conditions: ENOENT, EACCES, ENOTDIR, ENOEXEC.
- Validates executable existence, permissions (is_file, X_OK), and interpreter shebangs.
- Emits SHA-256 verifiable ProcessDiagnosticReceipt.
- Safe execution across non-project working directories.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform  # noqa: F401
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass(frozen=True)
class ProcessDiagnosticReceipt:
    receipt_id: str
    timestamp: str
    argv: List[str]
    cwd: str
    executable_input: str
    resolved_executable: Optional[str]
    path_lookup_success: bool
    exists: bool
    is_file: bool
    is_dir: bool
    is_executable: bool
    stat_mode_octal: Optional[str]
    executable_sha256: Optional[str]
    interpreter_shebang: Optional[str]
    errno_code: Optional[int]
    errno_name: Optional[str]
    error_message: Optional[str]
    can_execute: bool
    receipt_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        d = self.to_dict()
        # Omit receipt_hash from inner representation to guarantee deterministic hashing
        payload = {k: v for k, v in d.items() if k != "receipt_hash"}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ProcessDoctor:
    """
    Subsystem for deep preflight inspection and execution diagnostics of subprocess calls.
    Never invokes shell=True. Handles PATH lookup, directory verification, permissions,
    and interpreter shebang resolution.
    """

    ALLOWED_SAFE_BINARIES = {
        "python", "python3", "pytest", "git", "ls", "grep", "cat", "find",
        "mkdir", "cp", "echo", "pwd", "tree", "node", "which", "head", "tail"
    }

    def __init__(self, workspace_root: Optional[Union[str, Path]] = None):
        self.workspace_root = Path(workspace_root or ".").resolve()

    def inspect_command(
        self,
        argv: Union[List[str], Tuple[str, ...]],
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None
    ) -> ProcessDiagnosticReceipt:
        """
        Performs comprehensive preflight diagnostics on a proposed subprocess execution.
        Guarantees that argv is an array. Inspects cwd, executable path, permissions,
        and POSIX errno conditions.
        """
        # 1. Enforce argument array invariant
        if not isinstance(argv, (list, tuple)):
            raise TypeError(
                f"argv MUST be an argument array (list[str]), received {type(argv).__name__}. "
                "Concatenated shell strings are strictly forbidden."
            )

        argv_list = [str(arg) for arg in argv]
        if not argv_list:
            raise ValueError("argv array cannot be empty.")

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        env_map = env if env is not None else os.environ.copy()

        # 2. Inspect cwd
        target_cwd_raw = cwd if cwd is not None else self.workspace_root
        target_cwd_path = Path(target_cwd_raw)

        cwd_str = str(target_cwd_path.resolve()) if target_cwd_path.exists() else str(target_cwd_path)
        cwd_exists = target_cwd_path.exists()
        cwd_is_dir = target_cwd_path.is_dir() if cwd_exists else False

        # If cwd doesn't exist or isn't a directory, fail-closed immediately with ENOTDIR or ENOENT
        if not cwd_exists:
            receipt_payload = self._build_receipt_dict(
                timestamp=now_str,
                argv=argv_list,
                cwd=cwd_str,
                executable_input=argv_list[0],
                resolved_executable=None,
                path_lookup_success=False,
                exists=False,
                is_file=False,
                is_dir=False,
                is_executable=False,
                stat_mode_octal=None,
                executable_sha256=None,
                interpreter_shebang=None,
                errno_code=errno.ENOENT,
                errno_name="ENOENT",
                error_message=f"Working directory does not exist: {cwd_str}",
                can_execute=False
            )
            return self._finalize_receipt(receipt_payload)

        if not cwd_is_dir:
            receipt_payload = self._build_receipt_dict(
                timestamp=now_str,
                argv=argv_list,
                cwd=cwd_str,
                executable_input=argv_list[0],
                resolved_executable=None,
                path_lookup_success=False,
                exists=True,
                is_file=target_cwd_path.is_file(),
                is_dir=False,
                is_executable=False,
                stat_mode_octal=None,
                executable_sha256=None,
                interpreter_shebang=None,
                errno_code=errno.ENOTDIR,
                errno_name="ENOTDIR",
                error_message=f"Working directory path is not a directory: {cwd_str}",
                can_execute=False
            )
            return self._finalize_receipt(receipt_payload)

        # 3. Resolve executable
        exec_input = argv_list[0]
        has_path_separator = (os.sep in exec_input) or ("/" in exec_input)

        resolved_path: Optional[Path] = None
        path_lookup_success = False

        if has_path_separator:
            # Relative to cwd or absolute
            cand = Path(exec_input)
            if cand.is_absolute():
                resolved_path = cand
            else:
                resolved_path = (target_cwd_path / cand).resolve()
            path_lookup_success = resolved_path.exists()
        else:
            # Lookup in PATH
            lookup = shutil.which(exec_input, path=env_map.get("PATH"))
            if lookup:
                resolved_path = Path(lookup).resolve()
                path_lookup_success = True
            else:
                path_lookup_success = False

        if not resolved_path or not resolved_path.exists():
            receipt_payload = self._build_receipt_dict(
                timestamp=now_str,
                argv=argv_list,
                cwd=cwd_str,
                executable_input=exec_input,
                resolved_executable=str(resolved_path) if resolved_path else None,
                path_lookup_success=path_lookup_success,
                exists=False,
                is_file=False,
                is_dir=False,
                is_executable=False,
                stat_mode_octal=None,
                executable_sha256=None,
                interpreter_shebang=None,
                errno_code=errno.ENOENT,
                errno_name="ENOENT",
                error_message=(
                    f"Executable '{exec_input}' not found in PATH or relative path does not exist "
                    f"(target_cwd: {cwd_str})."
                ),
                can_execute=False
            )
            return self._finalize_receipt(receipt_payload)

        # File exists - inspect properties and permissions
        is_dir = resolved_path.is_dir()
        is_file = resolved_path.is_file()

        if is_dir:
            receipt_payload = self._build_receipt_dict(
                timestamp=now_str,
                argv=argv_list,
                cwd=cwd_str,
                executable_input=exec_input,
                resolved_executable=str(resolved_path),
                path_lookup_success=path_lookup_success,
                exists=True,
                is_file=False,
                is_dir=True,
                is_executable=False,
                stat_mode_octal=oct(resolved_path.stat().st_mode),
                executable_sha256=None,
                interpreter_shebang=None,
                errno_code=errno.EACCES,
                errno_name="EACCES",
                error_message=f"Target executable is a directory, not a regular file: {resolved_path}",
                can_execute=False
            )
            return self._finalize_receipt(receipt_payload)

        # Permission check
        st_mode = resolved_path.stat().st_mode
        stat_octal = oct(st_mode)
        is_exec = os.access(resolved_path, os.X_OK)

        if not is_exec:
            receipt_payload = self._build_receipt_dict(
                timestamp=now_str,
                argv=argv_list,
                cwd=cwd_str,
                executable_input=exec_input,
                resolved_executable=str(resolved_path),
                path_lookup_success=path_lookup_success,
                exists=True,
                is_file=is_file,
                is_dir=False,
                is_executable=False,
                stat_mode_octal=stat_octal,
                executable_sha256=None,
                interpreter_shebang=None,
                errno_code=errno.EACCES,
                errno_name="EACCES",
                error_message=f"Permission denied: '{resolved_path}' does not have execute permission (st_mode: {stat_octal}).",
                can_execute=False
            )
            return self._finalize_receipt(receipt_payload)

        # 4. Hash executable and check for script interpreter (shebang)
        sha256_hash = hashlib.sha256()
        shebang: Optional[str] = None
        try:
            with open(resolved_path, "rb") as f:
                header = f.read(256)
                if header.startswith(b"#!"):
                    first_line = header.split(b"\n")[0].decode("utf-8", errors="replace")
                    shebang = first_line[2:].strip()
                f.seek(0)
                while chunk := f.read(65536):
                    sha256_hash.update(chunk)
            file_digest = sha256_hash.hexdigest()
        except Exception:
            file_digest = None

        # If shebang exists, verify interpreter presence
        if shebang:
            interp_parts = shebang.split()
            interp_bin = interp_parts[0]
            if interp_bin == "/usr/bin/env" and len(interp_parts) > 1:
                interp_target = interp_parts[1]
                interp_resolved = shutil.which(interp_target, path=env_map.get("PATH"))
            else:
                interp_resolved = shutil.which(interp_bin, path=env_map.get("PATH")) or (
                    interp_bin if os.path.exists(interp_bin) else None
                )

            if not interp_resolved or not os.path.exists(interp_resolved):
                receipt_payload = self._build_receipt_dict(
                    timestamp=now_str,
                    argv=argv_list,
                    cwd=cwd_str,
                    executable_input=exec_input,
                    resolved_executable=str(resolved_path),
                    path_lookup_success=path_lookup_success,
                    exists=True,
                    is_file=is_file,
                    is_dir=False,
                    is_executable=is_exec,
                    stat_mode_octal=stat_octal,
                    executable_sha256=file_digest,
                    interpreter_shebang=shebang,
                    errno_code=errno.ENOEXEC,
                    errno_name="ENOEXEC",
                    error_message=f"Shebang interpreter '{shebang}' not found on system PATH (Exec format error).",
                    can_execute=False
                )
                return self._finalize_receipt(receipt_payload)

        # Everything passed preflight
        receipt_payload = self._build_receipt_dict(
            timestamp=now_str,
            argv=argv_list,
            cwd=cwd_str,
            executable_input=exec_input,
            resolved_executable=str(resolved_path),
            path_lookup_success=path_lookup_success,
            exists=True,
            is_file=is_file,
            is_dir=False,
            is_executable=True,
            stat_mode_octal=stat_octal,
            executable_sha256=file_digest,
            interpreter_shebang=shebang,
            errno_code=None,
            errno_name=None,
            error_message=None,
            can_execute=True
        )
        return self._finalize_receipt(receipt_payload)

    def execute_with_receipt(
        self,
        argv: Union[List[str], Tuple[str, ...]],
        cwd: Optional[Union[str, Path]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: int = 60
    ) -> Tuple[int, str, str, ProcessDiagnosticReceipt]:
        """
        Executes a subprocess command ONLY after preflight passes.
        Returns: (exit_code, stdout, stderr, ProcessDiagnosticReceipt)
        """
        report = self.inspect_command(argv, cwd=cwd, env=env)
        if not report.can_execute:
            return report.errno_code or -1, "", f"PREFLIGHT BLOCKED: {report.error_message}", report

        work_dir = report.cwd
        executable = report.resolved_executable or argv[0]
        full_argv = [executable] + list(argv[1:])

        exec_env = env if env is not None else os.environ.copy()
        exec_env["PYTHONPATH"] = f"{self.workspace_root}:{exec_env.get('PYTHONPATH', '')}"

        try:
            proc = subprocess.run(
                full_argv,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=exec_env,
                shell=False
            )
            return proc.returncode, proc.stdout, proc.stderr, report
        except subprocess.TimeoutExpired as te:
            out = te.stdout or ""
            err = f"TIMEOUT: Command exceeded {timeout}s limit."
            return -9, out, err, report
        except FileNotFoundError as fnfe:
            return errno.ENOENT, "", f"ENOENT: {fnfe}", report
        except PermissionError as pe:
            return errno.EACCES, "", f"EACCES: {pe}", report
        except NotADirectoryError as nde:
            return errno.ENOTDIR, "", f"ENOTDIR: {nde}", report
        except OSError as ose:
            return ose.errno or -1, "", f"OSERROR [{ose.errno}]: {ose}", report
        except Exception as ex:
            return -1, "", f"EXECUTION ERROR: {str(ex)}", report

    def _build_receipt_dict(
        self,
        timestamp: str,
        argv: List[str],
        cwd: str,
        executable_input: str,
        resolved_executable: Optional[str],
        path_lookup_success: bool,
        exists: bool,
        is_file: bool,
        is_dir: bool,
        is_executable: bool,
        stat_mode_octal: Optional[str],
        executable_sha256: Optional[str],
        interpreter_shebang: Optional[str],
        errno_code: Optional[int],
        errno_name: Optional[str],
        error_message: Optional[str],
        can_execute: bool
    ) -> Dict[str, Any]:
        return {
            "receipt_id": f"PROC-DIAG-{hashlib.sha256((timestamp + str(argv)).encode()).hexdigest()[:12]}",
            "timestamp": timestamp,
            "argv": argv,
            "cwd": cwd,
            "executable_input": executable_input,
            "resolved_executable": resolved_executable,
            "path_lookup_success": path_lookup_success,
            "exists": exists,
            "is_file": is_file,
            "is_dir": is_dir,
            "is_executable": is_executable,
            "stat_mode_octal": stat_mode_octal,
            "executable_sha256": executable_sha256,
            "interpreter_shebang": interpreter_shebang,
            "errno_code": errno_code,
            "errno_name": errno_name,
            "error_message": error_message,
            "can_execute": can_execute,
        }

    def _finalize_receipt(self, payload: Dict[str, Any]) -> ProcessDiagnosticReceipt:
        canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        receipt_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        return ProcessDiagnosticReceipt(
            receipt_id=payload["receipt_id"],
            timestamp=payload["timestamp"],
            argv=payload["argv"],
            cwd=payload["cwd"],
            executable_input=payload["executable_input"],
            resolved_executable=payload["resolved_executable"],
            path_lookup_success=payload["path_lookup_success"],
            exists=payload["exists"],
            is_file=payload["is_file"],
            is_dir=payload["is_dir"],
            is_executable=payload["is_executable"],
            stat_mode_octal=payload["stat_mode_octal"],
            executable_sha256=payload["executable_sha256"],
            interpreter_shebang=payload["interpreter_shebang"],
            errno_code=payload["errno_code"],
            errno_name=payload["errno_name"],
            error_message=payload["error_message"],
            can_execute=payload["can_execute"],
            receipt_hash=receipt_hash
        )

    def render_report(self, receipt: ProcessDiagnosticReceipt) -> str:
        """Formats the receipt into human-readable diagnostic text."""
        status = "PASSED" if receipt.can_execute else "FAILED"
        lines = [
            f"=== FORK/EXEC DIAGNOSTIC RECEIPT [{status}] ===",
            f"  Receipt ID:          {receipt.receipt_id}",
            f"  Receipt SHA-256:     {receipt.receipt_hash}",
            f"  Timestamp:           {receipt.timestamp}",
            f"  argv (array):        {json.dumps(receipt.argv)}",
            f"  cwd:                 {receipt.cwd}",
            f"  Executable Input:    {receipt.executable_input}",
            f"  Resolved Path:       {receipt.resolved_executable or 'UNRESOLVED'}",
            f"  PATH Lookup:         {'SUCCESS' if receipt.path_lookup_success else 'FAILED'}",
            f"  File Exists:         {receipt.exists}",
            f"  Is File:             {receipt.is_file} (is_dir: {receipt.is_dir})",
            f"  Executable Perm:     {receipt.is_executable} (mode: {receipt.stat_mode_octal or 'N/A'})",
            f"  Executable SHA-256:  {receipt.executable_sha256 or 'N/A'}",
            f"  Shebang:             {receipt.interpreter_shebang or 'None'}",
        ]
        if not receipt.can_execute:
            lines.append(f"  Errno:               {receipt.errno_name} ({receipt.errno_code})")
            lines.append(f"  Error Detail:        {receipt.error_message}")
        lines.append("================================================")
        return "\n".join(lines)
