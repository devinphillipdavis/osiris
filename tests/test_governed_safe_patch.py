"""SafePatchWorkflow writes only under a CapabilityGovernor ExecutionGrant,
and the osiris_cli router drives /propose -> /apply through that path."""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from osiris.agents.gateway import HumanApproval
from osiris_cli.conversation_router import ConversationRouter, mode_capabilities
from osiris_cli.safe_patch import SafePatchWorkflow
from osiris_cli.session_manager import SessionManager

FIXED = 'def add(a, b):\n    """Correct addition."""\n    return a + b\n'
RESPONSE = "# TargetFile: math_utils.py\n```python\n" + FIXED + "```\n"


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "math_utils.py").write_text("def add(a, b):\n    return a - b\n")
    return ws


def _processed(workflow):
    res = workflow.process_proposal(RESPONSE, target_relative_path="math_utils.py")
    assert res["success"], res
    return res


def _apply(workflow, res, **kw):
    return workflow.apply_patch(
        target_relative_path=kw.pop("target", "math_utils.py"),
        code=kw.pop("code", res["code"]),
        diff_text=res["diff"],
        original_sha256=res["original_sha256"],
        ast_safe=True,
        sandbox_passed=True,
        **kw,
    )


def test_legacy_flag_without_approval_does_not_write(workspace):
    wf = SafePatchWorkflow(workspace)
    receipt = _apply(wf, _processed(wf), human_approved=False)
    assert receipt.applied is False
    assert "requires a human approval" in receipt.governance_error
    assert "return a - b" in (workspace / "math_utils.py").read_text()


def test_legacy_flag_is_governed_and_path_confined(workspace):
    wf = SafePatchWorkflow(workspace)
    res = _processed(wf)
    receipt = _apply(wf, res, target="../escape.py", human_approved=True)
    assert receipt.applied is False
    assert "Path traversal" in receipt.governance_error
    assert not (workspace.parent / "escape.py").exists()


def test_reviewed_proposal_with_bound_approval_is_applied(workspace):
    wf = SafePatchWorkflow(workspace)
    res = _processed(wf)
    request = wf.patch_request()
    proposal = wf.build_patch_proposal("math_utils.py", res["code"], res["diff"],
                                       res["original_sha256"], request)
    approval = HumanApproval.for_proposal(proposal, approver_id="reviewer")
    receipt = _apply(wf, res, human_approved=False, proposal=proposal,
                     approval=approval, request=request)
    assert receipt.applied is True
    assert receipt.grant_id.startswith("grant_")
    assert receipt.proposal_digest == proposal.proposal_digest
    assert receipt.human_approved is True
    assert "return a + b" in (workspace / "math_utils.py").read_text()


def test_content_changed_after_review_is_refused(workspace):
    wf = SafePatchWorkflow(workspace)
    res = _processed(wf)
    request = wf.patch_request()
    proposal = wf.build_patch_proposal("math_utils.py", res["code"], res["diff"],
                                       res["original_sha256"], request)
    approval = HumanApproval.for_proposal(proposal, approver_id="reviewer")
    receipt = _apply(wf, res, code=res["code"] + "BACKDOOR = 1\n", human_approved=False,
                     proposal=proposal, approval=approval, request=request)
    assert receipt.applied is False
    assert "differs from the reviewed proposal" in receipt.governance_error


def test_approval_cannot_be_moved_to_another_proposal(workspace):
    wf = SafePatchWorkflow(workspace)
    res = _processed(wf)
    request = wf.patch_request()
    reviewed = wf.build_patch_proposal("math_utils.py", res["code"], res["diff"],
                                       res["original_sha256"], request)
    reissued = wf.build_patch_proposal("math_utils.py", res["code"], res["diff"],
                                       res["original_sha256"], request)
    approval = HumanApproval.for_proposal(reviewed, approver_id="reviewer")
    receipt = _apply(wf, res, human_approved=False, proposal=reissued,
                     approval=approval, request=request)
    assert receipt.applied is False
    assert "different proposal digest" in receipt.governance_error


def test_a_proposal_can_be_applied_only_once(workspace):
    wf = SafePatchWorkflow(workspace)
    res = _processed(wf)
    request = wf.patch_request()
    proposal = wf.build_patch_proposal("math_utils.py", res["code"], res["diff"],
                                       res["original_sha256"], request)
    approval = HumanApproval.for_proposal(proposal, approver_id="reviewer")
    first = _apply(wf, res, human_approved=False, proposal=proposal, approval=approval, request=request)
    second = _apply(wf, res, human_approved=False, proposal=proposal, approval=approval, request=request)
    assert first.applied is True
    assert second.applied is False
    assert "Replay" in second.governance_error


