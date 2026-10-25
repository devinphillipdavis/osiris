"""LocalBrainAdapter: the osiris_brain tool loop, governed per tool call.

The model is always scripted here (no Ollama). Each test drives one or more tool
calls and asserts what the CapabilityGovernor allowed to reach the filesystem.
"""

import asyncio
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import osiris_brain
from osiris.agents.gateway import (
    AgentGateway,
    AuthorizedAgentRequest,
    CapabilityGovernor,
    HumanApproval,
    ModelRouter,
    build_proposal,
)
from osiris.agents.gateway.adapters import LocalBrainAdapter

READ_ONLY = frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL", "SESSION_STATE_WRITE"})
ELEVATED = READ_ONLY | {"WORKSPACE_WRITE", "SUBPROCESS_EXEC"}


class ScriptedChat:
    """Replays tool calls, then a final answer. Records what the model was shown."""

    def __init__(self, *tool_calls, answer="done"):
        self._steps = [
            {"message": {"content": "", "tool_calls": [
                {"function": {"name": name, "arguments": args}}
            ]}}
            for name, args in tool_calls
        ] + [{"message": {"content": answer}, "eval_count": 7, "prompt_eval_count": 5}]
        self.seen = []

    def __call__(self, messages, tools=None, model=None):
        self.seen.append([dict(m) for m in messages])
        return self._steps.pop(0) if self._steps else {"message": {"content": "done"}}

    def tool_results(self):
        last = self.seen[-1]
        return [m["content"] for m in last if m["role"] == "tool"]


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "notes.txt").write_text("phase-conjugate notes\n")
    (tmp_path / "outside.txt").write_text("SECRET-OUTSIDE\n")
    return ws


@pytest.fixture(autouse=True)
def brain_state(tmp_path, monkeypatch):
    state = tmp_path / "brain_state"
    monkeypatch.setattr(osiris_brain, "MEMORY_DIR", state)
    monkeypatch.setattr(osiris_brain, "MEMORY_FILE", state / "brain_memory.json")
    monkeypatch.setattr(osiris_brain, "INDEX_FILE", state / "repo_index.json")
    monkeypatch.setattr(osiris_brain, "SPRINT_FILE", state / "sprint.json")
    return state


def _request(caps=READ_ONLY, request_id="req-brain-1"):
    return AuthorizedAgentRequest(
        request_id=request_id,
        task="inspect the workspace",
        allowed_capabilities=frozenset(caps),
        data_classification="LOCAL_WORKSPACE",
        authority_scope="test",
    )


def _approve_all(proposal, description):
    return HumanApproval.for_proposal(proposal, approver_id="tester", channel="test")


def _run(adapter, request):
    return asyncio.run(adapter.run(request))


def test_adapter_satisfies_agent_adapter_protocol(workspace):
    adapter = LocalBrainAdapter(workspace, chat_fn=ScriptedChat())
    caps = adapter.capabilities()
    assert {"READ_ONLY_ANALYSIS", "WORKSPACE_WRITE", "SUBPROCESS_EXEC"} <= caps
    result = _run(adapter, _request())
    assert result.status == "SUCCESS"
    assert result.output == "done"
    assert result.proposals == ()
    assert result.usage["tokens"] == 12


def test_read_inside_workspace_is_granted(workspace):
    chat = ScriptedChat(("read_file", {"path": "notes.txt"}))
    result = _run(LocalBrainAdapter(workspace, chat_fn=chat), _request())
    assert "phase-conjugate notes" in chat.tool_results()[0]
    assert result.usage["granted"] == 1 and result.usage["denied"] == 0
    assert result.usage["governance"][0]["grant_id"].startswith("grant_")


@pytest.mark.parametrize("path", ["../outside.txt", "OUTSIDE_ABS"])
def test_read_outside_workspace_is_denied(workspace, path):
    if path == "OUTSIDE_ABS":
        path = str(workspace.parent / "outside.txt")
    chat = ScriptedChat(("read_file", {"path": path}))
    result = _run(LocalBrainAdapter(workspace, chat_fn=chat), _request())
    shown = chat.tool_results()[0]
    assert shown.startswith("DENIED by CapabilityGovernor")
    assert "SECRET-OUTSIDE" not in shown
    assert result.usage["denied"] == 1


