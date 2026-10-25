"""
Unit tests for evidence_and_claim_pipeline.py
Covers:
- Preregistered statistical analysis and effect size computation
- Null hypothesis retention vs rejection
- ResearchClaim formulation and claim ceiling clamping
- ReviewPacket assembly with negative controls and permitted language
"""

import pytest
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from evidence_and_claim_pipeline import EvidenceAndClaimPipeline
from experiment_orchestrator import ExperimentPreregistration, RunReceipt
from physics_hypothesis_lab import DimensionalStatus, MechanismType, PhysicsHypothesis


@pytest.fixture
def pipeline():
    return EvidenceAndClaimPipeline()


@pytest.fixture
def mock_prereg():
    return ExperimentPreregistration(
        experiment_id="OCCR-EXP-000202",
        hypothesis_id="OCCR-HYP-000202",
        null_hypothesis="Delta_F <= 0",
        primary_endpoint="fidelity",
        units="dimensionless",
        dimensional_analysis="Fidelity ratio",
        data_source="Local Aer",
        dataset_hashes=["0" * 64],
        model_hashes=["aer_v1"],
        fixed_hyperparameters={"shots": 1000},
        sample_size_rationale="Adequate power",
        planned_statistical_method="t-test",
        stopping_rule="Fixed shots",
        exclusion_rules=[],
        baseline_controls=["idle_unmitigated"],
        negative_controls=["random_phase"],
        expected_failure_modes=[],
        execution_environment={"node_type": "TEST"},
        claim_ceiling_before_execution="TESTED",
        manifest_hash="a" * 64
    )


@pytest.fixture
def mock_receipt(mock_prereg):
    return RunReceipt(
        run_id="OCCR-RUN-000202",
        experiment_id=mock_prereg.experiment_id,
        preregistration_manifest_hash=mock_prereg.manifest_hash,
        status="COMPLETED",
        timestamp_start=1700000000.0,
        timestamp_end=1700000005.0,
        execution_node="TEST_NODE",
        command=["python3", "sim.py"],
        exit_code=0,
        raw_artifact_hashes={"results.json": "b" * 64},
        metrics={
            "observed_primary_endpoint": 0.885,
            "baseline_value": 0.795,
            "fidelity": 0.885,
            "idle_baseline": 0.795
        },
        policy_evaluations=[],
        receipt_signature="c" * 64
    )


def test_analyze_run_rejects_null_hypothesis_on_significant_effect(pipeline, mock_prereg, mock_receipt):
    outcome = pipeline.analyze_run(mock_prereg, mock_receipt)

    assert outcome.effect_size == pytest.approx(0.090, abs=1e-4)
    assert outcome.null_hypothesis_rejected is True
    assert outcome.is_preregistered is True


def test_formulate_claim_capped_at_tested(pipeline, mock_prereg, mock_receipt):
    outcome = pipeline.analyze_run(mock_prereg, mock_receipt)
    claim = pipeline.formulate_claim(mock_prereg, mock_receipt, outcome)

    assert claim.claim_id.startswith("OCCR-CLM-")
    assert claim.claim_ceiling == "TESTED"
    assert "improved by +0.0900" in claim.statement
    assert len(claim.evidence_refs) >= 1


def test_build_review_packet(pipeline, mock_prereg, mock_receipt):
    outcome = pipeline.analyze_run(mock_prereg, mock_receipt)
    claim = pipeline.formulate_claim(mock_prereg, mock_receipt, outcome)

    hyp = PhysicsHypothesis(
        hypothesis_id=mock_prereg.hypothesis_id,
        title="Test Staggered DD",
        statement="Staggered timing suppresses static ZZ coupling.",
        domain="QUANTUM_INFORMATION",
        mechanism_type=MechanismType.COMPUTATIONAL,
        assumptions=["Static ZZ dominates"],
        mathematical_formulation="H_eff = J_zz * ZZ",
        symbols_and_units={"tau": {"dimension": "time", "si_unit": "us", "description": "window"}},
        dimensional_analysis_status=DimensionalStatus.PASSED,
        falsifiable_predictions=[],
        null_hypothesis="Delta_F <= 0",
        observables=["fidelity"],
        measurement_or_simulation_plan="Local Aer run",
        baseline_models=["idle"],
        negative_controls=["random"],
        likely_confounders=[],
        alternative_explanations=[],
        data_requirements={},
        required_evidence=[],
        requested_claim_ceiling="HYPOTHESIS",
        permitted_claim_ceiling="HYPOTHESIS",
        provenance={}
    )

    packet = pipeline.build_review_packet(hyp, mock_prereg, mock_receipt, outcome, claim)

    assert packet.packet_id.startswith("OCCR-PKT-")
    assert len(packet.permitted_claim_language) > 0
    assert len(packet.forbidden_claim_language) > 0
    assert len(packet.negative_control_checks) >= 5
    assert any("OCCR-NEG-0001" in chk for chk in packet.negative_control_checks)