def test_expired_proposal_is_refused(workspace, monkeypatch):
    monkeypatch.setattr(SafePatchWorkflow, "PROPOSAL_TTL_S", -1.0)
    wf = SafePatchWorkflow(workspace)
    receipt = _apply(wf, _processed(wf), human_approved=True)
    assert receipt.applied is False
    assert "expired" in receipt.governance_error


def test_unsafe_or_unsandboxed_patch_never_reaches_the_governor(workspace):
    wf = SafePatchWorkflow(workspace)
    res = _processed(wf)
    receipt = wf.apply_patch("math_utils.py", res["code"], res["diff"], res["original_sha256"],
                             ast_safe=True, sandbox_passed=False, human_approved=True)
    assert receipt.applied is False
    assert receipt.governance_error.startswith("pre-gate failed")


# ── Router: /propose -> /apply ─────────────────────────────────────────────────

def _propose(router, workspace):
    (workspace / "proposal.md").write_text(RESPONSE)
    return router.route_turn("/propose proposal.md")


def _router(workspace, tmp_path, mode="inspect", model="local_nclm", backend_factory=None):
    sm = SessionManager(storage_dir=str(tmp_path / "sessions"))
    sm.new_session(workspace_path=str(workspace), mode=mode, model=model)
    return ConversationRouter(str(workspace), sm, backend_factory=backend_factory)


def test_mode_capability_scopes():
    assert "WORKSPACE_WRITE" not in mode_capabilities("inspect")
    assert "SUBPROCESS_EXEC" not in mode_capabilities("propose")
    assert {"WORKSPACE_WRITE", "SUBPROCESS_EXEC"} <= mode_capabilities("edit")
    assert mode_capabilities("safe") == {"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL"}


def test_apply_refused_in_inspect_mode(workspace, tmp_path):
    router = _router(workspace, tmp_path, mode="inspect")
    _propose(router, workspace)
    assert "not permitted in mode 'inspect'" in router.route_turn("/apply")
    assert "return a - b" in (workspace / "math_utils.py").read_text()


@pytest.mark.parametrize("confirm,applied", [(True, True), (False, False)])
def test_apply_in_propose_mode_follows_human_decision(workspace, tmp_path, monkeypatch, confirm, applied):
    router = _router(workspace, tmp_path, mode="propose")
    monkeypatch.setattr(router.approval_ui, "prompt_confirmation",
                        lambda *a, **k: confirm)
    out = _propose(router, workspace)
    assert "Pending WORKSPACE_WRITE proposal" in out
    reply = router.route_turn("/apply")
    assert ("Applied math_utils.py under grant_" in reply) is applied
    assert ("return a + b" in (workspace / "math_utils.py").read_text()) is applied
    assert "No pending patch" in router.route_turn("/apply")


def test_templated_model_keeps_canned_responses(workspace, tmp_path):
    router = _router(workspace, tmp_path, model="local_nclm",
                     backend_factory=lambda r: pytest.fail("backend must not be built"))
    assert "evidence-governed engineering copilot" in router.route_turn("hello there")


def test_real_model_turns_go_through_the_gateway(workspace, tmp_path, monkeypatch):
    from osiris.agents.gateway.adapters import LocalBrainAdapter

    script = [
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "write_file", "arguments": {"path": "x.py", "content": "y = 2\n"}}}
        ]}},
        {"message": {"content": "tried to write"}},
    ]
    prompts = []

    def factory(router):
        return LocalBrainAdapter(router.workspace_root, model=router.active_model,
                                 approver=lambda p, d: prompts.append(d),
                                 governor=router.governor,
                                 chat_fn=lambda m, tools=None, model=None: script.pop(0))

    router = _router(workspace, tmp_path, mode="inspect", model="qwen2.5:7b", backend_factory=factory)
    reply = router.route_turn("please add a file")
    assert reply.splitlines()[0] == "tried to write"
    assert "0 granted · 1 denied · mode inspect" in reply
    assert prompts == []  # out of scope in inspect mode: refused without asking
    assert not (workspace / "x.py").exists()


def test_model_slash_command_switches_generation(workspace, tmp_path):
    router = _router(workspace, tmp_path)
    assert router.generation_enabled() is False
    assert "governed local model" in router.route_turn("/model qwen2.5:7b")
    assert router.generation_enabled() is True
    router.route_turn("/model local_nclm")
    assert router.generation_enabled() is False


def test_propose_file_outside_workspace_is_refused(workspace, tmp_path):
    (workspace.parent / "evil.md").write_text(RESPONSE)
    router = _router(workspace, tmp_path, mode="propose")
    assert "Path traversal" in router.route_turn("/propose ../evil.md")
