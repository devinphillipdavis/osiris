"""
OSIRIS Capability & Claim Registry (OCCR) - Partial-Order Lattice Claim Engine
Version: 2.0.0 (Lattice & Multi-Dimensional Vector Model)
Author: Agile Defense Systems LLC / OSIRIS Sovereign Core
License: Proprietary / Sovereign Research Invariant

Key Invariants:
1. Partial Order over Scalar Hierarchy:
   Claims form a partially ordered set (Poset), not a total linear scalar.
   Orthogonal concerns (such as independent empirical replication vs production
   deployment authority) are never collapsed into an artificial scalar rank.

2. Incomparability as a First-Class State:
   Two claims or governance states that differ along non-dominating dimensions
   (e.g., Claim A: independent observation with no deployment; Claim B: authorized
   deployment with no independent observation) are explicitly INCOMPARABLE.
   Incomparability does NOT mean contradiction; it signifies that the governance
   model lacks an ordering between them.

3. Multi-Dimensional Governance Vector:
   System states and claim requirements are represented as vectors spanning:
   - implementation: DESIGN -> IMPLEMENTATION -> TESTED
   - evidence_provenance: NONE -> INTERNAL -> INDEPENDENT -> REPLICATED
   - evidence_scope: NONE -> BENCHMARK -> EXPERIMENTAL -> FIELD
   - deployment_scope: NONE -> SANDBOX -> STAGING -> PRODUCTION
   - deployment_authority: NONE -> READ_ONLY -> HUMAN_AUTHORIZED -> AUTONOMOUS
   - inference_level: HYPOTHESIS -> CORRELATION -> OBSERVED -> CAUSAL

4. Predicate-Based Adjudication:
   Each claim definition specifies predicates over the governance vector.
   A claim is admissible iff all required predicates hold and it is not prohibited
   by registered ceilings or policy boundaries.

5. Meet and Join Semantics:
   - MEET(A, B): Conservative intersection (greatest lower bound / infimum).
     Computes what survives both constraints simultaneously.
   - JOIN(A, B): Least upper bound (supremum).
     CRITICAL INVARIANT: Join is strictly informational and NEVER produces
     claim or execution authorization. Combining state A and state B cannot
     manufacture higher authorization without explicit verified evidence.

6. Admissible Frontier:
   The adjudicator does not compute max(A) because a unique maximum may not exist.
   Instead, it returns the maximal elements: Maximal(A(x)), exposing the frontier,
   incomparable pairs, and dimension-level blockers.
"""

from __future__ import annotations

import enum
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple


# ============================================================================
# 1. Dimension Partial Orders & Controlled Vocabularies
# ============================================================================

class PosetEnum(enum.Enum):
    """Base class for dimension enums with well-defined partial order comparison."""
    @classmethod
    def order_rank(cls, val: Any) -> int:
        raise NotImplementedError

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.order_rank(self) <= self.order_rank(other)

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.order_rank(self) < self.order_rank(other)

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.order_rank(self) >= self.order_rank(other)

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.order_rank(self) > self.order_rank(other)


class ImplementationLevel(PosetEnum):
    DESIGN = "DESIGN"
    IMPLEMENTATION = "IMPLEMENTATION"
    TESTED = "TESTED"

    @classmethod
    def order_rank(cls, val: ImplementationLevel) -> int:
        _RANKS = {cls.DESIGN: 0, cls.IMPLEMENTATION: 1, cls.TESTED: 2}
        return _RANKS[val]

    def implies(self) -> Tuple[ImplementationLevel, ...]:
        if self == ImplementationLevel.TESTED:
            return (ImplementationLevel.TESTED, ImplementationLevel.IMPLEMENTATION, ImplementationLevel.DESIGN)
        elif self == ImplementationLevel.IMPLEMENTATION:
            return (ImplementationLevel.IMPLEMENTATION, ImplementationLevel.DESIGN)
        return (ImplementationLevel.DESIGN,)


