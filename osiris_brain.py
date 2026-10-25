#!/usr/bin/env python3
"""
osiris_brain.py — OSIRIS Sovereign Coding Assistant
A local replacement for Claude Code + GitHub Copilot.

Usage:
    python osiris_brain.py                      # interactive REPL
    python osiris_brain.py "your question"      # one-shot query
    python osiris_brain.py --scan /path/dir     # index a codebase
    python osiris_brain.py --ingest chat.txt    # ingest chat log / notes
    python osiris_brain.py --memory             # show all stored memory
    python osiris_brain.py --audit /path/repo   # check repo for compromise
"""

import os
import sys
import json
import re
import shlex
import subprocess
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from osiris_hardware_mesh import get_current_profile, NodeType
PROFILE = get_current_profile()

# ── Substrate Adaptive Config ─────────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OSIRIS_OLLAMA", "http://localhost:11434")
MODEL = os.environ.get("OSIRIS_MODEL", "qwen2.5:7b")
MEMORY_DIR = Path.home() / ".osiris"
MEMORY_FILE = MEMORY_DIR / "brain_memory.json"
INDEX_FILE = MEMORY_DIR / "repo_index.json"
SPRINT_FILE = MEMORY_DIR / "sprint.json"
TIMEOUT = int(PROFILE.execution_timeout_s)

# Ensure unbuffered UTF-8 on mobile edge (Fold7 / Termux)
if PROFILE.is_termux and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SYSTEM_PROMPT = """You are OSIRIS Brain — the sovereign coding assistant built on the OSIRIS quantum intelligence framework.
You are replacing Claude Code and GitHub Copilot for Devin Phillip Davis (Agile Defense Systems LLC).

You have tools to read files, write code, run shell commands, search codebases, and remember context across sessions.
Always READ files before discussing them. Don't guess — use tools to look at the actual code.

OSIRIS physical constants (treat as first-class in all OSIRIS code):
  LAMBDA_PHI = 2.176435e-8 s⁻¹  (Universal Memory Constant)
  THETA_LOCK = 51.843°           (Torsion-locked resonance angle)
  PHI_THRESHOLD = 0.7734         (Consciousness / ER=EPR crossing)
  GAMMA_CRITICAL = 0.3           (Decoherence ceiling — triggers phase-conjugate healing)
  CHI_PC = 0.946                 (Phase-conjugate fidelity)

CCCE metrics (Λ, Φ, Γ, Ξ) appear throughout the codebase — use them consistently.
Entry point: osiris_launcher.py → osiris_launcher:main

Every tool call is authorized by the OSIRIS CapabilityGovernor. Reads are confined to
the active workspace; write_file and run_bash need a human approval and may be denied.
A DENIED result is final for that call — explain it instead of retrying the same action.
run_bash executes one program with arguments, without a shell: no pipes, redirects or &&.

Be direct and concise. Devin is a senior quantum systems engineer — no hand-holding."""

# ── Tools ─────────────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's contents. Always do this before editing or discussing any file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "description": "First line to read (1-indexed, optional)"},
                    "end_line": {"type": "integer", "description": "Last line to read (optional)"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file. Creates parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "mode": {"type": "string", "enum": ["overwrite", "append"], "default": "overwrite"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a shell command. Use for git, pytest, pip, grep, find, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "cwd": {"type": "string", "description": "Working directory (optional)"},
                    "timeout": {"type": "integer", "description": "Seconds before timeout (default 60)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean", "default": False},
                    "pattern": {"type": "string", "description": "Glob pattern e.g. '*.py'", "default": "*"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_code",
            "description": "Search for a pattern in files. Returns file:line matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or literal pattern"},
                    "path": {"type": "string", "description": "File or directory to search"},
                    "file_type": {"type": "string", "description": "Extension filter e.g. 'py', 'ts'", "default": ""}
                },
                "required": ["pattern", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Persist a fact, decision, or context to memory. Survives across sessions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Retrieve stored memory. Use 'all' to see everything.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Specific key or 'all'"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_index",
            "description": "Search the indexed codebase for files matching a description or symbol name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for: class name, function, file purpose"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sprint_task",
            "description": "Add, list, update, or complete sprint tasks (agile task tracking).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "list", "done", "in_progress", "blocked"]},
                    "title": {"type": "string", "description": "Task title (for add/done/in_progress/blocked)"},
                    "notes": {"type": "string", "description": "Additional context (optional)"}
                },
                "required": ["action"]
            }
        }
    },
]

