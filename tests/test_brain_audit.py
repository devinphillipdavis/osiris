"""osiris_brain runs no subprocess through a shell, and audit_repo still reports."""

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import osiris_brain

BRAIN_SOURCE = _ROOT / "osiris_brain.py"


def test_no_call_in_osiris_brain_passes_shell_true():
    tree = ast.parse(BRAIN_SOURCE.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False)
    ]
    assert offenders == [], f"shell= not literally False at lines {offenders}"


def test_no_os_system_or_popen_in_osiris_brain():
    tree = ast.parse(BRAIN_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) not in {("os", "system"), ("os", "popen")}


git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "Ada", "GIT_AUTHOR_EMAIL": "ada@example.org",
                        "GIT_COMMITTER_NAME": "Ada", "GIT_COMMITTER_EMAIL": "ada@example.org",
                        "HOME": str(repo), "PATH": "/usr/bin:/bin"})


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "big.py").write_text("x = 1\n" * 50)
    (r / "small.py").write_text("y = 2\n")
    (r / "pyproject.toml").write_text("[project]\nname='t'\n")
    (r / "leak.py").write_text("eval('1')\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "initial")
    return r


@git
def test_audit_reports_every_section(repo):
    report = osiris_brain.audit_repo(str(repo))
    assert "ada@example.org Ada" in report
    assert "initial" in report
    assert "eval('1')" in report  # suspicious-pattern scan
    largest = osiris_brain._largest_added_files(repo).splitlines()
    assert largest[0].split()[-1] == "big.py"  # sorted by size, not by diffstat bars


@git
def test_audit_path_is_never_shell_interpreted(tmp_path):
    weird = tmp_path / "repo $(touch PWNED) `touch PWNED2`"
    weird.mkdir()
    _git(weird, "init", "-q")
    osiris_brain.audit_repo(str(weird))
    assert not list(tmp_path.rglob("PWNED*"))


def test_audit_missing_path():
    assert osiris_brain.audit_repo("/nonexistent/osiris/repo").startswith("ERROR")
