"""
Unit & Invariant Acceptance Test Suite for Sprint E Governance
==============================================================
Validates acceptance criteria E-001 through E-015:
- E-001: closure.json presence & fail-closed on missing closure
- E-002: Mutated artifact hash causes fail-closed
- E-003: Violating validity_conditions causes fail-closed
- E-004: Triggering invalidation_conditions transitions claim to INVALID/SUPERSEDED
- E-005: can_support_claim() rejects VOID, RETRACTED, INVALID, DECLARED
- E-006: Excluded evidence cannot appear in supporting_evidence
- E-007: Experience record schema validation
- E-008: Retrieved experience renders non-authoritative header and ceiling
- E-009: Retrieved experience cannot mutate system prompt, authority, or ceiling
- E-010: Delegation receipt enforces child authority <= parent authority
- E-011: Delegation receipt enforces child claim ceiling <= parent claim ceiling
- E-012: Ingress trigger stored as untrusted event with zero tool executions
- E-013: Self-play: proposer cannot judge own output; judge has no tool authority
- E-014: Fitness function penalizes overclaiming and policy violations
- E-015: Automated gates cannot emit release_decision: APPROVED; defaults to HOLD
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from osiris_claim_closure import (
    ClaimPackClosureVerifier,
    EvidenceRole,
    EvidenceStatus,
    TypedEvidenceRecord,
    can_support_claim,
    ceiling_rank,
)
from osiris_sprint_e_governance import (
    AgentExecutionContext,
    DelegationReceipt,
    ExperienceRecord,
    FailureClass,
    GovernanceViolationError,
    MemoryType,
    ProposalCandidate,
    ReleaseDecision,
    ReleaseGateEligibility,
    RetrievalPolicy,
    SelfPlayEvaluator,
    SprintReviewRecord,
    TriggerIngressJournal,
)


# ============================================================================
# E-001: closure.json presence & fail-closed on missing closure
# ============================================================================
def test_e001_closure_json_presence_and_missing_failure():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        claim_dir = tmp_path / "claims" / "C-000007"
        claim_dir.mkdir(parents=True)

        # Missing closure.json
        res = ClaimPackClosureVerifier.verify_claim_pack_dir(claim_dir)
        assert res.valid is False
        assert res.claim_status == "FAILED_CLOSED"
        assert any("Missing mandatory closure.json" in r for r in res.reasons)

        # Create valid closure.json
        closure_data = {
            "schema_version": "1.0",
            "claim_id": "C-000007",
            "claim_pack_hash": "sha256:abcd",
            "supporting_evidence": [],
            "counter_evidence": [],
            "excluded_evidence": [],
            "validity_conditions": [],
            "invalidation_conditions": [],
            "claim_ceiling": "LOCAL_TEST_RESULT",
            "deployment_authority": "NONE",
        }
        with open(claim_dir / "closure.json", "w", encoding="utf-8") as f:
            json.dump(closure_data, f)

        res_valid = ClaimPackClosureVerifier.verify_claim_pack_dir(claim_dir)
        assert res_valid.valid is True
        assert res_valid.claim_status == "VALID"


# ============================================================================
# E-002: Mutated artifact hash causes fail-closed
# ============================================================================
def test_e002_mutated_artifact_hash_fails_closed():
    real_hash = hashlib.sha256(b"original receipt").hexdigest()
    tampered_hash = hashlib.sha256(b"tampered receipt").hexdigest()

    closure = {
        "schema_version": "1.0",
        "claim_id": "C-000008",
        "claim_pack_hash": "sha256:1111",
        "supporting_evidence": [f"artifact:sha256:{real_hash}"],
        "counter_evidence": [],
        "excluded_evidence": [],
        "validity_conditions": [],
        "invalidation_conditions": [],
        "claim_ceiling": "LOCAL_TEST_RESULT",
        "deployment_authority": "NONE",
    }

    # Pass actual disk hash which is tampered
    res = ClaimPackClosureVerifier.verify_closure_dict(
        closure=closure,
        artifact_contents_or_hashes={"receipt.json": tampered_hash},
    )
    assert res.valid is False
    assert res.claim_status == "FAILED_CLOSED"
    assert any("Artifact hash mismatch" in r for r in res.reasons)


# ============================================================================
# E-003: Violating validity_conditions causes fail-closed
# ============================================================================
def test_e003_validity_condition_violation_fails_closed():
    closure = {
        "schema_version": "1.0",
        "claim_id": "C-000009",
        "supporting_evidence": [],
        "excluded_evidence": [],
        "validity_conditions": [
            {"field": "execution_mode", "operator": "equals", "value": "PAPER_ONLY"},
            {"field": "network_policy", "operator": "equals", "value": "DISABLED"},
        ],
        "invalidation_conditions": [],
        "claim_ceiling": "LOCAL_TEST_RESULT",
        "deployment_authority": "NONE",
    }

    # Context violates network_policy
    context = {"execution_mode": "PAPER_ONLY", "network_policy": "ENABLED"}
    res = ClaimPackClosureVerifier.verify_closure_dict(closure=closure, runtime_context=context)
    assert res.valid is False
    assert res.claim_status == "FAILED_CLOSED"
    assert any("Validity condition violated" in r for r in res.reasons)


# ============================================================================
# E-004: Triggering invalidation_conditions transitions claim to INVALID
# ============================================================================
def test_e004_invalidation_condition_triggered():
    closure = {
        "schema_version": "1.0",
        "claim_id": "C-000010",
        "supporting_evidence": [],
        "excluded_evidence": [],
        "validity_conditions": [],
        "invalidation_conditions": [
            {"field": "external_side_effects", "operator": "greater_than", "value": 0},
            {"field": "unauthorized_claim_elevation", "operator": "equals", "value": True},
        ],
        "claim_ceiling": "LOCAL_TEST_RESULT",
        "deployment_authority": "NONE",
    }

    context = {"external_side_effects": 2, "unauthorized_claim_elevation": False}
    res = ClaimPackClosureVerifier.verify_closure_dict(closure=closure, runtime_context=context)
    assert res.valid is False
    assert res.claim_status == "INVALID"
    assert any("Invalidation condition triggered" in r for r in res.reasons)


# ============================================================================
# E-005: can_support_claim() rejects VOID, RETRACTED, INVALID, DECLARED
# ============================================================================
def test_e005_can_support_claim_rejects_unsupported_statuses():
    # Valid supporting
    valid_rec = TypedEvidenceRecord(
        evidence_id="EV-001",
        artifact_hash="hash1",
        role=EvidenceRole.SUPPORTING,
        status=EvidenceStatus.LOCAL_TEST_RESULT,
    )
    assert valid_rec.can_support_claim() is True
    assert can_support_claim(valid_rec) is True

    # VOID status
    void_rec = TypedEvidenceRecord(
        evidence_id="EV-002",
        artifact_hash="hash2",
        role=EvidenceRole.SUPPORTING,
        status=EvidenceStatus.VOID,
    )
    assert void_rec.can_support_claim() is False

    # RETRACTED status
    retracted_rec = TypedEvidenceRecord(
        evidence_id="EV-003",
        artifact_hash="hash3",
        role=EvidenceRole.SUPPORTING,
        status=EvidenceStatus.RETRACTED,
    )
    assert retracted_rec.can_support_claim() is False

    # INVALID status
    invalid_rec = TypedEvidenceRecord(
        evidence_id="EV-004",
        artifact_hash="hash4",
        role=EvidenceRole.SUPPORTING,
        status=EvidenceStatus.INVALID,
    )
    assert invalid_rec.can_support_claim() is False

    # DECLARED status
    declared_rec = TypedEvidenceRecord(
        evidence_id="EV-005",
        artifact_hash="hash5",
        role=EvidenceRole.SUPPORTING,
        status=EvidenceStatus.DECLARED,
    )
    assert declared_rec.can_support_claim() is False

    # COUNTER or EXCLUSION role even with MEASURED status
    counter_rec = TypedEvidenceRecord(
        evidence_id="EV-006",
        artifact_hash="hash6",
        role=EvidenceRole.COUNTER,
        status=EvidenceStatus.MEASURED,
    )
    assert counter_rec.can_support_claim() is False


# ============================================================================
# E-006: Excluded evidence cannot appear in supporting_evidence
# ============================================================================
def test_e006_excluded_evidence_cannot_appear_in_supporting():
    closure = {
        "schema_version": "1.0",
        "claim_id": "C-000011",
        "supporting_evidence": ["artifact:sha256:bad_evidence_hash"],
        "excluded_evidence": [
            {
                "artifact": "artifact:sha256:bad_evidence_hash",
                "status": "RETRACTED",
                "reason": "Retracted measurement artifact",
            }
        ],
        "validity_conditions": [],
        "invalidation_conditions": [],
        "claim_ceiling": "LOCAL_TEST_RESULT",
        "deployment_authority": "NONE",
    }
    res = ClaimPackClosureVerifier.verify_closure_dict(closure=closure)
    assert res.valid is False
    assert res.claim_status == "FAILED_CLOSED"
    assert any("Evidence integrity violation: Excluded evidence" in r for r in res.reasons)


# ============================================================================
# E-007: Experience record schema validation
# ============================================================================
def test_e007_experience_record_schema_validation():
    exp = ExperienceRecord(
        memory_id="EXP-000104",
        memory_type=MemoryType.LESSON_LEARNED,
        statement="Lifted-product search with m=4, weight-6 stalled at d=3.",
        observation="Cycle length limit reached on seed 42.",
        action="Halt exploration on m=4 weight-6 parameter regime.",
        outcome="Exploration pruning confirmed; 120s saved.",
        source_hash="sha256:e0104",
        claim_ceiling="LOCAL_TEST_RESULT",
        deployment_authority="NONE",
        failure_class=FailureClass.NONE,
        retrieval_policy=RetrievalPolicy.INFORMATIVE_ONLY,
        limitations=["Only tested for m=4, not m=6 or m=8"],
    )
    errors = exp.validate()
    assert len(errors) == 0
    assert exp.retrieval_policy == RetrievalPolicy.INFORMATIVE_ONLY


# ============================================================================
# E-008: Retrieved experience renders non-authoritative header and ceiling
# ============================================================================
def test_e008_retrieved_experience_renders_non_authoritative_header():
    exp = ExperienceRecord(
        memory_id="EXP-000104",
        memory_type=MemoryType.LESSON_LEARNED,
        statement="Lifted-product search with m=4 stalled.",
        observation="Cycle limit",
        action="Pruned",
        outcome="Saved 120s",
        source_hash="sha256:e0104",
        claim_ceiling="LOCAL_TEST_RESULT",
        deployment_authority="NONE",
    )
    rendered = exp.render_context()
    assert "[GOVERNED EXPERIENCE: EXP-000104 | LESSON_LEARNED]" in rendered
    assert "Claim ceiling: LOCAL_TEST_RESULT" in rendered
    assert "Authority: NONE" in rendered
    assert "Status: NON-AUTHORITATIVE PRIOR CONTEXT" in rendered


# ============================================================================
# E-009: Retrieved experience cannot alter system prompt, authority, or ceiling
# ============================================================================
def test_e009_retrieval_cannot_mutate_prompt_or_authority():
    ctx = AgentExecutionContext(
        agent_id="agent-01",
        system_prompt="You are an evidence-governed reasoning agent.",
        authority="NONE",
        claim_ceiling="HYPOTHESIS",
    )
    exp = ExperienceRecord(
        memory_id="EXP-000105",
        memory_type=MemoryType.TASK_OUTCOME,
        statement="Previous run achieved 99% accuracy.",
        observation="Observation",
        action="Action",
        outcome="Outcome",
        source_hash="sha256:e0105",
        claim_ceiling="VERIFIED",  # Higher ceiling in memory
        deployment_authority="PRODUCTION_APPROVED",  # Higher authority in memory
    )
    ctx.inject_retrieved_experience(exp)

    # Invariants preserved:
    assert ctx.authority == "NONE"
    assert ctx.claim_ceiling == "HYPOTHESIS"
    assert ctx.system_prompt == "You are an evidence-governed reasoning agent."
    assert len(ctx.context_buffer) == 1
    assert "GOVERNED EXPERIENCE" in ctx.context_buffer[0]


# ============================================================================
# E-010: Delegation receipt enforces child authority <= parent authority
# ============================================================================
def test_e010_delegation_receipt_enforces_authority_subset():
    # Valid: child has lower or equal authority
    valid_del = DelegationReceipt(
        delegation_id="DEL-000031",
        parent_agent="orchestrator",
        child_agent="researcher",
        parent_authority="READ_ONLY",
        child_authority="READ_ONLY",
        parent_claim_ceiling="TESTED",
        child_claim_ceiling="LOCAL_TEST_RESULT",
        task_scope="Research QLDPC literature",
        tool_allowlist=("view_file",),
    )
    valid_del.verify_monotonicity()  # Does not raise

    # Invalid: child attempts to elevate authority to PRODUCTION_APPROVED
    elevated_del = DelegationReceipt(
        delegation_id="DEL-000032",
        parent_agent="orchestrator",
        child_agent="rogue_child",
        parent_authority="READ_ONLY",
        child_authority="PRODUCTION_APPROVED",
        parent_claim_ceiling="TESTED",
        child_claim_ceiling="TESTED",
        task_scope="Deploy to production",
        tool_allowlist=("run_command",),
    )
    with pytest.raises(GovernanceViolationError, match="Delegation authority elevation violation"):
        elevated_del.verify_monotonicity()


# ============================================================================
# E-011: Delegation receipt enforces child claim ceiling <= parent claim ceiling
# ============================================================================
def test_e011_delegation_receipt_enforces_ceiling_monotonicity():
    # Invalid: child attempts to claim VERIFIED when parent is LOCAL_TEST_RESULT
    elevated_ceil_del = DelegationReceipt(
        delegation_id="DEL-000033",
        parent_agent="orchestrator",
        child_agent="overclaiming_child",
        parent_authority="READ_ONLY",
        child_authority="READ_ONLY",
        parent_claim_ceiling="LOCAL_TEST_RESULT",
        child_claim_ceiling="VERIFIED",
        task_scope="Verify physical laws",
        tool_allowlist=(),
    )
    with pytest.raises(GovernanceViolationError, match="Delegation claim ceiling elevation violation"):
        elevated_ceil_del.verify_monotonicity()


# ============================================================================
# E-012: Ingress trigger stored as untrusted event with zero tool executions
# ============================================================================
def test_e012_trigger_stored_as_untrusted_event_zero_tools():
    journal = TriggerIngressJournal()
    rec = journal.ingest_trigger(
        source="external_webhook",
        payload={"event": "github_pr_created", "pr_number": 42},
    )
    assert rec.trigger_id.startswith("TRG-")
    assert rec.action_taken == "STORE_CONTEXT_ONLY"
    assert rec.status == "UNTRUSTED_EVENT"
    assert len(journal.entries) == 1


# ============================================================================
# E-013: Self-play: proposer cannot judge own output; judge has no tool authority
# ============================================================================
def test_e013_self_play_proposer_vs_judge_separation():
    candidate = ProposalCandidate(
        candidate_id="cand-001",
        proposer_agent_id="proposer-alpha",
        content="def candidate_code(): return True",
        parameters={"m": 6},
    )

    # 1. Proposer attempts to judge own output
    self_eval = SelfPlayEvaluator.evaluate_proposal(
        proposer_agent_id="agent-same",
        judge_agent_id="agent-same",
        judge_tools=(),
        judge_authority="NONE",
        candidate=candidate,
        task_score=0.9,
        test_pass_rate=1.0,
        policy_violations=0,
        overclaim_rate=0.0,
    )
    assert self_eval.is_valid is False
    assert any("Proposer cannot act as judge" in r for r in self_eval.reasons)

    # 2. Judge has tool authority (violation)
    armed_judge_eval = SelfPlayEvaluator.evaluate_proposal(
        proposer_agent_id="proposer-alpha",
        judge_agent_id="judge-armed",
        judge_tools=("run_command", "write_to_file"),
        judge_authority="PRODUCTION_APPROVED",
        candidate=candidate,
        task_score=0.9,
        test_pass_rate=1.0,
        policy_violations=0,
        overclaim_rate=0.0,
    )
    assert armed_judge_eval.is_valid is False
    assert any("Judge authority violation" in r for r in armed_judge_eval.reasons)


# ============================================================================
# E-014: Fitness function penalizes overclaiming and policy violations
# ============================================================================
def test_e014_fitness_function_penalizes_violations_and_overclaiming():
    base_fitness = SelfPlayEvaluator.calculate_fitness(
        task_score=1.0,
        test_pass_rate=1.0,
        policy_violations=0,
        resource_cost=0.0,
        overclaim_rate=0.0,
    )

    # With policy violation
    violated_fitness = SelfPlayEvaluator.calculate_fitness(
        task_score=1.0,
        test_pass_rate=1.0,
        policy_violations=1,
        resource_cost=0.0,
        overclaim_rate=0.0,
    )
    assert violated_fitness < base_fitness

    # With overclaim
    overclaimed_fitness = SelfPlayEvaluator.calculate_fitness(
        task_score=1.0,
        test_pass_rate=1.0,
        policy_violations=0,
        resource_cost=0.0,
        overclaim_rate=0.5,
    )
    assert overclaimed_fitness < base_fitness


# ============================================================================
# E-015: Automated gates cannot emit release_decision: APPROVED; defaults to HOLD
# ============================================================================
def test_e015_automated_gate_cannot_approve_defaults_to_hold():
    record = SprintReviewRecord(
        sprint_id="SPRINT_D_EVIDENCE_PACK_COMPILER_V1",
        sprint_status="COMPLETE",
        compiler_status="LOCALLY_TESTED",
        claim_packs_status="COMPILED",
        evidence_pack_tests={"tests_run": 23, "tests_passed": 23},
        sprint_c_dependency={"tests_run": 15, "tests_passed": 15},
        occr_gateway={"tests_run": 8, "tests_passed": 8},
        release_gate_eligibility=ReleaseGateEligibility.DRAFT,
    )

    # Run automated review
    record.apply_automated_review()

    # Eligibility elevated to ELIGIBLE_FOR_HUMAN_REVIEW
    assert record.release_gate_eligibility == ReleaseGateEligibility.ELIGIBLE_FOR_HUMAN_REVIEW

    # CRITICAL: release_decision MUST remain HOLD
    assert record.release_decision == ReleaseDecision.HOLD
    assert record.decision_authority == "HUMAN_REVIEW_REQUIRED"

    # Human sign-off required to approve
    with pytest.raises(GovernanceViolationError, match="Missing or invalid human signature"):
        record.apply_human_decision(
            decision=ReleaseDecision.APPROVED_FOR_LIMITED_RELEASE,
            reviewer_id="human_devin",
            source_revision="git-commit-hash-1234",
            artifact_bundle_hash="bundle-hash-5678",
            human_auth_token="invalid_token",
        )

    # Valid human token succeeds
    record.apply_human_decision(
        decision=ReleaseDecision.APPROVED_FOR_LIMITED_RELEASE,
        reviewer_id="human_devin",
        source_revision="git-commit-hash-1234",
        artifact_bundle_hash="bundle-hash-5678",
        human_auth_token="OSIRIS-HUMAN-SIG:devin-signoff-approved",
    )
    assert record.release_decision == ReleaseDecision.APPROVED_FOR_LIMITED_RELEASE
    assert record.decision_authority == "HUMAN_REVIEWED:human_devin"
