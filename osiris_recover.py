#!/usr/bin/env python3
"""
osiris_recover.py — GitHub Repo Recovery Tool
Safe recovery of your 157 ENKI-420 repos after the compromise.

Usage:
    python osiris_recover.py list                          # list all your repos
    python osiris_recover.py audit ENKI-420/repo-name     # audit one repo (clone to temp, check, report)
    python osiris_recover.py audit-all                    # audit every repo (slow, but thorough)
    python osiris_recover.py clone ENKI-420/repo-name ~/repos/  # clone if audit passes
    python osiris_recover.py status                       # show recovery progress

Requires: gh CLI authenticated  OR  GITHUB_TOKEN env var
"""

import os
import sys
import json
import shutil
import subprocess
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RECOVERY_DIR = Path.home() / ".osiris" / "recovery"
RECOVERY_LOG = RECOVERY_DIR / "repo_status.json"
TARGET_DIR = Path.home() / "repos"

# ── GitHub API ────────────────────────────────────────────────────────────────

def gh_api(path: str) -> dict | list:
    """Call GitHub API via gh CLI (preferred) or curl."""
    try:
        r = subprocess.run(
            ["gh", "api", path, "--paginate"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0:
            # gh --paginate returns newline-separated JSON arrays; merge them
            lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
            merged = []
            for line in lines:
                obj = json.loads(line)
                if isinstance(obj, list):
                    merged.extend(obj)
                else:
                    return obj
            return merged
    except FileNotFoundError:
        pass  # gh not available, fall through to curl

    if not GITHUB_TOKEN:
        print("ERROR: Set GITHUB_TOKEN or install gh CLI and run 'gh auth login'")
        sys.exit(1)

    import urllib.request
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def list_repos(username: str = "ENKI-420") -> List[Dict]:
    """List all repos for a GitHub user."""
    print(f"Fetching repos for {username}...")
    repos = gh_api(f"/users/{username}/repos?per_page=100&sort=updated")
    if isinstance(repos, dict):
        repos = [repos]
    return repos


# ── Audit ─────────────────────────────────────────────────────────────────────

SUSPICIOUS_PATTERNS = [
    r"eval\s*\(",
    r"exec\s*\(",
    r"base64\.b64decode",
    r"__import__\s*\(",
    r"subprocess\s*\.\s*Popen.*shell\s*=\s*True",
    r"os\.system\s*\(",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r"nc\s+-e",
    r"reverse.?shell",
    r"AAAAAAAAAAAAAAAAAAAAAAAAAAAApHq",  # common base64-encoded shellcode prefix
    r"BEGIN RSA PRIVATE KEY",
    r"AKIA[A-Z0-9]{16}",  # AWS access key
    r"ghp_[A-Za-z0-9]{36}",  # GitHub token
    r"eyJhbGciOiJIUzI1NiIs",  # JWT
]

def _run(cmd: str, cwd: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           cwd=cwd, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"
    except Exception as e:
        return f"(error: {e})"


def audit_repo(full_name: str, work_dir: Optional[str] = None) -> Dict:
    """Clone to temp dir, run security audit, return report."""
    use_temp = work_dir is None
    if use_temp:
        work_dir = tempfile.mkdtemp(prefix="osiris_audit_")

    repo_dir = os.path.join(work_dir, full_name.split("/")[-1])
    report = {
        "repo": full_name,
        "ts": time.strftime("%Y-%m-%d %H:%M"),
        "clone_ok": False,
        "findings": [],
        "risk": "UNKNOWN",
        "contributors": [],
        "ci_cd_changes": "",
        "suspicious_code": "",
        "active_hooks": [],
        "large_files_added": "",
        "credentials_in_history": "",
        "recommendation": "",
    }

    try:
        # Clone (shallow first, then we check full history)
        print(f"  Cloning {full_name}...", end=" ", flush=True)
        clone_url = f"https://github.com/{full_name}.git"
        if GITHUB_TOKEN:
            clone_url = f"https://{GITHUB_TOKEN}@github.com/{full_name}.git"

        r = subprocess.run(
            ["git", "clone", "--depth=50", clone_url, repo_dir],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode != 0:
            report["findings"].append(f"Clone failed: {r.stderr[:200]}")
            report["risk"] = "ERROR"
            report["recommendation"] = "Cannot audit — clone failed"
            return report

        print("OK")
        report["clone_ok"] = True

        # 1. Contributors
        contribs = _run("git log --format='%ae %an' | sort | uniq -c | sort -rn | head -20", repo_dir)
        report["contributors"] = contribs

        unknown_contribs = [l for l in contribs.splitlines()
                            if "ENKI-420" not in l and "devin" not in l.lower()
                            and "davis" not in l.lower() and not l.strip().startswith("0")]
        if unknown_contribs:
            report["findings"].append(f"UNKNOWN CONTRIBUTORS: {unknown_contribs[:5]}")

        # 2. CI/CD + deps changes
        ci_changes = _run(
            "git log --oneline -- .github/ requirements*.txt pyproject.toml setup.py "
            "Dockerfile* Makefile .circleci/ .travis.yml",
            repo_dir
        )
        report["ci_cd_changes"] = ci_changes
        if ci_changes and "ENKI-420" not in ci_changes:
            report["findings"].append("CI/CD OR DEPS MODIFIED BY EXTERNAL COMMIT")

        # 3. Suspicious code in recent additions
        patterns = "|".join(SUSPICIOUS_PATTERNS)
        susp = _run(
            f"git diff HEAD~10 HEAD 2>/dev/null | grep -E '\\+.*({patterns})' | head -20",
            repo_dir, timeout=20
        )
        if not susp or susp == "(timeout)":
            susp = _run(
                f"grep -rn -E '({patterns})' --include='*.py' --include='*.sh' --include='*.js' . 2>/dev/null | head -20",
                repo_dir, timeout=20
            )
        report["suspicious_code"] = susp
        if susp and "(no matches)" not in susp and not susp.startswith("("):
            report["findings"].append(f"SUSPICIOUS CODE PATTERNS FOUND")

        # 4. Credential leak in history
        creds = _run(
            "git log -p --since='1 year ago' 2>/dev/null | "
            "grep -E '(AKIA[A-Z0-9]{16}|ghp_[A-Za-z]{36}|BEGIN RSA PRIVATE KEY|eyJhbGci)' | head -10",
            repo_dir, timeout=30
        )
        report["credentials_in_history"] = creds
        if creds and not creds.startswith("("):
            report["findings"].append("CREDENTIALS FOUND IN GIT HISTORY")

        # 5. Large binary files
        large = _run(
            "git log --all --diff-filter=A --stat --format='' | "
            "awk '{print $NF, $1}' | sort -rn | head -10",
            repo_dir
        )
        report["large_files_added"] = large

        # 6. Git hooks
        hooks_dir = Path(repo_dir) / ".git" / "hooks"
        if hooks_dir.exists():
            active = [h.name for h in hooks_dir.iterdir()
                      if h.is_file() and not h.name.endswith(".sample")]
            report["active_hooks"] = active
            if active:
                report["findings"].append(f"ACTIVE GIT HOOKS: {active}")

        # Risk scoring
        n = len(report["findings"])
        if n == 0:
            report["risk"] = "CLEAN"
            report["recommendation"] = "Safe to clone to ~/repos/"
        elif n <= 2:
            report["risk"] = "LOW"
            report["recommendation"] = "Review findings before cloning"
        elif n <= 4:
            report["risk"] = "MEDIUM"
            report["recommendation"] = "Manual review required — do not clone yet"
        else:
            report["risk"] = "HIGH"
            report["recommendation"] = "DO NOT CLONE — significant compromise indicators"

    finally:
        if use_temp and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

    return report


# ── Recovery Log ──────────────────────────────────────────────────────────────

def load_log() -> Dict:
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    if RECOVERY_LOG.exists():
        return json.loads(RECOVERY_LOG.read_text())
    return {}


def save_log(log: Dict):
    RECOVERY_DIR.mkdir(parents=True, exist_ok=True)
    RECOVERY_LOG.write_text(json.dumps(log, indent=2))


def print_report(report: Dict):
    risk_colors = {"CLEAN": "\033[32m", "LOW": "\033[33m",
                   "MEDIUM": "\033[33m", "HIGH": "\033[31m",
                   "UNKNOWN": "\033[90m", "ERROR": "\033[31m"}
    c = risk_colors.get(report["risk"], "")
    reset = "\033[0m"

    print(f"\n{'='*60}")
    print(f"  {c}{report['risk']}{reset}  {report['repo']}")
    print(f"  Audited: {report['ts']}")
    print(f"  Recommendation: {report['recommendation']}")
    if report["findings"]:
        print(f"\n  Findings ({len(report['findings'])}):")
        for f in report["findings"]:
            print(f"    ⚠  {f}")
    if report["contributors"]:
        print(f"\n  Contributors:\n    {report['contributors'][:300]}")
    print(f"{'='*60}\n")


# ── Clone ─────────────────────────────────────────────────────────────────────

def safe_clone(full_name: str, dest_base: str) -> bool:
    log = load_log()
    entry = log.get(full_name, {})

    if entry.get("risk") not in ("CLEAN", "LOW"):
        print(f"ERROR: {full_name} has not been audited as CLEAN/LOW. Run audit first.")
        print(f"  Current status: {entry.get('risk', 'not audited')}")
        return False

    dest = Path(dest_base) / full_name.split("/")[-1]
    if dest.exists():
        print(f"Already cloned: {dest}")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    clone_url = f"https://github.com/{full_name}.git"
    if GITHUB_TOKEN:
        clone_url = f"https://{GITHUB_TOKEN}@github.com/{full_name}.git"

    print(f"Cloning {full_name} → {dest}...")
    r = subprocess.run(["git", "clone", clone_url, str(dest)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode == 0:
        print(f"  ✓ Cloned to {dest}")
        log[full_name]["cloned_to"] = str(dest)
        save_log(log)
        return True
    else:
        print(f"  ✗ Failed: {r.stderr[:200]}")
        return False


# ── Status ────────────────────────────────────────────────────────────────────

def show_status():
    log = load_log()
    if not log:
        print("No repos audited yet. Run: python osiris_recover.py audit ENKI-420/repo-name")
        return

    by_risk = {"CLEAN": [], "LOW": [], "MEDIUM": [], "HIGH": [], "ERROR": [], "UNKNOWN": []}
    for name, entry in log.items():
        by_risk.setdefault(entry.get("risk", "UNKNOWN"), []).append(name)

    print("\n=== Recovery Status ===")
    for risk, repos in by_risk.items():
        if repos:
            print(f"  {risk}: {len(repos)} repos")
            for r in repos[:5]:
                cloned = " [cloned]" if log[r].get("cloned_to") else ""
                print(f"    {r}{cloned}")
            if len(repos) > 5:
                print(f"    ...and {len(repos)-5} more")
    print(f"\nTotal audited: {len(log)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "list":
        username = args[1] if len(args) > 1 else "ENKI-420"
        repos = list_repos(username)
        print(f"\n{username} has {len(repos)} repos:\n")
        for r in sorted(repos, key=lambda x: x.get("updated_at", ""), reverse=True):
            private = " [private]" if r.get("private") else ""
            print(f"  {r['full_name']}{private}  ({r.get('language','?')})")
        print(f"\nTotal: {len(repos)}")

    elif cmd == "audit":
        if len(args) < 2:
            print("Usage: python osiris_recover.py audit ENKI-420/repo-name")
            sys.exit(1)
        full_name = args[1]
        if "/" not in full_name:
            full_name = f"ENKI-420/{full_name}"
        report = audit_repo(full_name)
        print_report(report)
        log = load_log()
        log[full_name] = report
        save_log(log)
        print(f"Report saved to {RECOVERY_LOG}")

    elif cmd == "audit-all":
        username = args[1] if len(args) > 1 else "ENKI-420"
        repos = list_repos(username)
        log = load_log()
        print(f"\nAuditing {len(repos)} repos (this will take a while)...\n")
        for i, repo in enumerate(repos):
            name = repo["full_name"]
            if name in log and log[name].get("risk") not in ("UNKNOWN", "ERROR"):
                print(f"  [{i+1}/{len(repos)}] SKIP (already audited): {name}")
                continue
            print(f"\n[{i+1}/{len(repos)}] {name}")
            report = audit_repo(name)
            print_report(report)
            log[name] = report
            save_log(log)
            time.sleep(1)  # be nice to GitHub

        show_status()

    elif cmd == "clone":
        if len(args) < 2:
            print("Usage: python osiris_recover.py clone ENKI-420/repo-name [dest_dir]")
            sys.exit(1)
        full_name = args[1]
        if "/" not in full_name:
            full_name = f"ENKI-420/{full_name}"
        dest = args[2] if len(args) > 2 else str(TARGET_DIR)
        safe_clone(full_name, dest)

    elif cmd == "status":
        show_status()

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: list, audit, audit-all, clone, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