class EvidenceProvenance(PosetEnum):
    NONE = "NONE"
    INTERNAL = "INTERNAL"
    INDEPENDENT = "INDEPENDENT"
    REPLICATED = "REPLICATED"

    @classmethod
    def order_rank(cls, val: EvidenceProvenance) -> int:
        _RANKS = {cls.NONE: 0, cls.INTERNAL: 1, cls.INDEPENDENT: 2, cls.REPLICATED: 3}
        return _RANKS[val]

    def implies(self) -> Tuple[EvidenceProvenance, ...]:
        rank = self.order_rank(self)
        return tuple(p for p in EvidenceProvenance if self.order_rank(p) <= rank)


class EvidenceScope(PosetEnum):
    NONE = "NONE"
    BENCHMARK = "BENCHMARK"
    EXPERIMENTAL = "EXPERIMENTAL"
    FIELD = "FIELD"

    @classmethod
    def order_rank(cls, val: EvidenceScope) -> int:
        _RANKS = {cls.NONE: 0, cls.BENCHMARK: 1, cls.EXPERIMENTAL: 2, cls.FIELD: 3}
        return _RANKS[val]


class DeploymentScope(PosetEnum):
    NONE = "NONE"
    SANDBOX = "SANDBOX"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"

    @classmethod
    def order_rank(cls, val: DeploymentScope) -> int:
        _RANKS = {cls.NONE: 0, cls.SANDBOX: 1, cls.STAGING: 2, cls.PRODUCTION: 3}
        return _RANKS[val]


class DeploymentAuthority(PosetEnum):
    NONE = "NONE"
    READ_ONLY = "READ_ONLY"
    HUMAN_AUTHORIZED = "HUMAN_AUTHORIZED"
    AUTONOMOUS = "AUTONOMOUS"

    @classmethod
    def order_rank(cls, val: DeploymentAuthority) -> int:
        _RANKS = {cls.NONE: 0, cls.READ_ONLY: 1, cls.HUMAN_AUTHORIZED: 2, cls.AUTONOMOUS: 3}
        return _RANKS[val]


class InferenceLevel(PosetEnum):
    HYPOTHESIS = "HYPOTHESIS"
    CORRELATION = "CORRELATION"
    OBSERVED = "OBSERVED"
    CAUSAL = "CAUSAL"

    @classmethod
    def order_rank(cls, val: InferenceLevel) -> int:
        _RANKS = {cls.HYPOTHESIS: 0, cls.CORRELATION: 1, cls.OBSERVED: 2, cls.CAUSAL: 3}
        return _RANKS[val]


class RelationType(enum.Enum):
    EQUAL = "EQUAL"
    GREATER = "GREATER"          # self strictly dominates other
    LESS = "LESS"                # other strictly dominates self
    INCOMPARABLE = "INCOMPARABLE"  # neither dominates the other


class AdjudicationDecision(enum.Enum):
    PERMIT = "PERMIT"
    DOWNGRADE = "DOWNGRADE"
    DENY = "DENY"
    INCONCLUSIVE = "INCONCLUSIVE"
    INCOMPARABLE = "INCOMPARABLE"


# ============================================================================
# 2. Multi-Dimensional Governance Vector
# ============================================================================