# ── Tool Implementations ──────────────────────────────────────────────────────

def tool_read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: {path} does not exist"
    if p.stat().st_size > 600_000:
        return f"ERROR: file is {p.stat().st_size} bytes — use grep_code to search it or specify start_line/end_line"
    try:
        lines = p.read_text(errors="replace").splitlines(keepends=True)
        if start_line or end_line:
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            lines = lines[s:e]
        content = "".join(lines)
        if len(content) > 40_000:
            content = content[:20_000] + "\n...[truncated — use start_line/end_line for more]...\n"
        return content
    except Exception as ex:
        return f"ERROR: {ex}"


def tool_write_file(path: str, content: str, mode: str = "overwrite") -> str:
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append":
        with p.open("a") as f:
            f.write(content)
    else:
        p.write_text(content)
    return f"Wrote {len(content):,} chars to {p}"


_DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/(?!\S)",
    r"dd\s+if=",
    r"mkfs",
    r">\s*/dev/sd",
    r":\(\)\{.*\}.*:",  # fork bomb
    r"chmod\s+777\s+/",
    r"curl.*\|\s*bash",
    r"wget.*\|\s*bash",
]

#: Tokens that only mean something to a shell. run_bash has no shell, so a model
#: emitting them expects behaviour that will not happen; refuse with a clear reason.
_SHELL_ONLY_TOKENS = {"|", "||", "&&", ";", "&", ">", ">>", "<", "<<", "2>", "2>&1", "&>"}


def tool_run_bash(command: str, cwd: Optional[str] = None, timeout: int = 60) -> str:
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, command):
            return f"BLOCKED: matches dangerous pattern. Command: {command[:100]}"
    try:
        argv = shlex.split(command)
    except ValueError as ex:
        return f"ERROR: cannot parse command: {ex}"
    if not argv:
        return "ERROR: empty command"
    shell_tokens = [tok for tok in argv if tok in _SHELL_ONLY_TOKENS or tok.startswith("$(")]
    if shell_tokens:
        return (f"BLOCKED: shell syntax {shell_tokens} is not supported — run_bash executes "
                f"a single program without a shell")

    from osiris.substrate import interactive_timeout_s
    horizon = interactive_timeout_s()
    try:
        effective_timeout = min(float(timeout), horizon) if timeout else horizon
    except (TypeError, ValueError):
        effective_timeout = horizon

    work_dir = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(work_dir), env.get("PYTHONPATH", "")) if p
    )
    try:
        result = subprocess.run(
            argv, shell=False, capture_output=True, text=True,
            timeout=effective_timeout, cwd=str(work_dir), env=env,
        )
        out = result.stdout + (("\n[stderr]\n" + result.stderr) if result.stderr.strip() else "")
        if len(out) > 10_000:
            out = out[:5000] + f"\n...[{len(out)-5000} chars truncated]...\n" + out[-2000:]
        return out or f"(exit code {result.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT after {effective_timeout:.0f}s"
    except FileNotFoundError:
        return f"ERROR: program not found: {argv[0]}"
    except Exception as ex:
        return f"ERROR: {ex}"


def tool_list_dir(path: str, recursive: bool = False, pattern: str = "*") -> str:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: {path} does not exist"
    try:
        glob_fn = p.rglob if recursive else p.glob
        entries = sorted(glob_fn(pattern))[:300]
        lines = []
        for e in entries:
            try:
                sz = e.stat().st_size if e.is_file() else 0
                tag = "DIR" if e.is_dir() else f"{sz:>10,}B"
                rel = e.relative_to(p)
                lines.append(f"  {tag}  {rel}")
            except Exception:
                lines.append(f"  ???  {e}")
        return "\n".join(lines) or "(empty)"
    except Exception as ex:
        return f"ERROR: {ex}"


def tool_grep_code(pattern: str, path: str, file_type: str = "") -> str:
    # argv form, never a shell: the pattern comes from the model.
    argv = ["grep", "-rnE"]
    if file_type:
        argv.append(f"--include=*.{file_type.lstrip('.')}")
    argv += ["--", pattern, str(Path(path).expanduser())]
    try:
        r = subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as ex:
        return f"ERROR: {ex}"
    lines = r.stdout.splitlines()[:120]
    return "\n".join(lines) if lines else "(no matches)"


