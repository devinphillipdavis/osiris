"""
Unit and Regression Tests for OSIRIS Safe Proposal-to-Patch Workflow & AST Security Firewall
===========================================================================================
"""

import tempfile
from pathlib import Path

import pytest

from osiris_cli.safe_patch import (
    ASTSecurityInspector,
    PatchReceipt,
    ProposalExtractor,
    SafePatchWorkflow,
    SandboxRunner,
    generate_patch_diff,
    validate_python_code,
)


def test_code_fence_extraction_preserves_structure():
    """Validates that proposal extraction preserves docstrings, comments, indentation, and directives."""
    raw_response = '''
Here is the proposed implementation for quantum telemetry:

# TargetFile: telemetry_module.py
```python
def compute_coherence(shots: int) -> float:
    """Computes basic survival probability without post-selection."""
    # Internal baseline check
    if shots <= 0:
        return 0.0
    return float(shots) / 1000.0
```

Please review before applying.
'''
    proposals = ProposalExtractor.extract(raw_response)
    assert len(proposals) == 1
    p = proposals[0]
    assert p.language == "python"
    assert p.target_file == "telemetry_module.py"
    assert '"""Computes basic survival probability without post-selection."""' in p.code
    assert "    # Internal baseline check" in p.code


def test_syntax_validation_catches_invalid_syntax():
    """Validates that syntax errors are caught before AST inspection."""
    bad_code = "def invalid_syntax_func(:\n    pass"
    res = validate_python_code(bad_code)
    assert res.is_valid_syntax is False
    assert res.is_safe is False
    assert "SyntaxError" in (res.syntax_error or "")


def test_ast_firewall_blocks_forbidden_builtins():
    """Validates that dangerous builtins (eval, exec, compile, open) are blocked."""
    proposals = [
        "eval('1 + 1')",
        "exec('print(1)')",
        "compile('x = 1', '<string>', 'exec')",
        "with open('secret.txt', 'r') as f:\n    pass",
        "__import__('os').system('ls')",
    ]
    for code in proposals:
        res = validate_python_code(code)
        assert res.is_valid_syntax is True
        assert res.is_safe is False
        assert len(res.security_violations) > 0
        assert any("Forbidden builtin" in v or "Forbidden module" in v for v in res.security_violations)


def test_ast_firewall_blocks_forbidden_modules():
    """Validates that unauthorized networking, subprocess, and FFI modules are blocked."""
    forbidden_snippets = [
        "import subprocess\nsubprocess.run(['ls'])",
        "import socket\ns = socket.socket()",
        "import requests\nrequests.get('https://example.com')",
        "import urllib.request",
        "import ctypes",
        "import pickle",
    ]
    for code in forbidden_snippets:
        res = validate_python_code(code)
        assert res.is_safe is False
        assert len(res.security_violations) > 0
        assert any("Forbidden module import" in v for v in res.security_violations)


def test_ast_firewall_blocks_destructive_os_calls():
    """Validates that os.system, os.popen, shutil.rmtree are blocked."""
    forbidden_snippets = [
        "import os\nos.system('rm -rf /')",
        "import os\nos.popen('uname -a')",
        "import shutil\nshutil.rmtree('/tmp/data')",
    ]
    for code in forbidden_snippets:
        res = validate_python_code(code)
        assert res.is_safe is False
        assert any("Forbidden system call" in v or "Forbidden module" in v for v in res.security_violations)


def test_ast_firewall_allows_safe_code():
    """Validates that clean algorithmic code passes AST security inspection."""
    safe_code = '''
import math

def calculate_survival_ratio(counts: dict, shots: int) -> float:
    """Calculates ground state probability."""
    if shots == 0:
        return 0.0
    zero_count = counts.get("0", 0)
    return math.sqrt(zero_count / shots)
'''
    res = validate_python_code(safe_code)
    assert res.is_valid_syntax is True
    assert res.is_safe is True
    assert len(res.security_violations) == 0


def test_sandbox_runner_execution():
    """Validates that SandboxRunner executes valid code in an isolated directory."""
    clean_code = "print('SANDBOX_RUNNER_SUCCESS')"
    result = SandboxRunner.dry_run(clean_code, timeout_seconds=5)
    assert result.exit_code == 0
    assert "SANDBOX_RUNNER_SUCCESS" in result.stdout
    assert result.timed_out is False


def test_sandbox_runner_timeout():
    """Validates that SandboxRunner enforces execution timeouts."""
    infinite_loop = "import time\nwhile True:\n    time.sleep(0.1)"
    result = SandboxRunner.dry_run(infinite_loop, timeout_seconds=1)
    assert result.timed_out is True
    assert result.exit_code == -9


def test_safe_patch_workflow_end_to_end():
    """Validates full 5-stage workflow from model text to patch receipt and file application."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir)
        target_file = workspace / "math_utils.py"
        target_file.write_text("def add(a, b):\n    return a - b\n")

        raw_response = '''
Here is the fix for addition:
# TargetFile: math_utils.py
```python
def add(a, b):
    """Correct addition function."""
    return a + b
```
'''
        workflow = SafePatchWorkflow(workspace_root=tmp_dir)
        processed = workflow.process_proposal(raw_response, target_relative_path="math_utils.py")

        assert processed["success"] is True
        assert processed["stage"] == "APPROVAL_GATE_READY"
        assert "def add(a, b):" in processed["diff"]
        assert "+    return a + b" in processed["diff"]
        assert "-    return a - b" in processed["diff"]

        # Simulate Human Approval
        receipt: PatchReceipt = workflow.apply_patch(
            target_relative_path="math_utils.py",
            code=processed["code"],
            diff_text=processed["diff"],
            original_sha256=processed["original_sha256"],
            ast_safe=True,
            sandbox_passed=True,
            human_approved=True,
            approval_token="HUMAN-TOKEN-9988"
        )

        assert receipt.applied is True
        assert receipt.human_approved is True
        assert receipt.approval_token == "HUMAN-TOKEN-9988"
        assert receipt.receipt_hash is not None

        # Verify disk modification occurred only after approval
        updated_content = target_file.read_text()
        assert "return a + b" in updated_content