@dataclass(frozen=True)
class GovernanceVector:
    """
    Multi-dimensional state vector representing empirical and operational status.
    Eliminates scalar collapse.
    """
    implementation: ImplementationLevel = ImplementationLevel.DESIGN
    evidence_provenance: EvidenceProvenance = EvidenceProvenance.NONE
    evidence_scope: EvidenceScope = EvidenceScope.NONE
    deployment_scope: DeploymentScope = DeploymentScope.NONE
    deployment_authority: DeploymentAuthority = DeploymentAuthority.NONE
    inference: InferenceLevel = InferenceLevel.HYPOTHESIS

    def dominates(self, other: GovernanceVector) -> bool:
        """Returns True iff self >= other in all 6 dimensions."""
        return (
            self.implementation >= other.implementation and
            self.evidence_provenance >= other.evidence_provenance and
            self.evidence_scope >= other.evidence_scope and
            self.deployment_scope >= other.deployment_scope and
            self.deployment_authority >= other.deployment_authority and
            self.inference >= other.inference
        )

    def is_dominated_by(self, other: GovernanceVector) -> bool:
        """Returns True iff other dominates self."""
        return other.dominates(self)

    def compare(self, other: GovernanceVector) -> RelationType:
        """
        Determines the formal lattice relationship between two vectors.
        Returns EQUAL, GREATER, LESS, or INCOMPARABLE.
        """
        if self == other:
            return RelationType.EQUAL
        
        self_dom = self.dominates(other)
        other_dom = other.dominates(self)

        if self_dom and not other_dom:
            return RelationType.GREATER
        elif other_dom and not self_dom:
            return RelationType.LESS
        else:
            return RelationType.INCOMPARABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "implementation": self.implementation.value,
            "evidence_provenance": self.evidence_provenance.value,
            "evidence_scope": self.evidence_scope.value,
            "deployment_scope": self.deployment_scope.value,
            "deployment_authority": self.deployment_authority.value,
            "inference": self.inference.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GovernanceVector:
        return cls(
            implementation=ImplementationLevel(data.get("implementation", "DESIGN")),
            evidence_provenance=EvidenceProvenance(data.get("evidence_provenance", "NONE")),
            evidence_scope=EvidenceScope(data.get("evidence_scope", "NONE")),
            deployment_scope=DeploymentScope(data.get("deployment_scope", "NONE")),
            deployment_authority=DeploymentAuthority(data.get("deployment_authority", "NONE")),
            inference=InferenceLevel(data.get("inference", "HYPOTHESIS")),
        )


# ============================================================================
# 3. Lattice Operations: Meet (Infimum) and Join (Supremum)
# ============================================================================

def vector_meet(v1: GovernanceVector, v2: GovernanceVector) -> GovernanceVector:
    """
    Meet (greatest lower bound / infimum) - Conservative Intersection.
    Calculates what survives both vectors simultaneously.
    """
    impl = v1.implementation if v1.implementation <= v2.implementation else v2.implementation
    prov = v1.evidence_provenance if v1.evidence_provenance <= v2.evidence_provenance else v2.evidence_provenance
    ev_scope = v1.evidence_scope if v1.evidence_scope <= v2.evidence_scope else v2.evidence_scope
    dep_scope = v1.deployment_scope if v1.deployment_scope <= v2.deployment_scope else v2.deployment_scope
    dep_auth = v1.deployment_authority if v1.deployment_authority <= v2.deployment_authority else v2.deployment_authority
    inf = v1.inference if v1.inference <= v2.inference else v2.inference

    return GovernanceVector(
        implementation=impl,
        evidence_provenance=prov,
        evidence_scope=ev_scope,
        deployment_scope=dep_scope,
        deployment_authority=dep_auth,
        inference=inf,
    )


def vector_join(v1: GovernanceVector, v2: GovernanceVector) -> GovernanceVector:
    """
    Join (least upper bound / supremum) - Informational Composite State.
    CRITICAL INVARIANT: Join is strictly informational and NEVER produces
    claim or execution authorization. Combining state A and state B cannot
    manufacture higher authorization without explicit verified evidence.
    """
    impl = v1.implementation if v1.implementation >= v2.implementation else v2.implementation
    prov = v1.evidence_provenance if v1.evidence_provenance >= v2.evidence_provenance else v2.evidence_provenance
    ev_scope = v1.evidence_scope if v1.evidence_scope >= v2.evidence_scope else v2.evidence_scope
    dep_scope = v1.deployment_scope if v1.deployment_scope >= v2.deployment_scope else v2.deployment_scope
    dep_auth = v1.deployment_authority if v1.deployment_authority >= v2.deployment_authority else v2.deployment_authority
    inf = v1.inference if v1.inference >= v2.inference else v2.inference

    return GovernanceVector(
        implementation=impl,
        evidence_provenance=prov,
        evidence_scope=ev_scope,
        deployment_scope=dep_scope,
        deployment_authority=dep_auth,
        inference=inf,
    )


# ============================================================================
# 4. Claim Definition & Predicate Specifications
# ============================================================================