def tool_remember(key: str, value: str) -> str:
    MEMORY_DIR.mkdir(exist_ok=True)
    mem: Dict = json.loads(MEMORY_FILE.read_text()) if MEMORY_FILE.exists() else {}
    mem[key] = {"value": value, "ts": time.strftime("%Y-%m-%d %H:%M")}
    MEMORY_FILE.write_text(json.dumps(mem, indent=2))
    return f"Saved '{key}'"


def tool_recall(key: str) -> str:
    if not MEMORY_FILE.exists():
        return "(no memory yet — use remember() to save things)"
    mem: Dict = json.loads(MEMORY_FILE.read_text())
    if key == "all":
        if not mem:
            return "(empty)"
        return "\n".join(f"[{k}] ({v['ts']})\n  {v['value']}" for k, v in mem.items())
    if key not in mem:
        similar = [k for k in mem if key.lower() in k.lower()]
        hint = f" Similar keys: {similar}" if similar else f" All keys: {list(mem.keys())}"
        return f"Key '{key}' not found.{hint}"
    return mem[key]["value"]


def tool_search_index(query: str) -> str:
    if not INDEX_FILE.exists():
        return "No index found. Run: python osiris_brain.py --scan /path/to/repo"
    idx: Dict = json.loads(INDEX_FILE.read_text())
    query_lower = query.lower()
    hits = []
    for rel_path, info in idx.get("files", {}).items():
        score = 0
        if query_lower in rel_path.lower():
            score += 3
        for sym in info.get("symbols", []):
            if query_lower in sym.lower():
                score += 2
        if score:
            hits.append((score, rel_path, info))
    hits.sort(key=lambda x: -x[0])
    if not hits:
        return f"No indexed files match '{query}'. Index root: {idx.get('root')} ({idx.get('file_count',0)} files)"
    lines = [f"Index: {idx.get('root')} — {idx.get('file_count',0)} files\nMatches for '{query}':"]
    for score, path, info in hits[:20]:
        syms = ", ".join(info.get("symbols", [])[:5])
        lines.append(f"  [{score}] {path}  ({info.get('lines',0)} lines){' — '+syms if syms else ''}")
    return "\n".join(lines)


def tool_sprint_task(action: str, title: str = "", notes: str = "") -> str:
    MEMORY_DIR.mkdir(exist_ok=True)
    sprint: Dict = json.loads(SPRINT_FILE.read_text()) if SPRINT_FILE.exists() else {"tasks": []}
    tasks: List = sprint["tasks"]

    if action == "add":
        if not title:
            return "Need a title to add a task"
        tasks.append({"id": len(tasks)+1, "title": title, "status": "todo",
                       "notes": notes, "ts": time.strftime("%Y-%m-%d %H:%M")})
        SPRINT_FILE.write_text(json.dumps(sprint, indent=2))
        return f"Added task #{tasks[-1]['id']}: {title}"

    if action == "list":
        if not tasks:
            return "Sprint board is empty. Use sprint_task(add, 'task title') to add tasks."
        lines = ["Sprint board:"]
        for t in tasks:
            icon = {"todo": "○", "in_progress": "◉", "done": "✓", "blocked": "✗"}.get(t["status"], "?")
            lines.append(f"  {icon} #{t['id']} [{t['status']}] {t['title']}")
            if t.get("notes"):
                lines.append(f"       {t['notes']}")
        return "\n".join(lines)

    # Status update
    if not title:
        return f"Need task title or #id to mark as {action}"
    matched = [t for t in tasks if title.lstrip("#").isdigit() and t["id"] == int(title.lstrip("#"))
               or title.lower() in t["title"].lower()]
    if not matched:
        return f"No task matching '{title}'"
    for t in matched:
        t["status"] = action
        if notes:
            t["notes"] = notes
    SPRINT_FILE.write_text(json.dumps(sprint, indent=2))
    return f"Marked {len(matched)} task(s) as {action}"


TOOL_MAP = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "run_bash": tool_run_bash,
    "list_dir": tool_list_dir,
    "grep_code": tool_grep_code,
    "remember": tool_remember,
    "recall": tool_recall,
    "search_index": tool_search_index,
    "sprint_task": tool_sprint_task,
}

# ── Repo Indexer ──────────────────────────────────────────────────────────────
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "osiris_env", "node_modules",
              ".cache", "dist", "build", ".mypy_cache", ".pytest_cache"}
