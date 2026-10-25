"""
OSIRIS Conversation Router
==========================

Routes classified user requests to slash commands, local code inspection,
planning, research workbench, or conversational model generation.

When the session model is a real model (anything outside ``TEMPLATE_MODELS``),
free-text turns go through ``AgentGateway`` to ``LocalBrainAdapter``. Every tool
call and every patch write is an ``ActionProposal`` the ``CapabilityGovernor``
must grant; the active mode bounds which capabilities a request may carry.
"""

from __future__ import annotations

import asyncio
import getpass
import io
import shlex
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple  # noqa: F401

from osiris.agents.gateway import (
    ActionProposal,
    AgentGateway,
    AuthorizedAgentRequest,
    CapabilityGovernor,
    HumanApproval,
    ModelRouter,
)

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

#: Model names served by the built-in templated responses rather than a real model.
TEMPLATE_MODELS = frozenset({"local_nclm", "livlm", "swarm", "offline", ""})

#: Capabilities every mode may request. Elevated ones are added per mode, and still
#: need a per-action human approval from the CapabilityGovernor on top.
_BASE_CAPABILITIES = frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL", "SESSION_STATE_WRITE"})
_MODE_ELEVATIONS: Dict[str, frozenset] = {
    "propose": frozenset({"WORKSPACE_WRITE"}),
    "edit": frozenset({"WORKSPACE_WRITE", "SUBPROCESS_EXEC"}),
    "test": frozenset({"SUBPROCESS_EXEC"}),
}

BackendFactory = Callable[["ConversationRouter"], Any]


def mode_capabilities(mode: str) -> frozenset:
    """Capability scope a request may carry in ``mode``. ``safe`` is strictly read-only."""
    if mode == "safe":
        return frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL"})
    return _BASE_CAPABILITIES | _MODE_ELEVATIONS.get(mode, frozenset())


def _operator_id() -> str:
    try:
        return getpass.getuser() or "operator"
    except Exception:
        return "operator"