@dataclass(frozen=True)
class ClaimDefinition:
    """
    Formal specification of a claim type as a predicate over GovernanceVector.
    """
    claim_id: str
    title: str
    description: str
    required_vector: GovernanceVector
    prohibited_namespaces: Tuple[str, ...] = ("hypotheses", "deprecated")
    evidence_status_required: Tuple[str, ...] = ()

    def check_predicate(self, state: GovernanceVector, namespace: str = "capabilities") -> Tuple[bool, List[str]]:
        """
        Evaluates whether governance state x satisfies R(c, x).
        Returns (is_admissible, list_of_blockers).
        """
        blockers: List[str] = []

        # Namespace quarantine check
        if namespace in self.prohibited_namespaces and self.claim_id != "HYPOTHESIS_ONLY":
            blockers.append(f"namespace_quarantine:{namespace}")

        # Vector dimension dominance checks
        if state.implementation < self.required_vector.implementation:
            blockers.append(
                f"implementation:{state.implementation.value}<{self.required_vector.implementation.value}"
            )
        if state.evidence_provenance < self.required_vector.evidence_provenance:
            blockers.append(
                f"evidence_provenance:{state.evidence_provenance.value}<{self.required_vector.evidence_provenance.value}"
            )
        if state.evidence_scope < self.required_vector.evidence_scope:
            blockers.append(
                f"evidence_scope:{state.evidence_scope.value}<{self.required_vector.evidence_scope.value}"
            )
        if state.deployment_scope < self.required_vector.deployment_scope:
            blockers.append(
                f"deployment_scope:{state.deployment_scope.value}<{self.required_vector.deployment_scope.value}"
            )
        if state.deployment_authority < self.required_vector.deployment_authority:
            blockers.append(
                f"deployment_authority:{state.deployment_authority.value}<{self.required_vector.deployment_authority.value}"
            )
        if state.inference < self.required_vector.inference:
            blockers.append(
                f"inference_requirement:{state.inference.value}<{self.required_vector.inference.value}"
            )

        return (len(blockers) == 0, blockers)


