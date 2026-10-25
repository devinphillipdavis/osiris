"""
OSIRIS Physics Hypothesis Lab & Epistemic Quarantine Engine
===========================================================

Safe, local-first module for rigorous formulation, validation, and critique
of advanced-physics and computational hypotheses within OSIRIS.

Invariants:
- All hypotheses enter in status GENERATED or UNDER_CRITIQUE.
- Max permitted claim ceiling for any hypothesis is HYPOTHESIS.
- Hypotheses invoking metaphors as physical measurements (consciousness,
  sentience, phi=0.7734 transitions, socket queue timestamps) are QUARANTINED.
- Strict dimensional analysis and falsification criteria are enforced.
- Critiques are labeled DETERMINISTIC_RUBRIC_CRITIQUE or MODEL_CRITIQUE;
  never "peer review".
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from occr_governance_engine import (
    ClaimCeiling,
    NegativeControlRecord,
    get_occr_registry,
)


class MechanismType(str, enum.Enum):
    MATHEMATICAL = "MATHEMATICAL"
    COMPUTATIONAL = "COMPUTATIONAL"
    STATISTICAL = "STATISTICAL"
    PHYSICAL_HYPOTHESIS = "PHYSICAL_HYPOTHESIS"
    ENGINEERING_HYPOTHESIS = "ENGINEERING_HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class HypothesisStatus(str, enum.Enum):
    GENERATED = "GENERATED"
    UNDER_CRITIQUE = "UNDER_CRITIQUE"
    PREREGISTERED = "PREREGISTERED"
    SIMULATED = "SIMULATED"
    ANALYZED = "ANALYZED"
    REPLICATING = "REPLICATING"
    SUPPORTED_WITH_LIMITS = "SUPPORTED_WITH_LIMITS"
    REFUTED = "REFUTED"
    ARCHIVED = "ARCHIVED"


class DimensionalStatus(str, enum.Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    PENDING = "PENDING"


@dataclass
class FalsifiablePrediction:
    prediction: str
    observable: str
    condition: str
    falsified_if: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PhysicsHypothesis:
    hypothesis_id: str
    title: str
    statement: str
    domain: str
    mechanism_type: MechanismType
    assumptions: List[str]
    mathematical_formulation: str
    symbols_and_units: Dict[str, Dict[str, str]]
    dimensional_analysis_status: DimensionalStatus
    falsifiable_predictions: List[FalsifiablePrediction]
    null_hypothesis: str
    observables: List[str]
    measurement_or_simulation_plan: str
    baseline_models: List[str]
    negative_controls: List[str]
    likely_confounders: List[str]
    alternative_explanations: List[str]
    data_requirements: Dict[str, Any]
    required_evidence: List[str]
    requested_claim_ceiling: str
    permitted_claim_ceiling: str
    provenance: Dict[str, Any]
    status: HypothesisStatus = HypothesisStatus.GENERATED

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mechanism_type"] = self.mechanism_type.value
        d["dimensional_analysis_status"] = self.dimensional_analysis_status.value
        d["status"] = self.status.value
        return d

    def canonical_hash(self) -> str:
        serialized = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class CritiqueReport:
    hypothesis_id: str
    critique_type: str  # "DETERMINISTIC_RUBRIC_CRITIQUE" or "MODEL_CRITIQUE"
    score: int          # 0 to 100
    passed_validation: bool
    quarantine_triggered: bool
    detected_flaws: List[str]
    dimensional_analysis_result: str
    negative_control_warnings: List[str]
    recommended_modifications: List[str]
    permitted_claim_ceiling: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PhysicsHypothesisLab:
    """
    Lab for evaluating, validating, and critiquing physics hypotheses.
    Enforces epistemic quarantine against pseudoscience, ungrounded metaphors,
    and disproven experimental artifacts.
    """

    QUARANTINE_PATTERNS = [
        (r"\bconsciousness\b", "Claims consciousness or sentience without an empirical biophysical basis."),
        (r"\bsentien(t|ce)\b", "Claims sentient agency in computational models."),
        (r"\bnon-causal intelligence\b", "Asserts non-causal omniscience or violation of relativistic causality."),
        (r"\btorsion frame\b", "Uses ungrounded speculative torsion mechanics as physical proof."),
        (r"\btrue name\b", "Esoteric or mystical terminology masquerading as physics."),
        (r"\buniversal constant 19\.93\b", "Mistakes finite sample ceiling log2(10^6) for a universal constant (OCCR-NEG-0005)."),
        (r"\bbimodal.*0\.7734\b", "Invokes circuit-width disparity artifact as physical phase transition (OCCR-NEG-0002)."),
        (r"\bmicrosecond.*46(\.0)?\s*µ?s\b", "Invokes Linux socket buffer timing artifact as quantum resonance (OCCR-NEG-0001)."),
        (r"\bspacetime manipulation\b", "Speculative warp or spacetime claims without peer-reviewed metrics."),
        (r"\bquantum supremacy\b", "Prohibited superlative without rigorous verifiable complexity separation.")
    ]

    DIMENSION_INVARIANTS = {
        "time": ["s", "us", "ns", "ms", "second", "microsecond"],
        "frequency": ["hz", "khz", "mhz", "ghz", "1/s"],
        "fidelity": ["dimensionless", "1", "ratio"],
        "energy": ["j", "ev", "mev", "gev"],
        "angle": ["rad", "deg", "degree", "radian"],
        "entropy": ["bit", "shannon", "nat", "j/k"]
    }

    def __init__(self):
        self.registry = get_occr_registry()

    def validate_schema(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate structure and essential fields of hypothesis data."""
        flaws: List[str] = []
        required_fields = [
            "hypothesis_id", "title", "statement", "domain", "mechanism_type",
            "assumptions", "mathematical_formulation", "symbols_and_units",
            "falsifiable_predictions", "null_hypothesis", "observables",
            "measurement_or_simulation_plan", "baseline_models", "negative_controls"
        ]
        for f in required_fields:
            if f not in data or data[f] is None:
                flaws.append(f"Missing required field: '{f}'")
            elif isinstance(data[f], (list, dict, str)) and len(data[f]) == 0:
                flaws.append(f"Required field '{f}' cannot be empty.")

        # Check hypothesis_id regex
        hyp_id = data.get("hypothesis_id", "")
        if not re.match(r"^OCCR-HYP-[0-9]{6}$", hyp_id):
            flaws.append(f"hypothesis_id '{hyp_id}' does not match pattern '^OCCR-HYP-[0-9]{{6}}$'.")

        return len(flaws) == 0, flaws

    def check_dimensional_analysis(self, symbols_and_units: Dict[str, Dict[str, str]], formulation: str) -> Tuple[DimensionalStatus, str]:
        """Perform dimensional and unit balance checks on symbols."""
        if not symbols_and_units:
            return DimensionalStatus.FAILED, "No symbols_and_units dictionary provided."

        for sym, meta in symbols_and_units.items():
            dim = meta.get("dimension", "").lower()
            unit = meta.get("si_unit", "").lower()
            if not dim or not unit:
                return DimensionalStatus.FAILED, f"Symbol '{sym}' missing dimension or unit specification."
            
            # If recognized dimension, check unit compatibility
            if dim in self.DIMENSION_INVARIANTS:
                allowed_units = self.DIMENSION_INVARIANTS[dim]
                if not any(u in unit for u in allowed_units):
                    return DimensionalStatus.FAILED, f"Unit '{unit}' incompatible with dimension '{dim}' for symbol '{sym}'."

        return DimensionalStatus.PASSED, "All declared symbols have well-formed, dimensionally consistent units."

    def critique(self, hypothesis: PhysicsHypothesis) -> CritiqueReport:
        """
        Evaluate hypothesis with deterministic rubric.
        Identifies epistemic flaws, unit mismatches, negative-control conflicts,
        and enforces claim ceiling bounds.
        """
        flaws: List[str] = []
        quarantine_triggered = False
        neg_warnings: List[str] = []
        recommended_mods: List[str] = []
        score = 100

        text_to_scan = f"{hypothesis.title} {hypothesis.statement} {hypothesis.mathematical_formulation}".lower()

        # 1. Epistemic Quarantine Scan
        for pattern, explanation in self.QUARANTINE_PATTERNS:
            if re.search(pattern, text_to_scan):
                flaws.append(f"QUARANTINE: {explanation}")
                quarantine_triggered = True
                score -= 35

        # 2. Check Negative Controls from OCCR Registry
        negative_controls = self.registry.get_negative_controls()
        for neg_id, neg in negative_controls.items():
            for pat in neg.disproven_patterns:
                if pat.lower() in text_to_scan:
                    warning = (
                        f"NEGATIVE_CONTROL_MATCH: Statement matches disproven artifact '{pat}' "
                        f"from {neg_id}. Lesson: {neg.lesson}"
                    )
                    neg_warnings.append(warning)
                    flaws.append(warning)
                    score -= 25

        # 3. Dimensional Analysis
        dim_status, dim_msg = self.check_dimensional_analysis(
            hypothesis.symbols_and_units, hypothesis.mathematical_formulation
        )
        if dim_status != DimensionalStatus.PASSED:
            flaws.append(f"DIMENSIONAL_ANALYSIS_FAILED: {dim_msg}")
            score -= 20
            recommended_mods.append("Correct dimensional mismatches and provide explicit SI units.")

        # 4. Falsifiability & Null Hypothesis
        if len(hypothesis.falsifiable_predictions) == 0:
            flaws.append("FALSIFIABILITY_DEFICIT: Zero falsifiable predictions defined.")
            score -= 30
            recommended_mods.append("Define at least one prediction with clear observable and falsification threshold.")
        else:
            for pred in hypothesis.falsifiable_predictions:
                if not pred.falsified_if or len(pred.falsified_if.strip()) < 5:
                    flaws.append(f"WEAK_FALSIFIER: Prediction '{pred.prediction}' lacks explicit falsified_if criteria.")
                    score -= 10

        if not hypothesis.null_hypothesis or len(hypothesis.null_hypothesis.strip()) < 10:
            flaws.append("NULL_HYPOTHESIS_MISSING: Null hypothesis is missing or underspecified.")
            score -= 20
            recommended_mods.append("State an explicit, statistically testable null hypothesis.")

        # 5. Baselines & Controls
        if not hypothesis.baseline_models:
            flaws.append("MISSING_BASELINES: No standard baseline models specified for comparative benchmarking.")
            score -= 15
            recommended_mods.append("Include standard textbook or uncoupled baseline models.")

        if not hypothesis.negative_controls:
            flaws.append("MISSING_NEGATIVE_CONTROLS: No negative control experiments specified.")
            score -= 15
            recommended_mods.append("Specify randomized-phase, uncoupled, or null controls.")

        # 6. Claim Ceiling Invariant Enforcement
        # Hypotheses can never claim beyond HYPOTHESIS
        permitted_ceiling = ClaimCeiling.HYPOTHESIS.name
        if hypothesis.requested_claim_ceiling not in (ClaimCeiling.NO_CLAIM.name, ClaimCeiling.HYPOTHESIS.name):
            flaws.append(
                f"OVERCLAIM_REDUCTION: Requested claim ceiling '{hypothesis.requested_claim_ceiling}' "
                f"exceeds maximum hypothesis ceiling 'HYPOTHESIS'. Permitted ceiling clamped to HYPOTHESIS."
            )
            score -= 10

        if quarantine_triggered:
            permitted_ceiling = ClaimCeiling.NO_CLAIM.name
            hypothesis.status = HypothesisStatus.ARCHIVED
        elif flaws:
            hypothesis.status = HypothesisStatus.UNDER_CRITIQUE
        else:
            hypothesis.status = HypothesisStatus.UNDER_CRITIQUE

        passed_validation = (len(flaws) == 0 and not quarantine_triggered)
        score = max(0, min(100, score))

        return CritiqueReport(
            hypothesis_id=hypothesis.hypothesis_id,
            critique_type="DETERMINISTIC_RUBRIC_CRITIQUE",
            score=score,
            passed_validation=passed_validation,
            quarantine_triggered=quarantine_triggered,
            detected_flaws=flaws,
            dimensional_analysis_result=dim_msg,
            negative_control_warnings=neg_warnings,
            recommended_modifications=recommended_mods,
            permitted_claim_ceiling=permitted_ceiling
        )

    def instantiate_hypothesis(self, data: Dict[str, Any]) -> Tuple[Optional[PhysicsHypothesis], List[str]]:
        """Instantiate PhysicsHypothesis from dict after strict validation."""
        valid, flaws = self.validate_schema(data)
        if not valid:
            return None, flaws

        try:
            preds = [
                FalsifiablePrediction(**p) if isinstance(p, dict) else p
                for p in data["falsifiable_predictions"]
            ]
            dim_status = DimensionalStatus(data.get("dimensional_analysis_status", DimensionalStatus.PENDING.value))
            status = HypothesisStatus(data.get("status", HypothesisStatus.GENERATED.value))
            mech_type = MechanismType(data.get("mechanism_type", MechanismType.COMPUTATIONAL.value))

            hyp = PhysicsHypothesis(
                hypothesis_id=data["hypothesis_id"],
                title=data["title"],
                statement=data["statement"],
                domain=data["domain"],
                mechanism_type=mech_type,
                assumptions=data["assumptions"],
                mathematical_formulation=data["mathematical_formulation"],
                symbols_and_units=data["symbols_and_units"],
                dimensional_analysis_status=dim_status,
                falsifiable_predictions=preds,
                null_hypothesis=data["null_hypothesis"],
                observables=data["observables"],
                measurement_or_simulation_plan=data["measurement_or_simulation_plan"],
                baseline_models=data["baseline_models"],
                negative_controls=data["negative_controls"],
                likely_confounders=data.get("likely_confounders", []),
                alternative_explanations=data.get("alternative_explanations", []),
                data_requirements=data.get("data_requirements", {}),
                required_evidence=data.get("required_evidence", []),
                requested_claim_ceiling=data.get("requested_claim_ceiling", "HYPOTHESIS"),
                permitted_claim_ceiling=data.get("permitted_claim_ceiling", "HYPOTHESIS"),
                provenance=data.get("provenance", {"generator": "user", "timestamp": time.time(), "seed": 42}),
                status=status
            )
            return hyp, []
        except Exception as e:
            return None, [f"Instantiation error: {str(e)}"]
