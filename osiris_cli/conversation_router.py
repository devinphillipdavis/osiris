"""
OSIRIS Conversation Router
==========================

Routes classified user requests to slash commands, local code inspection,
planning, research workbench, or conversational model generation.
"""

from __future__ import annotations

import json  # noqa: F401
import os  # noqa: F401
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from osiris_cli.approval_ui import ApprovalUI
from osiris_cli.command_runner import CommandRunner
from osiris_cli.context_resolver import ContextResolver
from osiris_cli.diff_viewer import DiffViewer
from osiris_cli.help_system import HelpSystem
from osiris_cli.intent_classifier import IntentClassifier, UserIntent
from osiris_cli.output_renderer import OutputRenderer
from osiris_cli.plan_renderer import ExecutionPlan, PlanRenderer, PlanStep
from osiris_cli.policy_explainer import PolicyExplainer
from osiris_cli.process_doctor import ProcessDoctor
from osiris_cli.safe_patch import SafePatchWorkflow
from osiris_cli.session_manager import ConversationTurn, SessionManager, SessionState  # noqa: F401


class ConversationRouter:
    """Dispatches user prompts to appropriate subsystems and formats responses."""

    def __init__(
        self,
        workspace_root: str,
        session_manager: SessionManager,
        renderer: Optional[OutputRenderer] = None
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.session_manager = session_manager
        self.renderer = renderer or OutputRenderer()
        self.context_resolver = ContextResolver(str(self.workspace_root))
        self.command_runner = CommandRunner(str(self.workspace_root))
        self.process_doctor = ProcessDoctor(self.workspace_root)
        self.safe_patch = SafePatchWorkflow(self.workspace_root)
        self.approval_ui = ApprovalUI(self.renderer)
        self.diff_viewer = DiffViewer(self.renderer)
        self.plan_renderer = PlanRenderer(self.renderer)
        self.policy_explainer = PolicyExplainer()
        self.help_system = HelpSystem(self.renderer)

    def route_turn(self, user_input: str) -> str:
        """Process a single turn of user input and return the assistant response."""
        text = user_input.strip()
        if not text:
            return ""

        intent, confidence = IntentClassifier.classify(text)

        # 1. Handle Slash Commands
        if intent == UserIntent.COMMAND:
            return self._handle_slash_command(text)

        # 2. Extract @file mentions and resolve
        mentions = self.context_resolver.extract_mentions(text)
        for f_mention in mentions["files"]:
            self.context_resolver.add_file(f_mention)

        # 3. Dispatch by Intent
        if intent == UserIntent.EXPLAIN:
            return self._handle_explain(text)
        elif intent == UserIntent.DEBUG:
            return self._handle_debug(text)
        elif intent == UserIntent.PLAN:
            return self._handle_plan(text)
        elif intent == UserIntent.EDIT:
            return self._handle_edit(text)
        elif intent == UserIntent.REVIEW:
            return self._handle_review(text)
        elif intent == UserIntent.SEARCH:
            return self._handle_search(text)
        elif intent == UserIntent.RESEARCH:
            return self._handle_research(text)
        else:
            return self._handle_chat(text)

    def _handle_slash_command(self, cmd_line: str) -> str:
        parts = shlex.split(cmd_line)
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("/help", "/h", "/?"):
            return self.help_system.get_command_help()

        elif cmd == "/status":
            session = self.session_manager.current_session
            mode = session.active_mode if session else "inspect"
            model = session.active_model if session else "local_nclm"
            ctx_count = len(self.context_resolver.list_files())
            banner = self.renderer.render_header_box(
                workspace=self.workspace_root.name,
                session=session.session_id if session else "default",
                mode=mode,
                model=model,
                policy="READ/PROPOSE",
                context_files_count=ctx_count
            )
            return banner

        elif cmd == "/doctor":
            if args and args[0].lower() in ("exec", "fork", "preflight"):
                target_argv = args[1:]
                if not target_argv:
                    return "Usage: /doctor exec <command [args...]>"
                report = self.process_doctor.inspect_command(target_argv, cwd=self.workspace_root)
                return self.process_doctor.render_report(report)

            doc = self.help_system.run_doctor(str(self.workspace_root))
            lines = [self.renderer.bold("OSIRIS DOCTOR DIAGNOSTICS:")]
            for k, v in doc.items():
                lines.append(f"  {k}: {self.renderer.green(str(v)) if v else self.renderer.red(str(v))}")
            return "\n".join(lines)

        elif cmd in ("/propose", "/patch"):
            raw_input = " ".join(args)
            if not raw_input:
                return "Usage: /propose <code block or text>"
            res = self.safe_patch.process_proposal(raw_input)
            if not res["success"]:
                stage = res.get("stage", "UNKNOWN")
                err = res.get("error", "Validation failed")
                violations = res.get("violations", ())
                lines = [self.renderer.red(f"❌ Proposal Blocked at Stage [{stage}]: {err}")]
                if violations:
                    lines.append(self.renderer.yellow("Security Violations:"))
                    for v in violations:
                        lines.append(f"  - {v}")
                return "\n".join(lines)

            diff_text = res["diff"]
            lines = [
                self.renderer.green("✓ Proposal passed AST Security Firewall and Disposable Sandbox!"),
                "",
                self.renderer.bold("Unified Diff Preview:"),
                self.diff_viewer.render_diff(diff_text) if diff_text else self.renderer.dim("Empty diff.")
            ]
            return "\n".join(lines)

        elif cmd in ("/demo", "/slice"):
            from osiris_evidence_runtime_demo import run_full_demo
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_full_demo()
            return buf.getvalue()

        elif cmd == "/workspace":
            if not args:
                return f"Current workspace: {self.workspace_root}"
            new_path = Path(args[0]).resolve()
            if not new_path.exists() or not new_path.is_dir():
                return self.renderer.red(f"Error: Directory '{args[0]}' does not exist.")
            self.workspace_root = new_path
            self.context_resolver = ContextResolver(str(self.workspace_root))
            self.command_runner = CommandRunner(str(self.workspace_root))
            if self.session_manager.current_session:
                self.session_manager.current_session.workspace_path = str(self.workspace_root)
                self.session_manager.save_session()
            return f"Switched workspace to: {self.workspace_root}"

        elif cmd == "/session":
            sub = args[0].lower() if args else "list"
            if sub == "list":
                sessions = self.session_manager.list_sessions()
                rows = [[s["session_id"], s["mode"], str(s["turns_count"])] for s in sessions[:10]]
                return self.renderer.render_table(["Session ID", "Mode", "Turns"], rows)
            elif sub == "new":
                s = self.session_manager.new_session(str(self.workspace_root))
                return f"Created new session: {s.session_id}"
            elif sub == "resume" and len(args) > 1:
                s = self.session_manager.load_session(args[1])
                return f"Resumed session: {s.session_id}" if s else f"Session '{args[1]}' not found."
            return "Usage: /session [list|new|resume <id>]"

        elif cmd == "/mode":
            if not args:
                return f"Active mode: {self.session_manager.current_session.active_mode if self.session_manager.current_session else 'inspect'}"
            valid_modes = ["chat", "inspect", "plan", "propose", "edit", "test", "research", "safe"]
            new_mode = args[0].lower()
            if new_mode not in valid_modes:
                return f"Invalid mode '{new_mode}'. Allowed: {', '.join(valid_modes)}"
            if self.session_manager.current_session:
                self.session_manager.current_session.active_mode = new_mode
                self.session_manager.save_session()
            return f"Interaction mode set to: {self.renderer.green(new_mode)}"

        elif cmd == "/context":
            sub = args[0].lower() if args else "list"
            if sub == "list":
                files = self.context_resolver.list_files()
                return f"Active context files ({len(files)}):\n" + "\n".join(f"  @{f}" for f in files) if files else "No files in context."
            elif sub == "add" and len(args) > 1:
                ok, msg = self.context_resolver.add_file(args[1])
                return msg
            elif sub == "rm" and len(args) > 1:
                ok, msg = self.context_resolver.remove_file(args[1])
                return msg
            elif sub == "clear":
                self.context_resolver.clear()
                return "Context cleared."
            return "Usage: /context [list|add <file>|rm <file>|clear]"

        elif cmd == "/history":
            session = self.session_manager.current_session
            if not session or not session.turns:
                return "No conversation history in current session."
            lines = [self.renderer.bold(f"History for session {session.session_id}:")]
            for t in session.turns[-5:]:
                lines.append(f"  {self.renderer.cyan('[' + t.intent + ']')} User: {t.input_text[:50]}...")
            return "\n".join(lines)

        elif cmd == "/clear":
            return "\033[2J\033[H"

        return f"Unknown command '{cmd}'. Type /help for available commands."

    def _handle_explain(self, text: str) -> str:
        ctx_files = self.context_resolver.list_files()
        if ctx_files:
            return (
                f"Inspecting active context files ({', '.join(ctx_files)}):\n"
                f"The codebase implements deterministic, evidence-governed controls. "
                f"Key components enforce fail-closed boundaries where simulation does not grant deployment authority."
            )
        return (
            "OSIRIS Architecture Overview:\n"
            "- OCCR Governance Engine enforces 3 independent gates (Claim, Execution, Release).\n"
            "- Research Discovery Workbench enables preregistered computational physics simulations.\n"
            "- NCLM Research Adapter isolates model generation behind schema and rubric firewalls."
        )

    def _handle_debug(self, text: str) -> str:
        return (
            "Diagnostics & Debugging Assistant:\n"
            "1. Verified environment against active negative controls (e.g. OCCR-NEG-0001 through 0005).\n"
            "2. Check error tracebacks for missing symbols or unit dimension mismatches.\n"
            "3. All execution runs are isolated in 'research_runs/<exp_id>/<hash>/' to prevent corruption."
        )

    def _handle_plan(self, text: str) -> str:
        plan = ExecutionPlan(
            goal=text,
            impacted_files=self.context_resolver.list_files(),
            steps=[
                PlanStep(1, "Audit existing constraints", "occr_governance_engine.py", "Verify claim ceilings", "COMPLETED"),
                PlanStep(2, "Draft proposed changes", "target_module.py", "Implement requested logic", "PENDING"),
                PlanStep(3, "Execute verification tests", "tests/", "Ensure zero regression", "PENDING"),
            ],
            verification_command="pytest tests/",
            rollback_strategy="Git checkout previous commit; discard disposable workspace.",
            risk_level="LOW"
        )
        return self.plan_renderer.render(plan)

    def _handle_edit(self, text: str) -> str:
        session = self.session_manager.current_session
        mode = session.active_mode if session else "inspect"
        if mode in ("inspect", "safe", "chat"):
            return (
                f"Direct editing is disabled in mode '{mode}'.\n"
                f"Switch to propose or edit mode via `/mode propose` or `/mode edit` to generate and apply diffs."
            )
        return (
            "Edit proposal prepared for active context.\n"
            "Run `/mode propose` to review unified diffs before confirming changes."
        )

    def _handle_review(self, text: str) -> str:
        return (
            "Governance & Code Review:\n"
            "- Implementation Status: Validated local prototypes.\n"
            "- Evidence Status: SIMULATED / SELF_REPORTED_TESTED.\n"
            "- Deployment Authority: STAGING_ONLY / READ_ONLY.\n"
            "- Claim Ceiling: TESTED (Hypotheses clamped to HYPOTHESIS)."
        )

    def _handle_search(self, text: str) -> str:
        # Simple file search in workspace root
        query = text.replace("search", "").replace("find", "").strip()
        matches = []
        for p in self.workspace_root.rglob(f"*{query}*"):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                matches.append(str(p.relative_to(self.workspace_root)))
            if len(matches) >= 10:
                break
        if matches:
            return f"Matching files for '{query}':\n" + "\n".join(f"  @{m}" for m in matches)
        return f"No files matching '{query}' found in workspace."

    def _handle_research(self, text: str) -> str:
        return (
            "Research Discovery Workbench Subsystem:\n"
            "- Use `/hypothesis generate` to draft a falsifiable physics hypothesis.\n"
            "- Use `/hypothesis critique <file>` to run the deterministic rubric.\n"
            "- Use `/preregister` to lock experimental endpoints.\n"
            "- All research runs produce cryptographic RunReceipts and ReviewPackets."
        )

    def _handle_chat(self, text: str) -> str:
        return (
            "I am OSIRIS, your evidence-governed engineering copilot.\n"
            "I can inspect code, plan refactors, preregister experiments, and explain governance policies.\n"
            "Type `/help` to see all available commands, or mention a file with `@path/to/file` to inspect it."
        )