# Standard OSIRIS Governed Claim Types
STANDARD_CLAIMS: Dict[str, ClaimDefinition] = {
    "HYPOTHESIS_ONLY": ClaimDefinition(
        claim_id="HYPOTHESIS_ONLY",
        title="Theoretical Hypothesis",
        description="Theoretical or mathematical model; zero empirical efficacy or operational claim.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.DESIGN,
            inference=InferenceLevel.HYPOTHESIS
        ),
        prohibited_namespaces=()  # Permitted everywhere including hypotheses/
    ),
    "DESIGN_SPECIFICATION": ClaimDefinition(
        claim_id="DESIGN_SPECIFICATION",
        title="Design Specification",
        description="Formal architectural and interface specification.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.DESIGN,
            inference=InferenceLevel.HYPOTHESIS
        )
    ),
    "IMPLEMENTED_INTERFACE": ClaimDefinition(
        claim_id="IMPLEMENTED_INTERFACE",
        title="Implemented Interface",
        description="Executable code and AST syntax implemented; no functional efficacy claimed.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.IMPLEMENTATION,
            inference=InferenceLevel.HYPOTHESIS
        )
    ),
    "TESTED_BEHAVIOR": ClaimDefinition(
        claim_id="TESTED_BEHAVIOR",
        title="Tested Deterministic Behavior",
        description="Passes internal unit and integration test assertions.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            evidence_provenance=EvidenceProvenance.INTERNAL,
            inference=InferenceLevel.HYPOTHESIS
        )
    ),
    "INDEPENDENT_OBSERVATION": ClaimDefinition(
        claim_id="INDEPENDENT_OBSERVATION",
        title="Independent Empirical Observation",
        description="Empirical hardware measurement verified by independent test runner or harness.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            evidence_provenance=EvidenceProvenance.INDEPENDENT,
            evidence_scope=EvidenceScope.EXPERIMENTAL,
            inference=InferenceLevel.OBSERVED
        )
    ),
    "AUTHORIZED_DEPLOYMENT": ClaimDefinition(
        claim_id="AUTHORIZED_DEPLOYMENT",
        title="Authorized Deployment",
        description="Execution approved for sandbox or staging with human authority token.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            deployment_scope=DeploymentScope.SANDBOX,
            deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED
        )
    ),
    "REPLICATED_OBSERVATION": ClaimDefinition(
        claim_id="REPLICATED_OBSERVATION",
        title="Replicated Empirical Observation",
        description="Replicated across independent hardware chips, sessions, or calibration epochs.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            evidence_provenance=EvidenceProvenance.REPLICATED,
            evidence_scope=EvidenceScope.EXPERIMENTAL,
            inference=InferenceLevel.OBSERVED
        )
    ),
    "DEPLOYED_OBSERVATION": ClaimDefinition(
        claim_id="DEPLOYED_OBSERVATION",
        title="Deployed In-Situ Observation",
        description="Empirical observations gathered in authorized staging/production runtime.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            evidence_provenance=EvidenceProvenance.INDEPENDENT,
            evidence_scope=EvidenceScope.FIELD,
            deployment_scope=DeploymentScope.STAGING,
            deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED,
            inference=InferenceLevel.OBSERVED
        )
    ),
    "CAUSAL_EFFECT": ClaimDefinition(
        claim_id="CAUSAL_EFFECT",
        title="Validated Causal Effect",
        description="Counterfactual or interventionally validated causal efficacy across replicates.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            evidence_provenance=EvidenceProvenance.REPLICATED,
            evidence_scope=EvidenceScope.EXPERIMENTAL,
            inference=InferenceLevel.CAUSAL
        )
    ),
    "CAUSAL_DEPLOYED_EFFICACY": ClaimDefinition(
        claim_id="CAUSAL_DEPLOYED_EFFICACY",
        title="Causal Deployed Efficacy",
        description="Causally validated efficacy operating in live authorized production.",
        required_vector=GovernanceVector(
            implementation=ImplementationLevel.TESTED,
            evidence_provenance=EvidenceProvenance.REPLICATED,
            evidence_scope=EvidenceScope.FIELD,
            deployment_scope=DeploymentScope.PRODUCTION,
            deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED,
            inference=InferenceLevel.CAUSAL
        )
    )
}


# ============================================================================
# 5. Claim Ceiling Sets & Admissible Frontier Mathematics
# ============================================================================

@dataclass(frozen=True)
class ClaimCeilingSet:
    """
    Replaces scalar ClaimCeiling with an explicit set-based ceiling and frontier.
    """
    permitted_claims: Tuple[str, ...]
    prohibited_claims: Tuple[str, ...] = ()
    custom_policy_notes: Tuple[str, ...] = ()

    def is_claim_permitted(self, claim_id: str) -> Tuple[bool, Optional[str]]:
        if claim_id in self.prohibited_claims:
            return (False, f"claim_explicitly_prohibited_by_ceiling:{claim_id}")
        if self.permitted_claims and claim_id not in self.permitted_claims:
            return (False, f"claim_not_in_permitted_ceiling_set:{claim_id}")
        return (True, None)


def compute_claim_dominance(c1: ClaimDefinition, c2: ClaimDefinition) -> RelationType:
    """
    Determines whether Claim 1 dominates Claim 2 based on required vectors.
    c1 dominates c2 (c1 >= c2) means satisfying c1 strictly implies satisfying c2.
    """
    return c1.required_vector.compare(c2.required_vector)


