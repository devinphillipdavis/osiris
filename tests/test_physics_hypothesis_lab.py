"""
Unit tests for physics_hypothesis_lab.py
Covers:
- Schema validation
- Dimensional analysis checks and failures
- Epistemic quarantine (consciousness, 19.93-bit, phi transition)
- OCCR negative control pattern firewalls
- Claim ceiling reduction and clamping
"""

import pytest
import sys
from pathlib import Path

# Ensure repo root is on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from physics_hypothesis_lab import (
    DimensionalStatus,
    FalsifiablePrediction,
    HypothesisStatus,
    MechanismType,
    PhysicsHypothesis,
    PhysicsHypothesisLab,
)


@pytest.fixture
def lab():
    return PhysicsHypothesisLab()


@pytest.fixture
def valid_hypothesis_dict():
    return {
        "hypothesis_id": "OCCR-HYP-000101",
        "title": "Staggered XY4 Decoupling Coherence Preservation",
        "statement": "Offsetting the odd sublattice in XY4 dynamical decoupling by half a slot suppresses static ZZ coupling in 8-qubit superconducting chains.",
        "domain": "QUANTUM_INFORMATION",
        "mechanism_type": "COMPUTATIONAL",
        "assumptions": ["Static ZZ coupling dominates idle phase decay over timescales tau <= 32us."],
        "mathematical_formulation": "H_eff = sum_i J_zz (Z_i Z_{i+1}) with staggered pi pulses",
        "symbols_and_units": {
            "tau": {"dimension": "time", "si_unit": "us", "description": "Idle duration"},
            "J_zz": {"dimension": "frequency", "si_unit": "khz", "description": "Coupling strength"}
        },
        "dimensional_analysis_status": "PASSED",
        "falsifiable_predictions": [
            {
                "prediction": "State survival fidelity F_plus exceeds standard XY4 by >= 0.05 at tau=32us.",
                "observable": "F_plus",
                "condition": "tau == 32us",
                "falsified_if": "F_staggered <= F_xy4 + 0.01"
            }
        ],
        "null_hypothesis": "Staggered timing yields no significant change in fidelity relative to standard XY4 (Delta_F <= 0).",
        "observables": ["F_plus", "parity_survival"],
        "measurement_or_simulation_plan": "Execute 1000 shots on local Aer simulator for tau in [8us, 16us, 32us].",
        "baseline_models": ["idle_unmitigated", "standard_xy4"],
        "negative_controls": ["random_phase_jitter", "sign_flipped_pi_rotations"],
        "likely_confounders": ["Finite sampling error", "SPAM distortion"],
        "alternative_explanations": ["Higher-order drift in simulated noise parameters."],
        "data_requirements": {"sample_size": 1000, "trials": 5},
        "required_evidence": ["LOCAL_SIMULATION_REPLICATION"],
        "requested_claim_ceiling": "HYPOTHESIS",
        "permitted_claim_ceiling": "HYPOTHESIS",
        "provenance": {"generator": "test_suite", "timestamp": 1700000000.0, "seed": 42},
        "status": "GENERATED"
    }


def test_valid_hypothesis_passes_validation(lab, valid_hypothesis_dict):
    hyp, flaws = lab.instantiate_hypothesis(valid_hypothesis_dict)
    assert hyp is not None
    assert len(flaws) == 0

    critique = lab.critique(hyp)
    assert critique.passed_validation is True
    assert critique.quarantine_triggered is False
    assert critique.permitted_claim_ceiling == "HYPOTHESIS"
    assert critique.score >= 80


def test_missing_falsifiable_predictions_fails(lab, valid_hypothesis_dict):
    valid_hypothesis_dict["falsifiable_predictions"] = []
    hyp, flaws = lab.instantiate_hypothesis(valid_hypothesis_dict)
    assert hyp is None
    assert any("falsifiable_predictions" in fl for fl in flaws)


def test_dimensional_analysis_failure(lab, valid_hypothesis_dict):
    valid_hypothesis_dict["symbols_and_units"]["tau"]["si_unit"] = "kg"  # Invalid unit for time
    hyp, _ = lab.instantiate_hypothesis(valid_hypothesis_dict)
    assert hyp is not None

    critique = lab.critique(hyp)
    assert any("DIMENSIONAL_ANALYSIS_FAILED" in fl for fl in critique.detected_flaws)
    assert critique.passed_validation is False


def test_quarantine_consciousness_claims(lab, valid_hypothesis_dict):
    valid_hypothesis_dict["statement"] += " This demonstrates living consciousness in the quantum circuit."
    hyp, _ = lab.instantiate_hypothesis(valid_hypothesis_dict)
    critique = lab.critique(hyp)

    assert critique.quarantine_triggered is True
    assert critique.passed_validation is False
    assert critique.permitted_claim_ceiling == "NO_CLAIM"
    assert hyp.status == HypothesisStatus.ARCHIVED


def test_negative_control_refutation_warning(lab, valid_hypothesis_dict):
    valid_hypothesis_dict["statement"] += " Correlation is verified via microseconds % 46.0 µs tau resonance."
    hyp, _ = lab.instantiate_hypothesis(valid_hypothesis_dict)
    critique = lab.critique(hyp)

    assert len(critique.negative_control_warnings) > 0
    assert any("OCCR-NEG-0001" in w for w in critique.negative_control_warnings)


def test_overclaim_ceiling_clamped_to_hypothesis(lab, valid_hypothesis_dict):
    valid_hypothesis_dict["requested_claim_ceiling"] = "PRODUCT_CAPABILITY"
    hyp, _ = lab.instantiate_hypothesis(valid_hypothesis_dict)
    critique = lab.critique(hyp)

    assert critique.permitted_claim_ceiling == "HYPOTHESIS"
    assert any("OVERCLAIM_REDUCTION" in fl for fl in critique.detected_flaws)
