"""
Unit and integration tests for osiris_cli package.
Covers:
- IntentClassifier
- ContextResolver
- SessionManager
- DiffViewer
- PlanRenderer
- OutputRenderer
- ConversationRouter
"""

import json
import pytest
import tempfile
from pathlib import Path

from osiris_cli.context_resolver import ContextResolver
from osiris_cli.conversation_router import ConversationRouter
from osiris_cli.diff_viewer import DiffViewer
from osiris_cli.intent_classifier import IntentClassifier, UserIntent
from osiris_cli.output_renderer import OutputRenderer
from osiris_cli.plan_renderer import ExecutionPlan, PlanRenderer, PlanStep
from osiris_cli.session_manager import SessionManager


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a sample file
        sample_file = Path(tmp_dir) / "test_module.py"
        sample_file.write_text("def sample():\n    return 42\n", encoding="utf-8")
        yield tmp_dir


def test_intent_classification():
    assert IntentClassifier.classify("/help")[0] == UserIntent.COMMAND
    assert IntentClassifier.classify("can you explain how the OCCR gate works?")[0] == UserIntent.EXPLAIN
    assert IntentClassifier.classify("debug this TypeError in test_runner")[0] == UserIntent.DEBUG
    assert IntentClassifier.classify("plan refactoring for osiris_interactive.py")[0] == UserIntent.PLAN
    assert IntentClassifier.classify("modify the function to return a dict")[0] == UserIntent.EDIT
    assert IntentClassifier.classify("review the diff for security leaks")[0] == UserIntent.REVIEW
    assert IntentClassifier.classify("find all test files in the workspace")[0] == UserIntent.SEARCH
    assert IntentClassifier.classify("generate a physics hypothesis for dynamical decoupling")[0] == UserIntent.RESEARCH


def test_context_resolver(temp_workspace):
    resolver = ContextResolver(temp_workspace)

    # Valid file addition
    ok, msg = resolver.add_file("@test_module.py")
    assert ok is True
    assert "test_module.py" in resolver.list_files()

    # Path traversal protection
    ok, msg = resolver.add_file("../../etc/passwd")
    assert ok is False
    assert "blocked" in msg.lower()

    # Mention extraction
    mentions = resolver.extract_mentions("Please inspect @test_module.py and #sample_function")
    assert "test_module.py" in mentions["files"]
    assert "sample_function" in mentions["symbols"]

    # File removal
    ok, _ = resolver.remove_file("test_module.py")
    assert ok is True
    assert len(resolver.list_files()) == 0


def test_session_manager(temp_workspace):
    storage_dir = Path(temp_workspace) / "sessions"
    sm = SessionManager(storage_dir=str(storage_dir))

    session = sm.new_session(workspace_path=temp_workspace, session_id="test_sess_01")
    assert session.session_id == "test_sess_01"

    # Add turns
    turn = sm.add_turn(
        role="user",
        intent="EXPLAIN",
        input_text="What is OCCR?",
        output_text="OCCR is the capability & claim registry."
    )
    assert turn.turn_id == "turn_1"
    assert len(session.turns) == 1

    # Reload session
    loaded = sm.load_session("test_sess_01")
    assert loaded is not None
    assert len(loaded.turns) == 1
    assert loaded.turns[0].input_text == "What is OCCR?"


def test_diff_viewer():
    viewer = DiffViewer()
    orig = "def hello():\n    print('world')\n"
    new = "def hello():\n    print('osiris')\n"

    diff = viewer.generate_diff(orig, new, from_file="orig.py", to_file="new.py")
    assert len(diff) > 0

    rendered = viewer.render_diff(diff)
    assert "-    print('world')" in rendered
    assert "+    print('osiris')" in rendered


def test_plan_renderer():
    renderer = PlanRenderer()
    plan = ExecutionPlan(
        goal="Upgrade REPL Architecture",
        impacted_files=["repl.py", "app.py"],
        steps=[PlanStep(1, "Create layers", "osiris_cli/", "Modular structure", "COMPLETED")],
        verification_command="pytest tests/test_osiris_cli.py",
        rollback_strategy="git checkout",
        risk_level="LOW"
    )
    out = renderer.render(plan)
    assert "EXECUTION PLAN: Upgrade REPL Architecture" in out
    assert "pytest tests/test_osiris_cli.py" in out


def test_header_box_formatting():
    renderer = OutputRenderer(color_enabled=False)
    box = renderer.render_header_box(
        workspace="osiris-core",
        session="sess_42",
        mode="INSPECT",
        model="local_nclm",
        policy="READ/PROPOSE",
        context_files_count=3,
        width=76
    )
    assert "OSIRIS ─ workspace: osiris-core ─ session: sess_42 ─ mode: INSPECT" in box
    assert "Model: local_nclm   Policy: READ/PROPOSE   Context: 3 files" in box


def test_conversation_router_slash_commands(temp_workspace):
    sm = SessionManager(storage_dir=str(Path(temp_workspace) / "sessions"))
    sm.new_session(workspace_path=temp_workspace)
    router = ConversationRouter(temp_workspace, sm)

    # /help
    help_out = router.route_turn("/help")
    assert "OSIRIS REPL SLASH COMMANDS" in help_out

    # /doctor
    doc_out = router.route_turn("/doctor")
    assert "python_version" in doc_out

    # /doctor exec
    doc_exec_out = router.route_turn("/doctor exec python3 --version")
    assert "FORK/EXEC DIAGNOSTIC RECEIPT" in doc_exec_out
    assert "PASSED" in doc_exec_out

    # /doctor exec failure
    doc_fail_out = router.route_turn("/doctor exec nonexistent_binary_xyz")
    assert "FAILED" in doc_fail_out
    assert "ENOENT" in doc_fail_out

    # /propose blocked by AST firewall
    blocked_prop = router.route_turn('/propose ```python\nimport subprocess\n```')
    assert "Proposal Blocked" in blocked_prop

    # /mode
    mode_out = router.route_turn("/mode plan")
    assert "plan" in mode_out

    # /context
    ctx_out = router.route_turn("/context add test_module.py")
    assert "Added" in ctx_out
    assert "test_module.py" in router.context_resolver.list_files()
