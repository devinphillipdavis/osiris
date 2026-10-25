"""LocalBrainAdapter — the osiris_brain Ollama tool loop, governed per tool call.

Wraps the nine ``osiris_brain.tool_*`` functions. Every call the model makes is
turned into an ``ActionProposal`` and must win an ``ExecutionGrant`` from the
``CapabilityGovernor`` (verified again immediately before execution) or it does
not run. Workspace tools are path-confined to the workspace root by the
governor. Memory and sprint tools take no path argument and only touch
``osiris_brain.MEMORY_DIR``; they are confined by construction, and a second
governor rooted there enforces capability scope, nonce and request binding.

The model loop runs inline inside ``run()`` (blocking), because each tool result
feeds the next model step. Grants are therefore issued inline and recorded in
``AgentResult.usage["governance"]``; ``AgentResult.proposals`` is left empty so
``AgentGateway.process`` does not re-evaluate already-consumed nonces.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..contracts import AgentResult, AuthorizedAgentRequest
from ..execution import Approver, GovernanceDecision, GovernedExecutor
from ..governor import CapabilityGovernor, GovernanceViolation

#: ``chat_fn(messages, tools=..., model=...) -> dict`` with Ollama /api/chat shape.
ChatFn = Callable[..., Dict[str, Any]]

# tool -> (capability, root, path argument or None)
_TOOL_POLICY: Mapping[str, tuple] = {
    "read_file": ("READ_ONLY_ANALYSIS", "workspace", "path"),
    "list_dir": ("READ_ONLY_ANALYSIS", "workspace", "path"),
    "grep_code": ("READ_ONLY_ANALYSIS", "workspace", "path"),
    "write_file": ("WORKSPACE_WRITE", "workspace", "path"),
    "run_bash": ("SUBPROCESS_EXEC", "workspace", "cwd"),
    "recall": ("READ_ONLY_ANALYSIS", "state", None),
    "search_index": ("READ_ONLY_ANALYSIS", "state", None),
    "remember": ("SESSION_STATE_WRITE", "state", None),
    "sprint_task": ("SESSION_STATE_WRITE", "state", None),
}

_MAX_TOOL_RESULT_CHARS = 6000
_MAX_HISTORY = 30


def _brain():
    import osiris_brain  # root module; imported lazily so the gateway stays light
    return osiris_brain


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class LocalBrainAdapter:
    """AgentAdapter over a local Ollama model and the governed brain tool set."""

    PROVIDER = "ollama_local_brain"

    def __init__(
        self,
        workspace_root: Path | str,
        *,
        model: Optional[str] = None,
        approver: Optional[Approver] = None,
        governor: Optional[CapabilityGovernor] = None,
        chat_fn: Optional[ChatFn] = None,
        max_iterations: int = 12,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.model = model
        self.max_iterations = max_iterations
        self._chat_fn = chat_fn
        self.governor = governor or CapabilityGovernor(self.workspace_root)
        self._approver = approver
        self._state_governor: Optional[CapabilityGovernor] = None
        self._history: List[Dict[str, Any]] = []

    # ── AgentAdapter protocol ────────────────────────────────────────────────
    def capabilities(self) -> frozenset[str]:
        return frozenset({cap for cap, _, _ in _TOOL_POLICY.values()} | {"RETURN_STRUCTURED_PROPOSAL"})

    async def run(self, request: AuthorizedAgentRequest) -> AgentResult:
        return self.run_sync(request)

    # ── Session state ────────────────────────────────────────────────────────
    @property
    def state_dir(self) -> Path:
        """The only directory the memory and sprint tools write to."""
        return Path(_brain().MEMORY_DIR).expanduser().resolve()

    def reset(self) -> None:
        """Drop conversation context; stored memory and the sprint board persist."""
        self._history = []

    def set_model(self, model: str) -> None:
        self.model = model

    def refresh_system_prompt(self) -> None:
        """Rebuild the system prompt in place (after /scan or /ingest) keeping the conversation."""
        if self._history:
            self._history[0] = {"role": "system", "content": self._system_prompt()}

    # ── Model loop ───────────────────────────────────────────────────────────
    def run_sync(self, request: AuthorizedAgentRequest) -> AgentResult:
        brain = _brain()
        executor = self._executor()
        if not self._history:
            self._history = [{"role": "system", "content": self._system_prompt()}]
        self._history.append({"role": "user", "content": request.task})

        tokens = 0
        tool_calls_made = 0
        status, output, error = "MAX_ITERATIONS", None, "model did not finish within the iteration budget"

        for _ in range(self.max_iterations):
            resp = self._chat(self._history, tools=brain.TOOLS)
            tokens += int(resp.get("prompt_eval_count", 0) or 0) + int(resp.get("eval_count", 0) or 0)
            if "error" in resp:
                self._history.pop()  # do not keep an unanswered user turn
                status, output, error = "ERROR", None, str(resp["error"])
                break

            msg = resp.get("message", {}) or {}
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                output = msg.get("content", "") or "(no response)"
                self._history.append({"role": "assistant", "content": output})
                status, error = "SUCCESS", None
                break

            self._history.append({
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                fn = call.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {}) or {}
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except (ValueError, TypeError):
                    args = None
                tool_calls_made += 1
                if args is None:
                    content = f"ERROR: arguments for {name} are not a JSON object"
                else:
                    content = self.dispatch(request, name, args, executor=executor)
                if len(content) > _MAX_TOOL_RESULT_CHARS:
                    content = (content[:3000]
                               + f"\n...[truncated — {len(content) - 3000} chars omitted]...\n"
                               + content[-1500:])
                self._history.append({"role": "tool", "content": content, "name": name})

        if len(self._history) > _MAX_HISTORY + 2:
            self._history = [self._history[0]] + self._history[-_MAX_HISTORY:]

        ledger = [d.to_dict() for d in executor.ledger]
        return AgentResult(
            request_id=request.request_id,
            status=status,
            provider=self.PROVIDER,
            proposals=(),
            usage={
                "tokens": tokens,
                "cost_usd": 0.0,
                "tool_calls": tool_calls_made,
                "granted": sum(1 for d in executor.ledger if d.granted),
                "denied": sum(1 for d in executor.ledger if not d.granted),
                "governance": ledger,
            },
            error=error,
            output=output,
        )

    # ── Governed tool dispatch ───────────────────────────────────────────────
    def dispatch(
        self,
        request: AuthorizedAgentRequest,
        name: str,
        args: Dict[str, Any],
        executor: Optional[GovernedExecutor] = None,
    ) -> str:
        """Authorize and run one tool call; always returns text for the model."""
        brain = _brain()
        policy = _TOOL_POLICY.get(name)
        fn = brain.TOOL_MAP.get(name)
        if policy is None or fn is None:
            return f"Unknown tool: {name}"
        capability, root_kind, path_key = policy
        if name == "sprint_task" and args.get("action") == "list":
            capability = "READ_ONLY_ANALYSIS"

        executor = executor or self._executor()
        if root_kind == "state":
            self.state_dir.mkdir(parents=True, exist_ok=True)
            governor = self._state_governor_for()
            locator = str(self.state_dir)
            gov_executor = GovernedExecutor(
                governor=governor, proposer_id=executor.proposer_id,
                provider=executor.provider, approver=None, model=self.model,
                ledger=executor.ledger,
            )
        else:
            governor = self.governor
            raw = args.get(path_key) or "."
            target = Path(str(raw)).expanduser()
            if not target.is_absolute():
                target = self.workspace_root / target
            locator = str(target.resolve())
            # Execute against the same resolved path the governor confines.
            args = {**args, path_key: locator}
            gov_executor = executor

        arguments, content_digest, description = self._describe(name, args, locator)
        decision, proposal, grant = gov_executor.authorize(
            request, capability, locator, arguments, description,
            content_digest=content_digest,
        )
        if not decision.granted:
            return f"DENIED by CapabilityGovernor: {decision.reason}"

        try:
            governor.verify_grant(grant, proposal)
            if name == "write_file" and _sha256(str(args.get("content", ""))) != content_digest:
                raise GovernanceViolation("write content differs from the approved content digest")
        except GovernanceViolation as exc:
            gov_executor.ledger.append(GovernanceDecision(
                capability, locator, "DENIED", proposal.proposal_digest, reason=str(exc)))
            return f"DENIED by CapabilityGovernor: {exc}"

        try:
            return fn(**args)
        except TypeError as exc:
            return f"Bad args for {name}: {exc}"
        except Exception as exc:
            return f"Error in {name}: {exc}"

    # ── Internals ────────────────────────────────────────────────────────────
    def _executor(self) -> GovernedExecutor:
        return GovernedExecutor(
            governor=self.governor,
            proposer_id="osiris_brain",
            provider=self.PROVIDER,
            approver=self._approver,
            model=self.model,
        )

    def _state_governor_for(self) -> CapabilityGovernor:
        if self._state_governor is None or self._state_governor.approved_root != self.state_dir:
            self._state_governor = CapabilityGovernor(self.state_dir)
        return self._state_governor

    @staticmethod
    def _describe(name: str, args: Dict[str, Any], locator: str):
        """Proposal arguments (digest-bound, never raw file bodies) and a human summary."""
        if name == "write_file":
            content = str(args.get("content", ""))
            digest = _sha256(content)
            mode = args.get("mode", "overwrite")
            arguments = {"path": locator, "mode": mode, "content_sha256": digest,
                         "content_chars": len(content)}
            return arguments, digest, f"write_file → {locator} ({len(content):,} chars, {mode})"
        if name == "run_bash":
            command = str(args.get("command", ""))
            arguments = {"command": command, "cwd": locator, "timeout": args.get("timeout")}
            return arguments, None, f"run_bash → `{command}` in {locator}"
        summary = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in sorted(args.items()))
        return {"tool": name, **{k: str(v)[:500] for k, v in args.items()}}, None, f"{name}({summary})"

    def _chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        if self._chat_fn is not None:
            return self._chat_fn(messages, tools=tools, model=self.model)
        return _brain().ollama_chat(messages, tools=tools, model=self.model)

    def _system_prompt(self) -> str:
        prompt = _brain().build_system_prompt()
        return prompt + f"\n\nActive workspace (tool calls are confined here): {self.workspace_root}"