def compute_admissible_frontier(
    admissible_claim_ids: Set[str],
    registry: Dict[str, ClaimDefinition]
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Calculates the Maximal elements (Admissible Frontier) of a set of admissible claims.
    Maximal(A) = { c in A | not exists c' in A such that c' > c }

    Also returns all pairs of mutually incomparable claims within the frontier.
    """
    claims = [registry[cid] for cid in admissible_claim_ids if cid in registry]
    maximal: List[ClaimDefinition] = []

    for c in claims:
        is_dominated = False
        for other in claims:
            if c.claim_id == other.claim_id:
                continue
            # If 'other' strictly dominates 'c' (other > c), then c is not maximal
            if other.required_vector.dominates(c.required_vector) and other.required_vector != c.required_vector:
                is_dominated = True
                break
        if not is_dominated:
            maximal.append(c)

    frontier_ids = sorted([c.claim_id for c in maximal])

    # Identify incomparable pairs on the frontier
    incomparable_pairs: List[Tuple[str, str]] = []
    for i in range(len(maximal)):
        for j in range(i + 1, len(maximal)):
            c1, c2 = maximal[i], maximal[j]
            rel = c1.required_vector.compare(c2.required_vector)
            if rel == RelationType.INCOMPARABLE:
                incomparable_pairs.append((c1.claim_id, c2.claim_id))

    return (frontier_ids, incomparable_pairs)


# ============================================================================
# 6. Adjudication Report & Lattice Adjudicator Engine
# ============================================================================

@dataclass(frozen=True)
class AdjudicationReport:
    """
    Comprehensive structured adjudication result returned by the LatticeClaimAdjudicator.
    """
    requested_claim: str
    decision: AdjudicationDecision
    is_permitted: bool
    current_state: GovernanceVector
    admissible_claims: Tuple[str, ...]
    admissible_frontier: Tuple[str, ...]
    incomparable_pairs: Tuple[Tuple[str, str], ...]
    blocked_claims: Dict[str, List[str]]
    reasons: Tuple[str, ...]
    downgrade_candidates: Tuple[str, ...] = ()
    receipt_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested_claim": self.requested_claim,
            "decision": self.decision.value,
            "is_permitted": self.is_permitted,
            "current_state": self.current_state.to_dict(),
            "admissible_claims": list(self.admissible_claims),
            "admissible_frontier": list(self.admissible_frontier),
            "incomparable_pairs": [list(pair) for pair in self.incomparable_pairs],
            "blocked_claims": self.blocked_claims,
            "reasons": list(self.reasons),
            "downgrade_candidates": list(self.downgrade_candidates),
            "receipt_hash": self.receipt_hash
        }


class LatticeClaimAdjudicator:
    """
    Lattice-Based OCCR Claim Adjudicator.
    Implements formal partial-order predicate satisfaction over GovernanceVector.
    """

    def __init__(self, registry: Optional[Dict[str, ClaimDefinition]] = None):
        self.registry: Dict[str, ClaimDefinition] = dict(registry or STANDARD_CLAIMS)

    def register_claim(self, claim: ClaimDefinition) -> None:
        self.registry[claim.claim_id] = claim

    def adjudicate(
        self,
        requested_claim_id: str,
        current_state: GovernanceVector,
        registered_ceiling: Optional[ClaimCeilingSet] = None,
        namespace: str = "capabilities",
        negative_controls: Optional[List[str]] = None
    ) -> AdjudicationReport:
        """
        Adjudicates a requested claim against current empirical/governance state.
        Computes the full admissible set A(x), maximal elements, and blocker diagnostics.
        """
        reasons: List[str] = []
        admissible_set: Set[str] = set()
        blocked_dict: Dict[str, List[str]] = {}

        # 1. Evaluate all claims in registry to compute A(x) and blockers
        for cid, cdef in self.registry.items():
            ok_pred, blockers = cdef.check_predicate(current_state, namespace=namespace)
            
            # Check ceiling constraints if provided
            if registered_ceiling:
                ok_ceil, ceil_blocker = registered_ceiling.is_claim_permitted(cid)
                if not ok_ceil and ceil_blocker:
                    blockers.append(ceil_blocker)

            if len(blockers) == 0:
                admissible_set.add(cid)
            else:
                blocked_dict[cid] = blockers

        # 2. Compute the maximal elements (Admissible Frontier) and incomparable pairs
        frontier, incomparable_pairs = compute_admissible_frontier(admissible_set, self.registry)

        # 3. Check requested claim
        if requested_claim_id not in self.registry:
            reasons.append(f"Requested claim '{requested_claim_id}' is unknown in the claim registry.")
            return AdjudicationReport(
                requested_claim=requested_claim_id,
                decision=AdjudicationDecision.DENY,
                is_permitted=False,
                current_state=current_state,
                admissible_claims=tuple(sorted(admissible_set)),
                admissible_frontier=tuple(frontier),
                incomparable_pairs=tuple(incomparable_pairs),
                blocked_claims=blocked_dict,
                reasons=tuple(reasons)
            )

        req_def = self.registry[requested_claim_id]
        is_requested_admissible = requested_claim_id in admissible_set

        # Check negative controls refutation
        if negative_controls and requested_claim_id in negative_controls:
            reasons.append(f"Requested claim '{requested_claim_id}' is refuted by active negative controls.")
            is_requested_admissible = False
            if requested_claim_id in admissible_set:
                admissible_set.remove(requested_claim_id)
            blocked_dict[requested_claim_id] = ["refuted_by_negative_control"]

        if is_requested_admissible:
            decision = AdjudicationDecision.PERMIT
            reasons.append(
                f"Requested claim '{requested_claim_id}' satisfies all vector predicate requirements."
            )
            downgrades: Tuple[str, ...] = ()
        else:
            # Determine whether this is a DOWNGRADE candidate or outright DENY
            # A downgrade candidate is an admissible claim that the requested claim implies
            downgrade_candidates = [
                cid for cid in frontier 
                if req_def.required_vector.dominates(self.registry[cid].required_vector) and cid != requested_claim_id
            ]
            
            if downgrade_candidates:
                decision = AdjudicationDecision.DOWNGRADE
                reasons.append(
                    f"Requested claim '{requested_claim_id}' blocked by: {', '.join(blocked_dict.get(requested_claim_id, []))}. "
                    f"Admissible frontier offers valid downgrades: {downgrade_candidates}."
                )
                downgrades = tuple(downgrade_candidates)
            else:
                decision = AdjudicationDecision.DENY
                reasons.append(
                    f"Requested claim '{requested_claim_id}' denied. Blockers: {', '.join(blocked_dict.get(requested_claim_id, []))}."
                )
                downgrades = ()

        # Compute cryptographic receipt hash
        raw_receipt = f"{requested_claim_id}:{decision.value}:{','.join(frontier)}:{time.time():.3f}"
        receipt_hash = hashlib.sha256(raw_receipt.encode("utf-8")).hexdigest()

        return AdjudicationReport(
            requested_claim=requested_claim_id,
            decision=decision,
            is_permitted=(decision == AdjudicationDecision.PERMIT),
            current_state=current_state,
            admissible_claims=tuple(sorted(admissible_set)),
            admissible_frontier=tuple(frontier),
            incomparable_pairs=tuple(incomparable_pairs),
            blocked_claims=blocked_dict,
            reasons=tuple(reasons),
            downgrade_candidates=downgrades,
            receipt_hash=receipt_hash
        )

    def compare_claims(self, claim_id_1: str, claim_id_2: str) -> Dict[str, Any]:
        """
        Exposes formal relationship between any two claims.
        """
        if claim_id_1 not in self.registry or claim_id_2 not in self.registry:
            raise KeyError(f"Claims must exist in registry: {claim_id_1}, {claim_id_2}")
        
        c1 = self.registry[claim_id_1]
        c2 = self.registry[claim_id_2]
        rel = c1.required_vector.compare(c2.required_vector)

        reasons = []
        if rel == RelationType.INCOMPARABLE:
            reasons.append(
                f"Claim '{claim_id_1}' and '{claim_id_2}' occupy orthogonal dimensions; "
                f"neither required vector dominates the other."
            )
        elif rel == RelationType.GREATER:
            reasons.append(f"Claim '{claim_id_1}' strictly dominates claim '{claim_id_2}'.")
        elif rel == RelationType.LESS:
            reasons.append(f"Claim '{claim_id_2}' strictly dominates claim '{claim_id_1}'.")
        else:
            reasons.append(f"Claim '{claim_id_1}' and '{claim_id_2}' have identical required vectors.")

        return {
            "claim_1": claim_id_1,
            "claim_2": claim_id_2,
            "relation": rel.value,
            "is_incomparable": (rel == RelationType.INCOMPARABLE),
            "reasons": reasons
        }
