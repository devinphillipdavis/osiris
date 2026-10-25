"""
Unit and Invariant Verification Suite for occr_claim_lattice.py
Tests:
- Partial order properties over dimensions (reflexivity, antisymmetry, transitivity)
- GovernanceVector dominance and comparability relations
- Incomparability as a first-class mathematical state
- Meet (conservative intersection) and Join (informational least upper bound) semantics
- Invariant: Join never manufactures unearned authorization
- Admissible set A(x) and Maximal(A(x)) frontier calculation
- Adjudication logic: PERMIT, DOWNGRADE, DENY, and granular blocker attribution
- Namespace quarantine enforcement (hypotheses/ namespace locks)
- Explicit incomparability between orthogonal claims (INDEPENDENT_OBSERVATION vs AUTHORIZED_DEPLOYMENT)
"""

import pytest
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from occr_claim_lattice import (
    ImplementationLevel,
    EvidenceProvenance,
    EvidenceScope,
    DeploymentScope,
    DeploymentAuthority,
    InferenceLevel,
    RelationType,
    AdjudicationDecision,
    GovernanceVector,
    ClaimDefinition,
    ClaimCeilingSet,
    LatticeClaimAdjudicator,
    STANDARD_CLAIMS,
    vector_meet,
    vector_join,
    compute_admissible_frontier
)


# ============================================================================
# 1. Partial Order & Dimension Invariants
# ============================================================================

def test_dimension_poset_properties():
    # Implementation dimension
    assert ImplementationLevel.DESIGN < ImplementationLevel.IMPLEMENTATION
    assert ImplementationLevel.IMPLEMENTATION < ImplementationLevel.TESTED
    assert ImplementationLevel.TESTED >= ImplementationLevel.DESIGN

    # Evidence Provenance dimension
    assert EvidenceProvenance.NONE < EvidenceProvenance.INTERNAL
    assert EvidenceProvenance.INTERNAL < EvidenceProvenance.INDEPENDENT
    assert EvidenceProvenance.INDEPENDENT < EvidenceProvenance.REPLICATED

    # Deployment Authority dimension
    assert DeploymentAuthority.NONE < DeploymentAuthority.READ_ONLY
    assert DeploymentAuthority.READ_ONLY < DeploymentAuthority.HUMAN_AUTHORIZED
    assert DeploymentAuthority.HUMAN_AUTHORIZED < DeploymentAuthority.AUTONOMOUS


def test_vector_dominance_and_strict_order():
    v_base = GovernanceVector(
        implementation=ImplementationLevel.DESIGN,
        evidence_provenance=EvidenceProvenance.NONE
    )
    v_tested = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INTERNAL
    )

    assert v_tested.dominates(v_base)
    assert not v_base.dominates(v_tested)
    assert v_tested.compare(v_base) == RelationType.GREATER
    assert v_base.compare(v_tested) == RelationType.LESS


# ============================================================================
# 2. Incomparability as First-Class State
# ============================================================================

def test_orthogonal_vectors_are_strictly_incomparable():
    """
    Claim A: Independent evidence, no deployment authority.
    Claim B: Authorized deployment, internal-only evidence.
    NEITHER dominates the other.
    """
    v_empirical = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INDEPENDENT,
        deployment_authority=DeploymentAuthority.NONE
    )
    v_deployment = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INTERNAL,
        deployment_scope=DeploymentScope.SANDBOX,
        deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED
    )

    assert not v_empirical.dominates(v_deployment)
    assert not v_deployment.dominates(v_empirical)
    assert v_empirical.compare(v_deployment) == RelationType.INCOMPARABLE
    assert v_deployment.compare(v_empirical) == RelationType.INCOMPARABLE


def test_claim_comparison_exposes_incomparability():
    adjudicator = LatticeClaimAdjudicator()
    res = adjudicator.compare_claims("INDEPENDENT_OBSERVATION", "AUTHORIZED_DEPLOYMENT")

    assert res["relation"] == "INCOMPARABLE"
    assert res["is_incomparable"] is True
    assert "orthogonal dimensions" in res["reasons"][0]


# ============================================================================
# 3. Meet & Join Semantics
# ============================================================================

def test_meet_semantics_conservative_intersection():
    """
    Evidence permits: OBSERVED, INDEPENDENT, but NO deployment.
    Deployment permits: SANDBOX, HUMAN_AUTHORIZED, but only INTERNAL evidence.
    MEET = conservative intersection that survives both constraints.
    """
    v_evidence = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INDEPENDENT,
        evidence_scope=EvidenceScope.EXPERIMENTAL,
        deployment_scope=DeploymentScope.NONE,
        deployment_authority=DeploymentAuthority.NONE,
        inference=InferenceLevel.OBSERVED
    )
    v_deployment = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INTERNAL,
        evidence_scope=EvidenceScope.BENCHMARK,
        deployment_scope=DeploymentScope.SANDBOX,
        deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED,
        inference=InferenceLevel.HYPOTHESIS
    )

    v_meet = vector_meet(v_evidence, v_deployment)

    assert v_meet.implementation == ImplementationLevel.TESTED
    assert v_meet.evidence_provenance == EvidenceProvenance.INTERNAL
    assert v_meet.evidence_scope == EvidenceScope.BENCHMARK
    assert v_meet.deployment_scope == DeploymentScope.NONE
    assert v_meet.deployment_authority == DeploymentAuthority.NONE
    assert v_meet.inference == InferenceLevel.HYPOTHESIS

    # Both parent vectors must dominate the meet
    assert v_evidence.dominates(v_meet)
    assert v_deployment.dominates(v_meet)


