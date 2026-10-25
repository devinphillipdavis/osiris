"""Plain-text tool-call fallback (qwen2.5-coder style), always governed."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import osiris_brain
from osiris.agents.gateway import AuthorizedAgentRequest, HumanApproval
from osiris.agents.gateway.adapters import LocalBrainAdapter
from osiris.agents.gateway.adapters.local_brain import parse_text_tool_calls

TOOLS = osiris_brain.TOOL_MAP
READ_ONLY = frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL", "SESSION_STATE_WRITE"})
ELEVATED = READ_ONLY | {"WORKSPACE_WRITE", "SUBPROCESS_EXEC"}

#: Verbatim shape of the live qwen2.5-coder:7b reply: one valid call, one invalid.
LIVE_REPLY = (
    '{"name": "read_file", "arguments": {"path": "notes.txt"}}\n\n'
    "After reading the contents of `notes.txt`, I will now write its value.\n\n"
    '{"name": "write_file", "arguments": {"path": "out.txt", "content": <read_content>, '
    '"mode": "overwrite"}}'
)


def _names(calls):
    return [c["function"]["name"] for c in calls]


# ── Parser ─────────────────────────────────────────────────────────────────────

def test_bare_name_arguments_object():
    calls = parse_text_tool_calls('{"name": "read_file", "arguments": {"path": "a.py"}}', TOOLS)
    assert calls == [{"function": {"name": "read_file", "arguments": {"path": "a.py"}}}]


def test_tool_kwargs_object():
    calls = parse_text_tool_calls('Sure: {"tool": "list_dir", "kwargs": {"path": "."}}', TOOLS)
    assert calls == [{"function": {"name": "list_dir", "arguments": {"path": "."}}}]


def test_fenced_json_block():
    text = 'I will search.\n```json\n{"name": "grep_code", "arguments": {"pattern": "x", "path": "."}}\n```\n'
    assert _names(parse_text_tool_calls(text, TOOLS)) == ["grep_code"]


def test_arguments_given_as_json_string():
    payload = json.dumps({"name": "recall", "arguments": json.dumps({"key": "all"})})
    calls = parse_text_tool_calls(payload, TOOLS)
    assert calls[0]["function"]["arguments"] == {"key": "all"}


def test_live_reply_keeps_the_valid_call_and_drops_the_malformed_one():
    calls = parse_text_tool_calls(LIVE_REPLY, TOOLS)
    assert _names(calls) == ["read_file"]


def test_array_of_calls_yields_each_call():
    text = '[{"name": "read_file", "arguments": {"path": "a"}}, {"tool": "recall", "kwargs": {"key": "all"}}]'
    assert _names(parse_text_tool_calls(text, TOOLS)) == ["read_file", "recall"]


def test_multiple_calls_preserve_order_without_double_counting_fences():
    text = (
        '```json\n{"name": "read_file", "arguments": {"path": "a"}}\n```\n'
        'then {"name": "list_dir", "arguments": {"path": "."}}'
    )
    assert _names(parse_text_tool_calls(text, TOOLS)) == ["read_file", "list_dir"]


@pytest.mark.parametrize("text", [
    "",
    "The answer is 51.843 degrees.",
    "Here is a dict: {'name': 'read_file'}",               # not JSON
    '{"name": "read_file", "arguments": {"path": ',        # truncated
    '{"name": "rm_rf", "arguments": {"path": "/"}}',       # unknown tool
    '{"name": "read_file", "arguments": ["a.py"]}',        # non-object arguments
    '{"name": "read_file", "arguments": "not json"}',      # unparsable string arguments
    '{"result": {"path": "a"}, "status": "ok"}',           # JSON, but not a tool call
])
def test_non_tool_and_malformed_text_yields_nothing(text):
    assert parse_text_tool_calls(text, TOOLS) == []


# ── Adapter: parsed calls are governed exactly like native ones ────────────────

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr(osiris_brain, "MEMORY_DIR", state)
    monkeypatch.setattr(osiris_brain, "MEMORY_FILE", state / "brain_memory.json")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "notes.txt").write_text("theta_lock = 51.843\n")
    return ws


def _request(caps):
    return AuthorizedAgentRequest(
        request_id="req-text", task="go", allowed_capabilities=frozenset(caps),
        data_classification="LOCAL_WORKSPACE", authority_scope="test",
    )


def _scripted(*contents):
    steps = [{"message": {"content": c}} for c in contents]
    seen = []

    def chat(messages, tools=None, model=None):
        seen.append([dict(m) for m in messages])
        return steps.pop(0)

    return chat, seen


def test_text_call_on_coder_model_runs_through_the_governor(workspace):
    chat, seen = _scripted(LIVE_REPLY, "It says theta_lock = 51.843")
    adapter = LocalBrainAdapter(workspace, model="qwen2.5-coder:7b", chat_fn=chat)
    result = asyncio.run(adapter.run(_request(READ_ONLY)))
    tool_msgs = [m["content"] for m in seen[-1] if m["role"] == "tool"]
    assert tool_msgs == ["theta_lock = 51.843\n"]
    assert result.output == "It says theta_lock = 51.843"
    assert result.usage["text_tool_calls"] == 1
    assert result.usage["governance"][0]["decision"] == "GRANTED"
    assert not (workspace / "out.txt").exists()


def test_text_write_is_still_denied_out_of_scope(workspace):
    write = '{"name": "write_file", "arguments": {"path": "out.txt", "content": "x"}}'
    chat, seen = _scripted(write, "done")
    adapter = LocalBrainAdapter(workspace, model="qwen2.5-coder:7b", chat_fn=chat)
    asyncio.run(adapter.run(_request(READ_ONLY)))
    tool_msgs = [m["content"] for m in seen[-1] if m["role"] == "tool"]
    assert tool_msgs[0].startswith("DENIED by CapabilityGovernor")
    assert not (workspace / "out.txt").exists()


def test_text_write_needs_human_approval_and_records_its_origin(workspace):
    proposals = []

    def approver(proposal, description):
        proposals.append((proposal, description))
        return HumanApproval.for_proposal(proposal, approver_id="tester")

    write = '{"name": "write_file", "arguments": {"path": "out.txt", "content": "51.843\\n"}}'
    chat, _ = _scripted(write, "done")
    adapter = LocalBrainAdapter(workspace, model="qwen2.5-coder:7b", chat_fn=chat, approver=approver)
    asyncio.run(adapter.run(_request(ELEVATED)))
    proposal, description = proposals[0]
    assert proposal.arguments["tool_call_origin"] == "text"
    assert "[parsed from text]" in description
    assert (workspace / "out.txt").read_text() == "51.843\n"


def test_native_tool_model_does_not_execute_json_it_merely_mentions(workspace):
    mention = 'Call it like {"name": "read_file", "arguments": {"path": "notes.txt"}}.'
    chat, _ = _scripted(mention)
    adapter = LocalBrainAdapter(workspace, model="qwen2.5:7b", chat_fn=chat)
    result = asyncio.run(adapter.run(_request(READ_ONLY)))
    assert result.output == mention
    assert result.usage["tool_calls"] == 0 and result.usage["text_tool_calls"] == 0


@pytest.mark.parametrize("flag,model,expected", [
    (None, "qwen2.5-coder:7b", True),
    (None, "QWEN2.5-CODER:14b", True),
    (None, "qwen2.5:7b", False),
    (True, "qwen2.5:7b", True),
    (False, "qwen2.5-coder:7b", False),
])
def test_fallback_switch(workspace, flag, model, expected):
    adapter = LocalBrainAdapter(workspace, model=model, text_tool_calls=flag)
    assert adapter.text_tool_calls_enabled() is expected


def test_native_tool_calls_take_precedence_over_text(workspace):
    native = {"message": {"content": '{"name": "list_dir", "arguments": {"path": "."}}',
                          "tool_calls": [{"function": {"name": "read_file",
                                                       "arguments": {"path": "notes.txt"}}}]}}
    steps = [native, {"message": {"content": "ok"}}]
    adapter = LocalBrainAdapter(workspace, model="qwen2.5-coder:7b",
                                chat_fn=lambda m, tools=None, model=None: steps.pop(0))
    result = asyncio.run(adapter.run(_request(READ_ONLY)))
    assert result.usage["tool_calls"] == 1 and result.usage["text_tool_calls"] == 0
