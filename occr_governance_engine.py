"""
OSIRIS Capability & Claim Registry (OCCR) - Executable Governance Control Plane
Version: 1.1.0
Author: Agile Defense Systems LLC / OSIRIS Sovereign Core
License: Proprietary / Sovereign Research Invariant

This module implements the 3-Gate Orthogonal Governance Architecture:
1. Claim Gate: "May we say it?" (Epistemic assertion boundary)
2. Execution Gate: "May we do it?" (Operational dispatch boundary)
3. Release Gate: "May we ship it?" (External distribution boundary)

Key Invariants:
- None of the 5 dimensions (Implementation, Evidence, Authority, Ceiling, Independence)
  may be inferred from any other.
- MEASURED != APPROVED, APPROVED != VERIFIED, VERIFIED != GENERALIZED, IMPLEMENTED != EFFICACIOUS.
- Claims have independent machine-readable IDs (OCCR-CLM-XXXXXX).
- Deprecated/refuted claims are first-class negative controls (OCCR-NEG-XXXX).
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================================
# 1. Orthogonal Status Dimensions & Controlled Vocabularies
# ============================================================================

class ImplementationStatus(enum.Enum):
    DECLARED = "DECLARED"                      # Specified in docs/intent; no code written
    PROPOSED = "PROPOSED"                      # Interface/AST specified; implementation pending
    IMPLEMENTED_CANDIDATE = "IMPLEMENTED_CANDIDATE"  # Code exists; partially verified or unverified
    IMPLEMENTED = "IMPLEMENTED"                # Complete implementation satisfying internal contracts
    DEPRECATED = "DEPRECATED"                  # Retained for audit/negative controls; decommissioned
    REFUTED = "REFUTED"                        # Architectural or algorithmic assumption disproven


class EvidenceStatus(enum.Enum):
    NONE = "NONE"                              # Zero empirical data or test suites
    SIMULATED = "SIMULATED"                    # Idealized mock/simulation runs only
    MEASURED = "MEASURED"                      # Physical hardware telemetry collected
    SELF_REPORTED_TESTED = "SELF_REPORTED_TESTED"  # Developer/model internal test suite passes
    REPRODUCED = "REPRODUCED"                  # Replicated across independent seeds/sessions/chips
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"  # Blind third-party or hidden-test harness
    UNRESOLVED = "UNRESOLVED"                  # Contradictory evidence under audit


class DeploymentAuthority(enum.Enum):
    NONE = "NONE"                              # Complete execution lock
    REPLAY_ONLY = "REPLAY_ONLY"                # Deterministic check on frozen historical inputs
    STAGING_ONLY = "STAGING_ONLY"              # Sandboxed execution; non-production only
    READ_ONLY = "READ_ONLY"                    # Discovery/audit; zero write/mutation privileges
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"  # Locked until explicit human token provided
    PRODUCTION_APPROVED = "PRODUCTION_APPROVED"  # Unrestricted production execution authorized


class ClaimCeiling(enum.IntEnum):
    """
    Ordered hierarchy of claim strength.
    A capability's evidence status establishes an absolute ceiling above which
    no claim may be made.
    """
    NO_CLAIM = 0
    HYPOTHESIS = 1            # Theoretical mechanism; zero factual claims
    IMPLEMENTATION_ONLY = 2   # Code exists and parses; no functional efficacy claimed
    TESTED = 3                # Passes deterministic unit/integration assertion gates
    EMPIRICAL_RESULT = 4      # Direct empirical measurement on specific physical setup
    REPRODUCIBILITY = 5       # Replicated across independent environments/hardware
    PRODUCT_CAPABILITY = 6    # Fully generalized, robust production software capability
    VERIFIED = 7              # Independently audited, peer-reviewed, and externally confirmed


class ReviewIndependence(enum.Enum):
    SELF_REVIEW = "SELF_REVIEW"                # Authored and tested by same author/agent
    SEPARATE_AGENT_REVIEW = "SEPARATE_AGENT_REVIEW"  # Scored by secondary agent harness
    HUMAN_REVIEW = "HUMAN_REVIEW"              # Audited by a human engineer
    INDEPENDENT_REVIEW = "INDEPENDENT_REVIEW"  # Blind external domain audit


class GateDecision(enum.Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    HOLD = "HOLD"


class CustomerTier(enum.Enum):
    TIER_1_INTERNAL_RESEARCH = "TIER_1_INTERNAL_RESEARCH"
    TIER_2_PILOT_READY = "TIER_2_PILOT_READY"
    TIER_3_RESTRICTED_RESEARCH = "TIER_3_RESTRICTED_RESEARCH"


# ============================================================================
# 2. Data Models: Capabilities, Claims, Negative Controls, and Policies
# ============================================================================

@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    namespace: str  # "capabilities", "experiments", "hypotheses", "deprecated", "policies"
    title: str
    implementation_status: ImplementationStatus
    evidence_status: EvidenceStatus
    deployment_authority: DeploymentAuthority
    claim_ceiling: ClaimCeiling
    review_independence: ReviewIndependence
    source_of_truth: str
    allowed_claim_types: Tuple[str, ...] = ()
    forbidden_claim_types: Tuple[str, ...] = ()
    spec: str = ""


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str                              # e.g., "OCCR-CLM-000417"
    capability_id: str
    statement: str
    claim_ceiling: ClaimCeiling
    evidence_refs: Tuple[str, ...]
    counter_evidence_refs: Tuple[str, ...] = ()
    status: str = "VALID"                      # VALID, SUPERSEDED, REFUTED
    supersedes: Tuple[str, ...] = ()
    invalidates: Tuple[str, ...] = ()


@dataclass(frozen=True)
class NegativeControlRecord:
    """
    First-class negative evidence preventing future agent/model loops
    from re-discovering disproven hypotheses or measurement artifacts.
    """
    claim_id: str                              # e.g., "OCCR-NEG-0004"
    original_claim: str
    status: str = "REFUTED"
    refutation_method: str = ""
    refutation_artifact: str = ""
    lesson: str = ""
    disproven_patterns: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPolicy:
    policy_id: str
    allowed_roles: Tuple[str, ...]
    sandbox_required: bool
    requires_human_token: bool
    max_budget_usd: float
    rate_limit_per_min: int


@dataclass(frozen=True)
class Claimability:
    allowed: bool
    ceiling: ClaimCeiling
    requested: ClaimCeiling
    reasons: Tuple[str, ...]
    required_evidence: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "ceiling": self.ceiling.name,
            "requested": self.requested.name,
            "reasons": list(self.reasons),
            "required_evidence": list(self.required_evidence)
        }


@dataclass(frozen=True)
class GateReceipt:
    gate_name: str
    decision: GateDecision
    timestamp: float
    target_id: str
    reasons: Tuple[str, ...]
    receipt_hash: str = field(default="")

    def compute_hash(self) -> str:
        payload = f"{self.gate_name}:{self.decision.value}:{self.timestamp}:{self.target_id}:{','.join(self.reasons)}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "decision": self.decision.value,
            "timestamp": self.timestamp,
            "target_id": self.target_id,
            "reasons": list(self.reasons),
            "receipt_hash": self.receipt_hash or self.compute_hash()
        }


# ============================================================================
# 3. Gate 1: Claim Gate ("May we say it?")
# ============================================================================

class ClaimGate:
    """
    Enforces epistemic integrity.
    Ensures no generated artifact, README, customer communication, or report
    exceeds the empirical claim ceiling or asserts forbidden claims.
    """

    EVIDENCE_CEILING_MAP = {
        EvidenceStatus.NONE: ClaimCeiling.HYPOTHESIS,
        EvidenceStatus.SIMULATED: ClaimCeiling.TESTED,
        EvidenceStatus.SELF_REPORTED_TESTED: ClaimCeiling.TESTED,
        EvidenceStatus.MEASURED: ClaimCeiling.EMPIRICAL_RESULT,
        EvidenceStatus.REPRODUCED: ClaimCeiling.REPRODUCIBILITY,
        EvidenceStatus.INDEPENDENTLY_VERIFIED: ClaimCeiling.VERIFIED,
        EvidenceStatus.UNRESOLVED: ClaimCeiling.HYPOTHESIS,
    }

    FORBIDDEN_WORDS = (
        "discovery", "proves", "proven", "confirmed new physics",
        "quantum supremacy", "consciousness", "non-causal intelligence",
        "hardware-verified", "universal constant", "error correction breakthrough",
        "production ready", "guaranteed survival", "validated reasoning",
        "spacetime manipulation", "peer reviewed"
    )

    @classmethod
    def evaluate(
        cls,
        capability: CapabilityRecord,
        requested_assertion_type: str,
        requested_ceiling: ClaimCeiling,
        negative_controls: Dict[str, NegativeControlRecord],
        context: Optional[Dict[str, Any]] = None
    ) -> Claimability:
        reasons: List[str] = []
        required_evidence: List[str] = []

        # 1. Namespace Quarantine Check
        if capability.namespace in ("hypotheses", "deprecated"):
            if requested_ceiling > ClaimCeiling.HYPOTHESIS:
                reasons.append(
                    f"Capability '{capability.capability_id}' is in quarantined namespace '{capability.namespace}'. "
                    f"Max permitted ceiling is HYPOTHESIS."
                )
                required_evidence.append("FORMAL_EMPIRICAL_PROMOTION")
                return Claimability(
                    allowed=False,
                    ceiling=ClaimCeiling.HYPOTHESIS,
                    requested=requested_ceiling,
                    reasons=tuple(reasons),
                    required_evidence=tuple(required_evidence)
                )

        # 2. Check Forbidden Claim Types
        if requested_assertion_type in capability.forbidden_claim_types:
            reasons.append(
                f"Assertion type '{requested_assertion_type}' is explicitly forbidden for '{capability.capability_id}'."
            )
            required_evidence.append(f"RECLASSIFICATION_OF_{requested_assertion_type.upper()}")

        # 3. Check Allowed Claim Types
        if capability.allowed_claim_types and requested_assertion_type not in capability.allowed_claim_types:
            reasons.append(
                f"Assertion type '{requested_assertion_type}' is not in allowed claim types: {capability.allowed_claim_types}."
            )

        # 4. Check Justifiable Claim Ceiling from Evidence & Review Independence
        max_evidence_ceiling = cls.EVIDENCE_CEILING_MAP.get(capability.evidence_status, ClaimCeiling.NO_CLAIM)
        
        # Independence penalty: Self-review cannot claim beyond EMPIRICAL_RESULT
        if capability.review_independence == ReviewIndependence.SELF_REVIEW and max_evidence_ceiling > ClaimCeiling.TESTED:
            max_evidence_ceiling = ClaimCeiling.TESTED
            reasons.append("Review independence is SELF_REVIEW; capped at TESTED pending external audit.")
            required_evidence.append("INDEPENDENT_REVIEW")

        effective_ceiling = min(capability.claim_ceiling, max_evidence_ceiling)

        if requested_ceiling > effective_ceiling:
            reasons.append(
                f"Requested claim ceiling {requested_ceiling.name} exceeds effective ceiling {effective_ceiling.name}."
            )
            if effective_ceiling < ClaimCeiling.REPRODUCIBILITY:
                required_evidence.append("INDEPENDENT_REPLICATION")
            if effective_ceiling < ClaimCeiling.VERIFIED:
                required_evidence.append("PEER_REVIEWED_BENCHMARK")

        # 5. Check against Context statement, Forbidden Words & Negative Controls
        if context and "statement" in context:
            statement_lower = context["statement"].lower()
            
            # Check forbidden vocabulary unless claim ceiling is VERIFIED
            if effective_ceiling < ClaimCeiling.VERIFIED:
                for bad_word in cls.FORBIDDEN_WORDS:
                    if bad_word in statement_lower:
                        reasons.append(f"Statement contains forbidden term '{bad_word}' without VERIFIED claim ceiling.")
                        required_evidence.append("PEER_REVIEWED_DISCOVERY_PROOF")

            for neg_id, neg in negative_controls.items():
                for pattern in neg.disproven_patterns:
                    if pattern.lower() in statement_lower:
                        reasons.append(
                            f"Statement matches disproven pattern '{pattern}' refuted by negative control {neg_id} ({neg.lesson})."
                        )
                        required_evidence.append(f"REFUTATION_REVERSAL_PROOF_{neg_id}")

        allowed = len(reasons) == 0
        return Claimability(
            allowed=allowed,
            ceiling=effective_ceiling,
            requested=requested_ceiling,
            reasons=tuple(reasons),
            required_evidence=tuple(required_evidence)
        )


# ============================================================================
# 4. Gate 2: Execution Gate ("May we do it?")
# ============================================================================

class ExecutionGate:
    """
    Enforces operational safety and dispatch authorization.
    Completely orthogonal to Claim Gate.
    """

    @classmethod
    def evaluate(
        cls,
        capability: CapabilityRecord,
        role: str,
        human_approval_token: Optional[str],
        policy: ExecutionPolicy,
        is_sandbox: bool = True
    ) -> GateReceipt:
        reasons: List[str] = []
        now = time.time()

        if capability.deployment_authority == DeploymentAuthority.NONE:
            reasons.append(f"Deployment authority is NONE for '{capability.capability_id}'. Absolute execution lock.")

        elif capability.deployment_authority == DeploymentAuthority.REPLAY_ONLY:
            if not is_sandbox:
                reasons.append(f"Deployment authority is REPLAY_ONLY; live execution forbidden.")

        elif capability.deployment_authority == DeploymentAuthority.READ_ONLY:
            if role in ("mutation", "executor", "writer"):
                reasons.append(f"Deployment authority is READ_ONLY; mutating role '{role}' rejected.")

        elif capability.deployment_authority == DeploymentAuthority.HUMAN_APPROVAL_REQUIRED:
            if not human_approval_token or not human_approval_token.startswith("OSIRIS-HUMAN-AUTH:"):
                reasons.append(f"Execution requires verified human approval token. Missing or invalid token.")

        if role not in policy.allowed_roles:
            reasons.append(f"Role '{role}' is not in policy allowed roles: {policy.allowed_roles}.")

        if policy.sandbox_required and not is_sandbox:
            reasons.append("Policy mandates sandboxed execution.")

        decision = GateDecision.PASS if len(reasons) == 0 else GateDecision.BLOCK
        receipt = GateReceipt(
            gate_name="ExecutionGate",
            decision=decision,
            timestamp=now,
            target_id=capability.capability_id,
            reasons=tuple(reasons)
        )
        return GateReceipt(
            gate_name=receipt.gate_name,
            decision=receipt.decision,
            timestamp=receipt.timestamp,
            target_id=receipt.target_id,
            reasons=receipt.reasons,
            receipt_hash=receipt.compute_hash()
        )


# ============================================================================
# 5. Gate 3: Release Gate ("May we ship it?")
# ============================================================================

class ReleaseGate:
    """
    Enforces distribution and customer packaging criteria.
    """

    @classmethod
    def evaluate(
        cls,
        capability: CapabilityRecord,
        has_sbom: bool,
        has_security_audit: bool,
        negative_controls: Dict[str, NegativeControlRecord]
    ) -> GateReceipt:
        reasons: List[str] = []
        now = time.time()

        if capability.implementation_status != ImplementationStatus.IMPLEMENTED:
            reasons.append(
                f"Implementation status is {capability.implementation_status.name}; release requires IMPLEMENTED."
            )

        if capability.evidence_status not in (EvidenceStatus.REPRODUCED, EvidenceStatus.INDEPENDENTLY_VERIFIED):
            reasons.append(
                f"Evidence status is {capability.evidence_status.name}; release requires REPRODUCED or INDEPENDENTLY_VERIFIED."
            )

        if capability.review_independence in (ReviewIndependence.SELF_REVIEW,):
            reasons.append("Review independence is SELF_REVIEW; release requires HUMAN_REVIEW or INDEPENDENT_REVIEW.")

        if not has_sbom:
            reasons.append("Cryptographic SBOM attestation missing.")

        if not has_security_audit:
            reasons.append("Formal security audit attestation missing.")

        decision = GateDecision.PASS if len(reasons) == 0 else GateDecision.BLOCK
        receipt = GateReceipt(
            gate_name="ReleaseGate",
            decision=decision,
            timestamp=now,
            target_id=capability.capability_id,
            reasons=tuple(reasons)
        )
        return GateReceipt(
            gate_name=receipt.gate_name,
            decision=receipt.decision,
            timestamp=receipt.timestamp,
            target_id=receipt.target_id,
            reasons=receipt.reasons,
            receipt_hash=receipt.compute_hash()
        )


# ============================================================================
# 6. Unified OCCR Registry & Policy Control Plane
# ============================================================================

class OCCRRegistry:
    """
    Authoritative boundary between what exists, what has been demonstrated,
    and what OSIRIS is permitted to claim or execute.
    """

    def __init__(self):
        self._capabilities: Dict[str, CapabilityRecord] = {}
        self._claims: Dict[str, ClaimRecord] = {}
        self._negative_controls: Dict[str, NegativeControlRecord] = {}
        self._policies: Dict[str, ExecutionPolicy] = {}

    def register_capability(self, cap: CapabilityRecord) -> None:
        self._capabilities[cap.capability_id] = cap

    def register_claim(self, claim: ClaimRecord) -> None:
        self._claims[claim.claim_id] = claim

    def register_negative_control(self, neg: NegativeControlRecord) -> None:
        self._negative_controls[neg.claim_id] = neg

    def register_policy(self, pol: ExecutionPolicy) -> None:
        self._policies[pol.policy_id] = pol

    def get_capability(self, capability_id: str) -> Optional[CapabilityRecord]:
        return self._capabilities.get(capability_id)

    def get_negative_controls(self) -> Dict[str, NegativeControlRecord]:
        return dict(self._negative_controls)

    def claimability(
        self,
        capability_id: str,
        assertion_type: str,
        requested_ceiling: ClaimCeiling,
        context: Optional[Dict[str, Any]] = None
    ) -> Claimability:
        cap = self._capabilities.get(capability_id)
        if not cap:
            return Claimability(
                allowed=False,
                ceiling=ClaimCeiling.NO_CLAIM,
                requested=requested_ceiling,
                reasons=(f"Capability '{capability_id}' not found in registry.",),
                required_evidence=("REGISTER_CAPABILITY",)
            )

        return ClaimGate.evaluate(
            capability=cap,
            requested_assertion_type=assertion_type,
            requested_ceiling=requested_ceiling,
            negative_controls=self._negative_controls,
            context=context
        )

    def dispatch_check(
        self,
        capability_id: str,
        role: str,
        human_approval_token: Optional[str] = None,
        policy_id: str = "default_safe_policy",
        is_sandbox: bool = True
    ) -> GateReceipt:
        cap = self._capabilities.get(capability_id)
        if not cap:
            return GateReceipt(
                gate_name="ExecutionGate",
                decision=GateDecision.BLOCK,
                timestamp=time.time(),
                target_id=capability_id,
                reasons=(f"Capability '{capability_id}' not found in registry.",)
            )

        policy = self._policies.get(policy_id, ExecutionPolicy(
            policy_id="default_safe_policy",
            allowed_roles=("human", "auditor", "system"),
            sandbox_required=True,
            requires_human_token=False,
            max_budget_usd=0.0,
            rate_limit_per_min=60
        ))

        return ExecutionGate.evaluate(
            capability=cap,
            role=role,
            human_approval_token=human_approval_token,
            policy=policy,
            is_sandbox=is_sandbox
        )

    def release_check(
        self,
        capability_id: str,
        has_sbom: bool,
        has_security_audit: bool
    ) -> GateReceipt:
        cap = self._capabilities.get(capability_id)
        if not cap:
            return GateReceipt(
                gate_name="ReleaseGate",
                decision=GateDecision.BLOCK,
                timestamp=time.time(),
                target_id=capability_id,
                reasons=(f"Capability '{capability_id}' not found in registry.",)
            )

        return ReleaseGate.evaluate(
            capability=cap,
            has_sbom=has_sbom,
            has_security_audit=has_security_audit,
            negative_controls=self._negative_controls
        )

    def project_customer_tier(self, capability_id: str) -> CustomerTier:
        cap = self._capabilities.get(capability_id)
        if not cap:
            return CustomerTier.TIER_3_RESTRICTED_RESEARCH

        if cap.namespace in ("hypotheses", "deprecated"):
            return CustomerTier.TIER_3_RESTRICTED_RESEARCH
        if cap.evidence_status in (EvidenceStatus.NONE, EvidenceStatus.UNRESOLVED):
            return CustomerTier.TIER_3_RESTRICTED_RESEARCH
        if cap.claim_ceiling <= ClaimCeiling.HYPOTHESIS:
            return CustomerTier.TIER_3_RESTRICTED_RESEARCH

        if (
            cap.implementation_status in (ImplementationStatus.IMPLEMENTED, ImplementationStatus.IMPLEMENTED_CANDIDATE)
            and cap.evidence_status in (EvidenceStatus.SELF_REPORTED_TESTED, EvidenceStatus.MEASURED, EvidenceStatus.REPRODUCED)
            and cap.deployment_authority in (DeploymentAuthority.STAGING_ONLY, DeploymentAuthority.READ_ONLY, DeploymentAuthority.REPLAY_ONLY)
            and cap.review_independence in (ReviewIndependence.SEPARATE_AGENT_REVIEW, ReviewIndependence.HUMAN_REVIEW)
        ):
            return CustomerTier.TIER_2_PILOT_READY

        if (
            cap.implementation_status == ImplementationStatus.IMPLEMENTED
            and cap.evidence_status in (EvidenceStatus.REPRODUCED, EvidenceStatus.INDEPENDENTLY_VERIFIED, EvidenceStatus.SELF_REPORTED_TESTED)
            and cap.deployment_authority in (DeploymentAuthority.PRODUCTION_APPROVED, DeploymentAuthority.READ_ONLY, DeploymentAuthority.REPLAY_ONLY)
            and cap.review_independence in (ReviewIndependence.HUMAN_REVIEW, ReviewIndependence.INDEPENDENT_REVIEW)
        ):
            return CustomerTier.TIER_1_INTERNAL_RESEARCH

        return CustomerTier.TIER_3_RESTRICTED_RESEARCH


# ============================================================================
# 7. Canonical Default OCCR Factory
# ============================================================================

_GLOBAL_REGISTRY: Optional[OCCRRegistry] = None

def get_occr_registry() -> OCCRRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = build_default_occr()
    return _GLOBAL_REGISTRY


def build_default_occr() -> OCCRRegistry:
    reg = OCCRRegistry()

    # Capabilities
    reg.register_capability(CapabilityRecord(
        capability_id="capabilities.governance.replay_core",
        namespace="capabilities",
        title="Fail-Closed Tool Dispatch & Replay Governance",
        implementation_status=ImplementationStatus.IMPLEMENTED,
        evidence_status=EvidenceStatus.SELF_REPORTED_TESTED,
        deployment_authority=DeploymentAuthority.REPLAY_ONLY,
        claim_ceiling=ClaimCeiling.TESTED,
        review_independence=ReviewIndependence.SEPARATE_AGENT_REVIEW,
        source_of_truth="file:///home/enki/osiris-cli/payload_gate.py",
        allowed_claim_types=("code_exists", "interface_exists", "deterministic_behavior_under_test"),
        forbidden_claim_types=("scientific_efficacy", "causal_effect", "production_performance")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="capabilities.compiler.dnalang_parser",
        namespace="capabilities",
        title="DNA-Lang AST & Grammar Parser",
        implementation_status=ImplementationStatus.IMPLEMENTED_CANDIDATE,
        evidence_status=EvidenceStatus.SELF_REPORTED_TESTED,
        deployment_authority=DeploymentAuthority.READ_ONLY,
        claim_ceiling=ClaimCeiling.TESTED,
        review_independence=ReviewIndependence.SELF_REVIEW,
        source_of_truth="file:///home/enki/dnalang/src/compiler/parser.py",
        allowed_claim_types=("code_exists", "grammar_spec", "parser_passes_tests"),
        forbidden_claim_types=("autopoietic_runtime_proven", "quantum_execution")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="capabilities.serialization.canonical_json",
        namespace="capabilities",
        title="Deterministic Key-Sorted JSON Serializer",
        implementation_status=ImplementationStatus.IMPLEMENTED,
        evidence_status=EvidenceStatus.INDEPENDENTLY_VERIFIED,
        deployment_authority=DeploymentAuthority.PRODUCTION_APPROVED,
        claim_ceiling=ClaimCeiling.PRODUCT_CAPABILITY,
        review_independence=ReviewIndependence.HUMAN_REVIEW,
        source_of_truth="file:///home/enki/osiris-governance/src/osiris_governance/canonical.py",
        allowed_claim_types=("code_exists", "rfc8785_compliance", "deterministic_bytes"),
        forbidden_claim_types=("arbitrary_type_serialization",)
    ))

    # Research Discovery Workbench Capabilities
    reg.register_capability(CapabilityRecord(
        capability_id="capabilities.research.hypothesis_lab",
        namespace="capabilities",
        title="Physics Hypothesis Lab & Critique Engine",
        implementation_status=ImplementationStatus.IMPLEMENTED,
        evidence_status=EvidenceStatus.SELF_REPORTED_TESTED,
        deployment_authority=DeploymentAuthority.READ_ONLY,
        claim_ceiling=ClaimCeiling.TESTED,
        review_independence=ReviewIndependence.HUMAN_REVIEW,
        source_of_truth="file:///home/enki/physics_hypothesis_lab.py",
        allowed_claim_types=("schema_validation", "rubric_evaluation", "dimensional_analysis"),
        forbidden_claim_types=("discovery", "proves", "quantum_advantage")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="capabilities.research.orchestrator",
        namespace="capabilities",
        title="Local-Only Computational Experiment Orchestrator",
        implementation_status=ImplementationStatus.IMPLEMENTED,
        evidence_status=EvidenceStatus.SELF_REPORTED_TESTED,
        deployment_authority=DeploymentAuthority.STAGING_ONLY,
        claim_ceiling=ClaimCeiling.TESTED,
        review_independence=ReviewIndependence.HUMAN_REVIEW,
        source_of_truth="file:///home/enki/experiment_orchestrator.py",
        allowed_claim_types=("isolated_simulation_run", "receipt_generation"),
        forbidden_claim_types=("hardware_execution", "cloud_submission")
    ))

    # Experiments
    reg.register_capability(CapabilityRecord(
        capability_id="experiments.quantum.staggered_dd",
        namespace="experiments",
        title="Topology-Aware Staggered Dynamical Decoupling",
        implementation_status=ImplementationStatus.IMPLEMENTED,
        evidence_status=EvidenceStatus.REPRODUCED,
        deployment_authority=DeploymentAuthority.HUMAN_APPROVAL_REQUIRED,
        claim_ceiling=ClaimCeiling.EMPIRICAL_RESULT,
        review_independence=ReviewIndependence.HUMAN_REVIEW,
        source_of_truth="doi:10.5281/zenodo.17859207",
        allowed_claim_types=("measured_p_plus_improvement", "telemetry_recorded"),
        forbidden_claim_types=("infinite_coherence", "quantum_supremacy", "universal_memory_constant")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="experiments.nclm.byte_model_learning",
        namespace="experiments",
        title="NCLM Autopoietic Generative Byte Model (Step 31)",
        implementation_status=ImplementationStatus.IMPLEMENTED_CANDIDATE,
        evidence_status=EvidenceStatus.UNRESOLVED,
        deployment_authority=DeploymentAuthority.STAGING_ONLY,
        claim_ceiling=ClaimCeiling.HYPOTHESIS,
        review_independence=ReviewIndependence.SELF_REVIEW,
        source_of_truth="file:///home/enki/.osiris/living/train_runs/trainer.log",
        allowed_claim_types=("training_loss_observed",),
        forbidden_claim_types=("persistent_learning_proven", "agi_threshold", "consciousness")
    ))

    # Hypotheses (Quarantined Research Hypotheses - Operational Effect: NONE, Deployment Authority: NONE)
    reg.register_capability(CapabilityRecord(
        capability_id="hypotheses.physics.crsm_11d",
        namespace="hypotheses",
        title="11D Cosmic Resonance Substrate Mechanics (CRSM)",
        implementation_status=ImplementationStatus.PROPOSED,
        evidence_status=EvidenceStatus.NONE,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.HYPOTHESIS,
        review_independence=ReviewIndependence.SELF_REVIEW,
        source_of_truth="spec:11d_crsm_theoretical_memo",
        allowed_claim_types=(),
        forbidden_claim_types=("scientific_efficacy", "operational_authority", "spacetime_modification")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="hypotheses.physics.phi_consciousness_proxy",
        namespace="hypotheses",
        title="Consciousness Proxy & Negentropy Condensation Hypothesis",
        implementation_status=ImplementationStatus.PROPOSED,
        evidence_status=EvidenceStatus.NONE,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.HYPOTHESIS,
        review_independence=ReviewIndependence.SELF_REVIEW,
        source_of_truth="spec:quarantined_phi_consciousness_memo",
        allowed_claim_types=(),
        forbidden_claim_types=("consciousness_proven", "sentience", "biological_advantage")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="hypotheses.physics.phase_conjugate_healing",
        namespace="hypotheses",
        title="Phase-Conjugate State Preservation Hypothesis",
        implementation_status=ImplementationStatus.PROPOSED,
        evidence_status=EvidenceStatus.NONE,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.HYPOTHESIS,
        review_independence=ReviewIndependence.SELF_REVIEW,
        source_of_truth="spec:phase_conjugate_memo",
        allowed_claim_types=(),
        forbidden_claim_types=("infinite_coherence", "hardware_proven")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="hypotheses.market.quantum_state_mapping",
        namespace="hypotheses",
        title="Quantum Hilbert Space to Financial Asset Mapping Hypothesis",
        implementation_status=ImplementationStatus.PROPOSED,
        evidence_status=EvidenceStatus.NONE,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.HYPOTHESIS,
        review_independence=ReviewIndependence.SELF_REVIEW,
        source_of_truth="spec:market_quantum_mapping_memo",
        allowed_claim_types=(),
        forbidden_claim_types=("arbitrage_guarantee", "operational_trading_authority")
    ))

    # Deprecated / Refuted Historical Claims (Errata Anchored)
    reg.register_capability(CapabilityRecord(
        capability_id="deprecated.quantum.tesseract_40q",
        namespace="deprecated",
        title="40-Qubit Tesseract Manifold Suppression Claim (Retracted)",
        implementation_status=ImplementationStatus.REFUTED,
        evidence_status=EvidenceStatus.UNRESOLVED,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.NO_CLAIM,
        review_independence=ReviewIndependence.INDEPENDENT_REVIEW,
        source_of_truth="doi:10.5281/zenodo.18209071",
        allowed_claim_types=(),
        forbidden_claim_types=("scientific_efficacy", "10^6_suppression", "quantum_advantage")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="deprecated.quantum.torsion_lock_156q",
        namespace="deprecated",
        title="156-Qubit Torsion Lock & 136-Bit Negentropy Gap (Retracted)",
        implementation_status=ImplementationStatus.REFUTED,
        evidence_status=EvidenceStatus.UNRESOLVED,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.NO_CLAIM,
        review_independence=ReviewIndependence.INDEPENDENT_REVIEW,
        source_of_truth="doi:10.5281/zenodo.19656600",
        allowed_claim_types=(),
        forbidden_claim_types=("negentropy_collapse", "torsion_lock_proven")
    ))

    reg.register_capability(CapabilityRecord(
        capability_id="deprecated.quantum.mock_xeb_days_1_4",
        namespace="deprecated",
        title="Day 1-4 Cross-Entropy Benchmarking Telemetry (Void Mock Artifact)",
        implementation_status=ImplementationStatus.DEPRECATED,
        evidence_status=EvidenceStatus.SIMULATED,
        deployment_authority=DeploymentAuthority.NONE,
        claim_ceiling=ClaimCeiling.NO_CLAIM,
        review_independence=ReviewIndependence.HUMAN_REVIEW,
        source_of_truth="audit:mock_backend_deviation_xeb_days_1_4",
        allowed_claim_types=(),
        forbidden_claim_types=("qpu_advantage", "p_value_statistical_significance")
    ))

    # Negative Controls (First-Class Evidence)
    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0001",
        original_claim="Microsecond timestamp modulo (microseconds % 46.0 µs) correlates with physical quantum processor coherence",
        refutation_method="TIMESTAMP_BURST_AUDIT",
        refutation_artifact="quantum_jobs_provenance_audit.md",
        lesson="Linux kernel socket buffering and IBM Cloud dispatch queues induce periodic time binning that mimics physical resonance.",
        disproven_patterns=("tau_phase", "46.0 us", "timestamp modulo", "tau resonance")
    ))

    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0002",
        original_claim="Bimodal phase transition observed at Phi = 0.7734 on IBM hardware",
        refutation_method="CIRCUIT_WIDTH_NORMALIZATION",
        refutation_artifact="quantum_jobs_provenance_audit.md",
        lesson="Evaluating 5q, 27q, and 127q circuits with a 2q Bell parity formula creates an artificial bimodal split between wide and narrow circuits.",
        disproven_patterns=("bimodal phase transition", "0.7734", "phi transition")
    ))

    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0003",
        original_claim="580 independent quantum hardware jobs executed",
        refutation_method="CORPUS_DEDUPLICATION_AUDIT",
        refutation_artifact="quantum_jobs_provenance_audit.md",
        lesson="Recursive ingestion across 4-6 mirrored upload folders duplicated 103 physical ibm_fez jobs up to 6 times each.",
        disproven_patterns=("580 quantum jobs", "580 independent runs")
    ))

    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0004",
        original_claim="Fractional Kelly criterion sizing guarantees portfolio survival",
        refutation_method="FAT_TAIL_SIMULATION",
        refutation_artifact="risk_research_memo_004.md",
        lesson="Gaussian assumptions fail in crypto/high-volatility regimes; exchange counterparty risk invalidates mathematical survival guarantees.",
        disproven_patterns=("kelly guarantees survival", "fractional kelly guarantee")
    ))

    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0005",
        original_claim="19.93-Bit Information Entropy Upper Bound as a Universal Physical Constant",
        refutation_method="FINITE_SAMPLING_ANALYSIS",
        refutation_artifact="quantum_jobs_provenance_audit.md",
        lesson="The measured entropy ceiling was strictly mathematical log2(shots) where shots = 1,000,000 (log2(10^6) = 19.93156 bits), representing a finite-sampling bound rather than a physical law.",
        disproven_patterns=("19.93-bit", "entropy upper bound", "universal memory constant")
    ))

    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0006",
        original_claim="Mentor benchmark heuristic evaluation guarantees model synthesis accuracy",
        refutation_method="BLIND_HELD_OUT_SYNTHESIS_TEST",
        refutation_artifact="mentor_benchmark_eval_2026.json",
        lesson="Self-evaluating models exhibit optimistic bias on synthesis tasks (0/3 pass rate on blind held-out tests); hidden test gating is mandatory.",
        disproven_patterns=("mentor benchmark passed", "self-evaluation guarantee", "0/3 pass rate promotion")
    ))

    reg.register_negative_control(NegativeControlRecord(
        claim_id="OCCR-NEG-0007",
        original_claim="Raw binary digest emission in IntentVectorizer is safe for text AST parsing",
        refutation_method="FUZZ_INPUT_ENCODING_AUDIT",
        refutation_artifact="intent_vectorizer_audit_log.json",
        lesson="Emitting raw binary digests without hexadecimal formatting introduces null bytes and utf-8 decoding exceptions in downstream AST parsers.",
        disproven_patterns=("raw binary intent digest", "unencoded sha256 bytes in ast")
    ))

    return reg