def test_symlink_escape_is_denied(workspace):
    (workspace / "link.txt").symlink_to(workspace.parent / "outside.txt")
    chat = ScriptedChat(("read_file", {"path": "link.txt"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat), _request())
    assert "SECRET-OUTSIDE" not in chat.tool_results()[0]
    assert "Path traversal" in chat.tool_results()[0]


def test_write_without_approval_is_denied_and_nothing_is_written(workspace):
    chat = ScriptedChat(("write_file", {"path": "new.py", "content": "x = 1\n"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat), _request(ELEVATED))
    assert "requires a human approval" in chat.tool_results()[0]
    assert not (workspace / "new.py").exists()


def test_out_of_scope_write_never_prompts_a_human(workspace):
    prompts = []

    def approver(proposal, description):
        prompts.append(description)
        return _approve_all(proposal, description)

    chat = ScriptedChat(("write_file", {"path": "new.py", "content": "x = 1\n"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat, approver=approver), _request(READ_ONLY))
    assert prompts == []
    assert "not granted in parent request" in chat.tool_results()[0]
    assert not (workspace / "new.py").exists()


def test_write_with_bound_approval_is_applied_under_a_grant(workspace):
    seen = []

    def approver(proposal, description):
        seen.append((proposal.capability, description))
        return _approve_all(proposal, description)

    chat = ScriptedChat(("write_file", {"path": "pkg/new.py", "content": "x = 1\n"}))
    result = _run(LocalBrainAdapter(workspace, chat_fn=chat, approver=approver), _request(ELEVATED))
    assert (workspace / "pkg" / "new.py").read_text() == "x = 1\n"
    assert seen and seen[0][0] == "WORKSPACE_WRITE"
    decision = result.usage["governance"][0]
    assert decision["decision"] == "GRANTED"
    assert decision["approval_id"].startswith("approval_")


def test_approval_bound_to_another_proposal_is_rejected(workspace):
    def replaying_approver(proposal, description):
        other = build_proposal(
            request=_request(ELEVATED), capability="WORKSPACE_WRITE", locator="other.py",
            arguments={}, proposer_id="x", provider="x",
        )
        return HumanApproval.for_proposal(other, approver_id="tester")

    chat = ScriptedChat(("write_file", {"path": "new.py", "content": "x = 1\n"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat, approver=replaying_approver), _request(ELEVATED))
    assert "different proposal digest" in chat.tool_results()[0]
    assert not (workspace / "new.py").exists()


def test_run_bash_executes_a_single_program_without_a_shell(workspace):
    command = f"{sys.executable} -c \"print('GOVERNED_OK')\""
    chat = ScriptedChat(("run_bash", {"command": command}), ("run_bash", {"command": "ls | head"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat, approver=_approve_all), _request(ELEVATED))
    ok, piped = chat.tool_results()
    assert "GOVERNED_OK" in ok
    assert piped.startswith("BLOCKED: shell syntax")


def test_run_bash_cwd_outside_workspace_is_denied(workspace):
    chat = ScriptedChat(("run_bash", {"command": "ls", "cwd": str(workspace.parent)}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat, approver=_approve_all), _request(ELEVATED))
    assert "Path traversal" in chat.tool_results()[0]


def test_grep_pattern_cannot_execute_shell(workspace):
    marker = workspace / "PWNED"
    pattern = f"it's $(touch {marker})"
    chat = ScriptedChat(("grep_code", {"pattern": pattern, "path": "."}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat), _request())
    assert not marker.exists()


def test_session_state_tools_write_only_brain_state(workspace, brain_state):
    chat = ScriptedChat(("remember", {"key": "lock", "value": "51.843"}),
                        ("recall", {"key": "lock"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat), _request())
    assert chat.tool_results()[1] == "51.843"
    assert (brain_state / "brain_memory.json").exists()
    assert sorted(p.name for p in workspace.iterdir()) == ["notes.txt"]


def test_session_state_write_requires_request_scope(workspace, brain_state):
    chat = ScriptedChat(("remember", {"key": "k", "value": "v"}))
    _run(LocalBrainAdapter(workspace, chat_fn=chat), _request({"READ_ONLY_ANALYSIS"}))
    assert chat.tool_results()[0].startswith("DENIED")
    assert not (brain_state / "brain_memory.json").exists()


def test_unknown_tool_and_bad_arguments_are_reported(workspace):
    chat = ScriptedChat(("delete_everything", {}), ("read_file", "{not json"))
    _run(LocalBrainAdapter(workspace, chat_fn=chat), _request())
    unknown, bad = chat.tool_results()
    assert unknown == "Unknown tool: delete_everything"
    assert "not a JSON object" in bad


def test_model_error_is_surfaced_and_turn_not_kept(workspace):
    adapter = LocalBrainAdapter(workspace, chat_fn=lambda m, tools=None, model=None: {"error": "ollama down"})
    result = _run(adapter, _request())
    assert result.status == "ERROR" and result.error == "ollama down"
    assert [m["role"] for m in adapter._history] == ["system"]


def test_conversation_persists_across_turns_until_reset(workspace):
    chat = ScriptedChat(answer="first")
    adapter = LocalBrainAdapter(workspace, chat_fn=chat)
    _run(adapter, _request(request_id="r1"))
    adapter._chat_fn = ScriptedChat(answer="second")
    _run(adapter, _request(request_id="r2"))
    roles = [m["role"] for m in adapter._history]
    assert roles == ["system", "user", "assistant", "user", "assistant"]
    adapter.reset()
    assert adapter._history == []


def test_gateway_routes_standard_requests_to_local_brain(workspace):
    adapter = LocalBrainAdapter(workspace, chat_fn=ScriptedChat(("read_file", {"path": "notes.txt"})))
    gateway = AgentGateway(ModelRouter({"local_brain": adapter}), adapter.governor)
    response = asyncio.run(gateway.process(_request()))
    assert response.result.provider == LocalBrainAdapter.PROVIDER
    assert response.result.output == "done"
    assert response.grants == ()  # grants were issued inline and are in usage["governance"]


def test_restricted_data_still_routes_to_replay_only(workspace):
    from osiris.agents.gateway import RoutingError

    router = ModelRouter({"local_brain": LocalBrainAdapter(workspace, chat_fn=ScriptedChat())})
    restricted = AuthorizedAgentRequest(
        request_id="r", task="t", allowed_capabilities=READ_ONLY,
        data_classification="RESTRICTED", authority_scope="test",
    )
    with pytest.raises(RoutingError):
        router.route(restricted)


def test_governor_tiers_gate_elevated_capabilities():
    assert not CapabilityGovernor.requires_human_approval("READ_ONLY_ANALYSIS")
    assert not CapabilityGovernor.requires_human_approval("SESSION_STATE_WRITE")
    assert CapabilityGovernor.requires_human_approval("WORKSPACE_WRITE")
    assert CapabilityGovernor.requires_human_approval("SUBPROCESS_EXEC")
    assert CapabilityGovernor.requires_human_approval("RUN_ARBITRARY_COMMAND")