def test_join_semantics_informational_composite_only():
    """
    JOIN(A, B) produces the least upper bound, but must NEVER automatically
    grant an unearned composite authorization.
    """
    v1 = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INDEPENDENT,
        inference=InferenceLevel.OBSERVED
    )
    v2 = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        deployment_scope=DeploymentScope.STAGING,
        deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED
    )

    v_join = vector_join(v1, v2)

    assert v_join.dominates(v1)
    assert v_join.dominates(v2)
    assert v_join.evidence_provenance == EvidenceProvenance.INDEPENDENT
    assert v_join.deployment_authority == DeploymentAuthority.HUMAN_AUTHORIZED

    # However, an adjudicator given ONLY v1 does NOT permit DEPLOYED_OBSERVATION
    adjudicator = LatticeClaimAdjudicator()
    rep = adjudicator.adjudicate("DEPLOYED_OBSERVATION", current_state=v1)
    assert not rep.is_permitted
    assert rep.decision in (AdjudicationDecision.DOWNGRADE, AdjudicationDecision.DENY)


# ============================================================================
# 4. Admissible Set & Frontier Mathematics
# ============================================================================

def test_admissible_frontier_calculation():
    """
    If a system satisfies both INDEPENDENT_OBSERVATION and AUTHORIZED_DEPLOYMENT,
    the frontier should contain BOTH claims as maximal elements (incomparable).
    """
    state = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INDEPENDENT,
        evidence_scope=EvidenceScope.EXPERIMENTAL,
        deployment_scope=DeploymentScope.SANDBOX,
        deployment_authority=DeploymentAuthority.HUMAN_AUTHORIZED,
        inference=InferenceLevel.OBSERVED
    )

    adjudicator = LatticeClaimAdjudicator()
    rep = adjudicator.adjudicate("INDEPENDENT_OBSERVATION", current_state=state)

    assert rep.is_permitted
    assert "INDEPENDENT_OBSERVATION" in rep.admissible_frontier
    assert "AUTHORIZED_DEPLOYMENT" in rep.admissible_frontier
    
    # Verify that the two maximal claims are recognized as incomparable
    found_incomparable_pair = any(
        ("AUTHORIZED_DEPLOYMENT" in pair and "INDEPENDENT_OBSERVATION" in pair)
        for pair in rep.incomparable_pairs
    )
    assert found_incomparable_pair is True


# ============================================================================
# 5. Adjudication Logic & Blocker Attribution
# ============================================================================

def test_adjudication_downgrade_with_granular_blockers():
    """
    Request CAUSAL_DEPLOYED_EFFICACY when system only has tested lab evidence.
    Adjudicator must DOWNGRADE to admissible frontier and cite exact missing dimensions.
    """
    state = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.INTERNAL,
        inference=InferenceLevel.HYPOTHESIS
    )

    adjudicator = LatticeClaimAdjudicator()
    rep = adjudicator.adjudicate("CAUSAL_DEPLOYED_EFFICACY", current_state=state)

    assert not rep.is_permitted
    assert rep.decision == AdjudicationDecision.DOWNGRADE
    assert "TESTED_BEHAVIOR" in rep.downgrade_candidates

    # Granular blockers must detail all deficiencies
    blockers = rep.blocked_claims["CAUSAL_DEPLOYED_EFFICACY"]
    assert any("evidence_provenance" in b for b in blockers)
    assert any("deployment_scope" in b for b in blockers)
    assert any("deployment_authority" in b for b in blockers)
    assert any("inference_requirement" in b for b in blockers)


def test_quarantined_namespace_rejection():
    """
    Items in 'hypotheses' namespace may only claim HYPOTHESIS_ONLY.
    All higher claims are fail-closed blocked.
    """
    state = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.REPLICATED,
        inference=InferenceLevel.CAUSAL
    )

    adjudicator = LatticeClaimAdjudicator()
    rep = adjudicator.adjudicate(
        "TESTED_BEHAVIOR",
        current_state=state,
        namespace="hypotheses"
    )

    assert not rep.is_permitted
    assert rep.decision == AdjudicationDecision.DOWNGRADE
    assert "namespace_quarantine:hypotheses" in rep.blocked_claims["TESTED_BEHAVIOR"]
    assert "HYPOTHESIS_ONLY" in rep.admissible_frontier


def test_registered_ceiling_set_enforcement():
    """
    Ceiling expressed as an explicit set of permitted/prohibited claims.
    """
    state = GovernanceVector(
        implementation=ImplementationLevel.TESTED,
        evidence_provenance=EvidenceProvenance.REPLICATED,
        evidence_scope=EvidenceScope.EXPERIMENTAL,
        inference=InferenceLevel.OBSERVED
    )

    ceiling = ClaimCeilingSet(
        permitted_claims=("TESTED_BEHAVIOR", "INDEPENDENT_OBSERVATION"),
        prohibited_claims=("REPLICATED_OBSERVATION", "CAUSAL_EFFECT")
    )

    adjudicator = LatticeClaimAdjudicator()
    rep = adjudicator.adjudicate(
        "REPLICATED_OBSERVATION",
        current_state=state,
        registered_ceiling=ceiling
    )

    assert not rep.is_permitted
    assert any("claim_explicitly_prohibited_by_ceiling" in b for b in rep.blocked_claims["REPLICATED_OBSERVATION"])
    assert "INDEPENDENT_OBSERVATION" in rep.admissible_frontier