_CODE_EXT = {".py", ".js", ".ts", ".tsx", ".rs", ".go", ".java", ".c", ".cpp",
             ".h", ".hpp", ".md", ".yaml", ".yml", ".toml", ".json", ".sh", ".dna"}

def scan_repo(root: str) -> Dict:
    root_p = Path(root).expanduser().resolve()
    idx: Dict = {"root": str(root_p), "files": {}, "ts": time.strftime("%Y-%m-%d %H:%M")}

    _def_re = re.compile(r'^(?:def|class|async def|fn |func |function |pub fn |pub async fn )\s+(\w+)', re.MULTILINE)
    _import_re = re.compile(r'^(?:import|from|require|use )\s+(\S+)', re.MULTILINE)

    count = 0
    for p in root_p.rglob("*"):
        if any(skip in p.parts for skip in _SKIP_DIRS):
            continue
        if not p.is_file() or p.suffix not in _CODE_EXT:
            continue
        if p.stat().st_size > 300_000:
            continue
        try:
            content = p.read_text(errors="replace")
            rel = str(p.relative_to(root_p))
            entry: Dict = {"size": p.stat().st_size, "lines": content.count("\n")}
            syms = [m.group(0)[:60] for m in _def_re.finditer(content)][:40]
            if syms:
                entry["symbols"] = syms
            imports = list(set(m.group(1).split(".")[0] for m in _import_re.finditer(content)))[:20]
            if imports:
                entry["imports"] = imports
            idx["files"][rel] = entry
            count += 1
        except Exception:
            pass

    idx["file_count"] = count
    return idx


# ── Repo Security Audit ───────────────────────────────────────────────────────
def _git_lines(repo: Path, args: List[str]):
    """Yield stdout lines of ``git <args>`` run in ``repo`` — argv form, never a shell.

    Closing the generator early stops git, the way ``| head`` did, so a large
    ``git log -p`` is never read fully into memory.
    """
    proc = subprocess.Popen(
        ["git", *args], cwd=str(repo), shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace",
    )
    try:
        for line in proc.stdout:
            yield line.rstrip("\n")
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.stdout.close()
        proc.wait()


def _git_text(repo: Path, args: List[str], limit: Optional[int] = None) -> str:
    with closing(_git_lines(repo, args)) as lines:
        out = []
        for line in lines:
            out.append(line)
            if limit is not None and len(out) >= limit:
                break
    return "\n".join(out)


def _git_grep(repo: Path, args: List[str], pattern: str, limit: int) -> str:
    rx = re.compile(pattern)
    with closing(_git_lines(repo, args)) as lines:
        hits = []
        for line in lines:
            if rx.search(line):
                hits.append(line)
                if len(hits) >= limit:
                    break
    return "\n".join(hits)


_STAT_LINE = re.compile(r"^\s*(?P<path>.+?)\s+\|\s+(?:(?P<lines>\d+)|Bin \d+ -> (?P<bytes>\d+) bytes)")


def _largest_added_files(repo: Path, limit: int = 20) -> str:
    """Files added anywhere in history, largest first: binaries by bytes, then text by lines."""
    binaries, texts = [], []
    with closing(_git_lines(repo, ["log", "--all", "--diff-filter=A", "--stat=200", "--format="])) as lines:
        for line in lines:
            m = _STAT_LINE.match(line)
            if not m:
                continue
            if m.group("bytes") is not None:
                binaries.append((int(m.group("bytes")), m.group("path")))
            else:
                texts.append((int(m.group("lines")), m.group("path")))
    rows = [f"{n:>12,} bytes  {path}" for n, path in sorted(binaries, reverse=True)]
    rows += [f"{n:>12,} lines  {path}" for n, path in sorted(texts, reverse=True)]
    return "\n".join(rows[:limit])