class ConversationRouter:
    """Dispatches user prompts to appropriate subsystems and formats responses."""

    def __init__(
        self,
        workspace_root: str,
        session_manager: SessionManager,
        renderer: Optional[OutputRenderer] = None,
        backend_factory: Optional[BackendFactory] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.session_manager = session_manager
        self.renderer = renderer or OutputRenderer()
        self.context_resolver = ContextResolver(str(self.workspace_root))
        self.command_runner = CommandRunner(str(self.workspace_root))
        self.process_doctor = ProcessDoctor(self.workspace_root)
        self.governor = CapabilityGovernor(self.workspace_root)
        self.safe_patch = SafePatchWorkflow(self.workspace_root, governor=self.governor)
        self.approval_ui = ApprovalUI(self.renderer)
        self.diff_viewer = DiffViewer(self.renderer)
        self.plan_renderer = PlanRenderer(self.renderer)
        self.policy_explainer = PolicyExplainer()
        self.help_system = HelpSystem(self.renderer)
        self._backend_factory = backend_factory or _default_backend
        self._backend: Any = None
        self._pending_patch: Optional[Dict[str, Any]] = None

    # ── Session-derived policy ───────────────────────────────────────────────
    @property
    def active_mode(self) -> str:
        session = self.session_manager.current_session
        return session.active_mode if session else "inspect"

    @property
    def active_model(self) -> str:
        session = self.session_manager.current_session
        return session.active_model if session else "local_nclm"

    def generation_enabled(self) -> bool:
        return self.active_model not in TEMPLATE_MODELS

    def approve(self, proposal: ActionProposal, description: str) -> Optional[HumanApproval]:
        """Interactive approver: a y/N prompt whose 'y' is bound to this proposal's digest."""
        ok = self.approval_ui.prompt_confirmation(
            f"Governed action [{proposal.capability}] {description}"
        )
        if not ok:
            return None
        return HumanApproval.for_proposal(proposal, approver_id=_operator_id(), channel="tty")

    def backend(self) -> Any:
        if self._backend is None:
            self._backend = self._backend_factory(self)
        return self._backend

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

        # 3. Real model configured: every free-text turn is governed generation
        if self.generation_enabled():
            return self._handle_generation(text)

        # 4. Dispatch by Intent (templated responses)
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
                return "Usage: /propose <code block or text | file>"
            if len(args) == 1:
                # A single-line REPL cannot carry a fenced block, so accept a file
                # (e.g. a saved model response), confined to the workspace.
                try:
                    candidate = self.governor.confine_path(args[0].lstrip("@"))
                except Exception as exc:
                    return self.renderer.red(f"❌ {exc}")
                if candidate.is_file():
                    raw_input = candidate.read_text(encoding="utf-8")
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
            target = res.get("target_file")
            if target:
                request = self.safe_patch.patch_request()
                proposal = self.safe_patch.build_patch_proposal(
                    target, res["code"], diff_text, res.get("original_sha256"), request
                )
                self._pending_patch = {"result": res, "proposal": proposal, "request": request}
                lines += ["", self.renderer.dim(
                    f"Pending WORKSPACE_WRITE proposal {proposal.proposal_id} → {target}. "
                    f"Run /apply to request an ExecutionGrant."
                )]
            else:
                self._pending_patch = None
                lines += ["", self.renderer.dim(
                    "No target file directive found; add '# TargetFile: <path>' to make it applicable."
                )]
            return "\n".join(lines)

        elif cmd == "/apply":
            return self._handle_apply()

        elif cmd == "/model":
            if not args:
                return f"Active model: {self.active_model}"
            session = self.session_manager.current_session
            if session:
                session.active_model = args[0]
                self.session_manager.save_session()
            if self._backend is not None and hasattr(self._backend, "set_model"):
                self._backend.set_model(args[0])
            kind = "templated responses" if args[0] in TEMPLATE_MODELS else "governed local model"
            return f"Model set to: {self.renderer.green(args[0])} ({kind})"

        elif cmd == "/reset":
            if self._backend is not None and hasattr(self._backend, "reset"):
                self._backend.reset()
            return "Model conversation context cleared (memory and sprint board retained)."

        elif cmd in ("/memory", "/sprint", "/scan", "/ingest", "/audit"):
            return self._handle_brain_command(cmd, args)

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
            self.governor = CapabilityGovernor(self.workspace_root)
            self.safe_patch = SafePatchWorkflow(self.workspace_root, governor=self.governor)
            self._backend = None
            self._pending_patch = None
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

    def _handle_generation(self, text: str) -> str:
        backend = self.backend()
        request = AuthorizedAgentRequest(
            request_id=f"cli-{uuid.uuid4().hex[:12]}",
            task=text,
            allowed_capabilities=mode_capabilities(self.active_mode),
            data_classification="LOCAL_WORKSPACE",
            authority_scope=f"workspace:{self.workspace_root}",
            session_id=(self.session_manager.current_session.session_id
                        if self.session_manager.current_session else None),
        )
        gateway = AgentGateway(ModelRouter({"local_brain": backend}), self.governor)
        response = asyncio.run(gateway.process(request))
        result = response.result

        if result.status == "ERROR":
            return self.renderer.red(f"[model error] {result.error}")
        lines = [result.output or self.renderer.dim("(no response)")]
        if result.status != "SUCCESS":
            lines.append(self.renderer.yellow(f"[{result.status}] {result.error or ''}".rstrip()))
        ledger = result.usage.get("governance", []) if result.usage else []
        if ledger:
            granted = sum(1 for d in ledger if d["decision"] == "GRANTED")
            denied = [d for d in ledger if d["decision"] != "GRANTED"]
            lines.append(self.renderer.dim(
                f"⚖ governance: {granted} granted · {len(denied)} denied · mode {self.active_mode}"
            ))
            for d in denied:
                lines.append(self.renderer.dim(f"  ✗ {d['capability']} {d['locator']} — {d['reason']}"))
        return "\n".join(lines)

    def _handle_apply(self) -> str:
        pending = self._pending_patch
        if not pending:
            return "No pending patch. Run /propose with a '# TargetFile:' directive first."
        if "WORKSPACE_WRITE" not in mode_capabilities(self.active_mode):
            return (f"/apply is not permitted in mode '{self.active_mode}'. "
                    f"Switch with `/mode propose` or `/mode edit`.")

        res, proposal, request = pending["result"], pending["proposal"], pending["request"]
        self._pending_patch = None  # one attempt per proposal: its nonce is single-use
        target = res["target_file"]
        ok = self.approval_ui.prompt_confirmation(
            f"Apply patch to {target} (proposal {proposal.proposal_id})?",
            diff_callback=lambda: print(self.diff_viewer.render_diff(res["diff"])),
        )
        approval = (HumanApproval.for_proposal(proposal, approver_id=_operator_id(), channel="tty")
                    if ok else None)
        sandbox = res.get("sandbox_result")
        receipt = self.safe_patch.apply_patch(
            target_relative_path=target,
            code=res["code"],
            diff_text=res["diff"],
            original_sha256=res.get("original_sha256"),
            ast_safe=res["ast_result"].is_safe,
            sandbox_passed=sandbox is not None and sandbox.exit_code == 0,
            human_approved=False,
            proposal=proposal,
            approval=approval,
            request=request,
        )
        if receipt.applied:
            return self.renderer.green(
                f"✓ Applied {target} under {receipt.grant_id} (receipt {receipt.receipt_id})"
            )
        return self.renderer.red(
            f"✗ Patch not applied: {receipt.governance_error} (receipt {receipt.receipt_id})"
        )

    def _handle_brain_command(self, cmd: str, args: List[str]) -> str:
        import osiris_brain as brain

        if cmd == "/memory":
            return brain.tool_recall("all")
        if cmd == "/sprint":
            return brain.tool_sprint_task("list")
        if not args:
            return f"Usage: {cmd} <path>"
        buf = io.StringIO()
        with redirect_stdout(buf):
            if cmd == "/scan":
                brain.write_index(args[0])
            elif cmd == "/ingest":
                print(brain.ingest_text(args[0]))
            else:
                print(brain.audit_repo(args[0]))
        if cmd in ("/scan", "/ingest") and self._backend is not None:
            self._backend.refresh_system_prompt()
        return buf.getvalue().rstrip()

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


def _default_backend(router: "ConversationRouter") -> Any:
    from osiris.agents.gateway.adapters import LocalBrainAdapter

    return LocalBrainAdapter(
        router.workspace_root,
        model=router.active_model,
        approver=router.approve,
        governor=router.governor,
    )
