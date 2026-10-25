"""
Integration tests for research_cli.py
Covers:
- status command
- nclm status command
- validate-registry command
- policy explain command
- end-to-end command dispatch
"""

import json
import pytest
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args):
    cmd = [sys.executable, str(_ROOT / "research_cli.py")] + list(args)
    proc = subprocess.run(cmd, cwd=str(_ROOT), capture_output=True, text=True)
    return proc


def test_cli_status():
    proc = run_cli("status")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["workbench_version"] == "1.0.0"
    assert "DEFAULT_DENY_EXTERNAL_EFFECTS" in data["governance_invariants"]


def test_cli_nclm_status():
    proc = run_cli("nclm", "status")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "frozen_gradients" in data
    assert data["frozen_gradients"] is True


def test_cli_validate_registry():
    proc = run_cli("validate-registry")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["registry_status"] == "VALID"
    assert "OCCR-NEG-0001" in data["negative_controls"]


def test_cli_policy_explain_qpu():
    proc = run_cli("policy", "explain", "cloud_qpu_dispatch")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "DENIED BY DEFAULT" in data["policy_explanation"]
    assert "OSIRIS-HUMAN-AUTH:QPU:" in data["policy_explanation"]