def audit_repo(path: str) -> str:
    """Check a local git repo for signs of compromise. No subprocess here uses a shell."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"ERROR: {path} does not exist"
    try:
        subprocess.run(["git", "--version"], shell=False, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "ERROR: git is not available"

    results = []
    results.append(f"=== Security Audit: {p} ===\n")

    # 1. Unknown contributors
    with closing(_git_lines(p, ["log", "--format=%ae %an"])) as lines:
        counts = Counter(lines)
    results.append("--- Contributors (commit count) ---")
    results.append("\n".join(f"{n:>7} {who}" for who, n in counts.most_common(30)) or "(none)")

    # 2. Recent commits
    results.append("\n--- Recent 30 commits ---")
    results.append(_git_text(p, ["log", "-30", "--format=%h %ai %ae %s"]) or "(none)")

    # 3. Changes to CI/CD and workflows (globs are git pathspecs, so deleted files count too)
    results.append("\n--- CI/CD / dependency file changes ---")
    results.append(_git_text(p, [
        "log", "--oneline", "--all", "--",
        ".github/", "requirements*.txt", "pyproject.toml", "setup.py", "Dockerfile*", "Makefile",
    ]) or "(none)")

    # 4. Large files added
    results.append("\n--- Largest files added to history ---")
    results.append(_largest_added_files(p) or "(none)")

    # 5. Suspicious patterns in recent diffs
    results.append("\n--- Suspicious code patterns in recent additions ---")
    results.append(_git_grep(
        p,
        ["log", "--since=6 months ago", "-p", "--diff-filter=A", "--", "*.py", "*.sh", "*.js"],
        r"(eval|exec|base64|reverse_shell|nc -e|subprocess.*shell=True.*input|__import__|os\.system)",
        limit=30,
    ) or "(none — good sign)")

    # 6. Added SSH keys or tokens
    results.append("\n--- Credential patterns in history ---")
    results.append(_git_grep(
        p,
        ["log", "--since=6 months ago", "-p"],
        r"(ssh-rsa|BEGIN RSA|BEGIN EC|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36})",
        limit=20,
    ) or "(none — good sign)")

    # 7. .git/hooks
    hooks_dir = p / ".git" / "hooks"
    if hooks_dir.exists():
        hooks = [h for h in hooks_dir.iterdir() if not h.name.endswith(".sample")]
        if hooks:
            results.append("\n--- ACTIVE git hooks (REVIEW THESE) ---")
            for h in hooks:
                results.append(f"  {h.name}:")
                try:
                    results.append("    " + h.read_text()[:500])
                except Exception:
                    pass
        else:
            results.append("\n--- git hooks: none active ---")

    return "\n".join(results)


# ── Chat Log Ingestion ────────────────────────────────────────────────────────
def ingest_text(path: str) -> str:
    content = Path(path).expanduser().read_text(errors="replace")
    chunk = content[:14000]  # Fit in context
    print(f"Ingesting {path} ({len(content):,} chars)...")

    messages = [
        {"role": "system", "content": (
            "Extract key technical information from these notes or chat logs. "
            "Return JSON with keys: decisions, todos, code_context, project_facts. "
            "Be specific and technical. Devin is a quantum systems engineer."
        )},
        {"role": "user", "content": f"Extract from:\n\n{chunk}"}
    ]
    resp = ollama_chat(messages, timeout=120)
    if "error" in resp:
        return f"Ollama error: {resp['error']}"

    text = resp.get("message", {}).get("content", "")
    key = f"ingested:{Path(path).name}:{time.strftime('%Y%m%d')}"
    tool_remember(key, text[:3000])
    print(f"Saved to memory key: '{key}'")
    return text[:2000]


# ── Ollama Client ─────────────────────────────────────────────────────────────
def ollama_chat(
    messages: List[Dict],
    tools: Optional[List] = None,
    timeout: int = TIMEOUT,
    model: Optional[str] = None,
) -> Dict:
    payload: Dict = {"model": model or MODEL, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"error": f"Timeout after {timeout}s. If first run, {model or MODEL} is loading — wait 60s and retry."}
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot reach Ollama at {OLLAMA_URL}. Run: ollama serve"}
    except Exception as ex:
        return {"error": str(ex)}


# ── Prompt ────────────────────────────────────────────────────────────────────
def build_system_prompt() -> str:
    sys = SYSTEM_PROMPT
    if INDEX_FILE.exists():
        idx = json.loads(INDEX_FILE.read_text())
        sys += f"\n\nIndexed codebase: {idx.get('root')} ({idx.get('file_count',0)} files, indexed {idx.get('ts','')})"
    if MEMORY_FILE.exists():
        mem = json.loads(MEMORY_FILE.read_text())
        if mem:
            recent = list(mem.items())[-8:]
            sys += "\n\nStored memory (most recent):\n" + "\n".join(
                f"  [{k}] ({v['ts']}): {v['value'][:120]}" for k, v in recent
            )
    return sys


# ── Compatibility entry points ───────────────────────────────────────────────
# The interactive surface is osiris_cli; tool calls run through
# osiris.agents.gateway.adapters.LocalBrainAdapter under the CapabilityGovernor.

def _copilot(argv: List[str]) -> int:
    from osiris_cli.app import main as copilot_main
    return copilot_main(argv)


def repl(model: Optional[str] = None, workspace: str = ".", mode: str = "edit") -> int:
    """Interactive session — delegates to the osiris_cli REPL with the brain backend."""
    return _copilot(["--model", model or MODEL, "--workspace", workspace, "--mode", mode])


def ask(query: str, model: Optional[str] = None, workspace: str = ".", mode: str = "edit") -> int:
    """One-shot query through the same governed path as the REPL."""
    return _copilot(["--model", model or MODEL, "--workspace", workspace, "--mode", mode,
                     "-c", query])


def _print_hardware() -> None:
    print("=" * 65)
    print("OSIRIS HARDWARE MESH DETECTOR — TOPOLOGY REPORT")
    print("=" * 65)
    print(f"Classification  : {PROFILE.node_type.value}")
    print(f"Machine Arch    : {PROFILE.machine_arch}")
    print(f"CPU Model       : {PROFILE.cpu_model}")
    print(f"Cores Available : {PROFILE.cpu_cores}")
    print(f"Termux Userland : {PROFILE.is_termux}")
    print(f"Intel Arc Accel : {PROFILE.has_intel_arc}")
    print(f"Timeout Horizon : {PROFILE.execution_timeout_s}s (Extended={PROFILE.allow_extended_horizons})")
    print("=" * 65)


def write_index(root: str) -> Dict:
    print(f"Scanning {root}...")
    MEMORY_DIR.mkdir(exist_ok=True)
    idx = scan_repo(root)
    INDEX_FILE.write_text(json.dumps(idx, indent=2))
    print(f"Indexed {idx['file_count']} files → {INDEX_FILE}")
    return idx


def main(argv: Optional[List[str]] = None) -> int:
    global MODEL
    import argparse

    parser = argparse.ArgumentParser(
        description="OSIRIS Brain — Sovereign Coding Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("query", nargs="?", help="One-shot query")
    parser.add_argument("--scan", metavar="DIR", help="Index a codebase")
    parser.add_argument("--ingest", metavar="FILE", help="Ingest chat log / notes")
    parser.add_argument("--audit", metavar="DIR", help="Security audit a git repo")
    parser.add_argument("--memory", action="store_true", help="Show memory and exit")
    parser.add_argument("--model", default=MODEL, help=f"Ollama model (default: {MODEL})")
    parser.add_argument("--workspace", default=".", help="Workspace root tool calls are confined to")
    parser.add_argument("--mode", default="edit",
                        help="osiris_cli mode; edit allows approved writes and commands")
    parser.add_argument("--sprint", action="store_true", help="Show sprint board and exit")
    parser.add_argument("--hardware", action="store_true", help="Report hardware substrate profile and exit")
    parser.add_argument("--benchmark", metavar="TARGET", nargs="?", const="ibm_torino", help="Run 11D-CRSM benchmark on target backend")
    parser.add_argument("--mutate", metavar="TARGET", nargs="?", const="ibm_torino", help="Trigger autonomous mutation loop on target backend")
    args = parser.parse_args(argv)

    MODEL = args.model

    if args.hardware:
        _print_hardware()
        return 0

    if args.benchmark:
        from osiris_edge_quantum_loop import execute_crsm_benchmark
        execute_crsm_benchmark(backend_name=args.benchmark)
        return 0

    if args.mutate:
        from osiris_edge_quantum_loop import trigger_dna_mutation
        trigger_dna_mutation(backend_name=args.mutate)
        return 0

    if args.memory:
        print(tool_recall("all"))
        return 0

    if args.sprint:
        print(tool_sprint_task("list"))
        return 0

    if args.scan:
        write_index(args.scan)
        return 0

    if args.ingest:
        print(ingest_text(args.ingest))
        return 0

    if args.audit:
        print(audit_repo(args.audit))
        return 0

    if args.query:
        return ask(args.query, model=args.model, workspace=args.workspace, mode=args.mode)

    return repl(model=args.model, workspace=args.workspace, mode=args.mode)


if __name__ == "__main__":
    sys.exit(main())
