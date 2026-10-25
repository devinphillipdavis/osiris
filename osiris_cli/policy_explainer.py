"""
OSIRIS Policy Explainer
=======================

Translates OCCR gate rules, customer tiers, and invariant constraints into clear human-readable explanations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional  # noqa: F401

from occr_governance_engine import (
    ClaimCeiling,  # noqa: F401
    CustomerTier,  # noqa: F401
    DeploymentAuthority,  # noqa: F401
    EvidenceStatus,  # noqa: F401
    ImplementationStatus,  # noqa: F401
    ReviewIndependence,  # noqa: F401
    get_occr_registry,
)


class PolicyExplainer:
    """Explains why an action is allowed, blocked, or requires human authorization."""

    def __init__(self):
        self.registry = get_occr_registry()

    def explain_capability(self, capability_id: str) -> Dict[str, Any]:
        cap = self.registry.get_capability(capability_id)
        if not cap:
            return {"status": "NOT_FOUND", "message": f"No capability registered with ID '{capability_id}'."}

        tier = self.registry.project_customer_tier(cap.capability_id)
        return {
            "capability_id": cap.capability_id,
            "title": cap.title,
            "implementation_status": cap.implementation_status.name,
            "evidence_status": cap.evidence_status.name,
            "deployment_authority": cap.deployment_authority.name,
            "claim_ceiling": cap.claim_ceiling.name,
            "review_independence": cap.review_independence.name,
            "customer_tier": tier.name,
            "summary": (
                f"Capability '{cap.title}' has implementation status {cap.implementation_status.name} "
                f"with evidence {cap.evidence_status.name}. Deployment authority is {cap.deployment_authority.name}. "
                f"It qualifies for Customer Exposure Tier: {tier.name}."
            )
        }

    def explain_forbidden_effect(self, effect_name: str) -> str:
        rules = {
            "qpu": "Quantum hardware dispatch is blocked by default. Requires physical hardware token verified by ExecutionGate.",
            "publish": "External publishing (Zenodo, arXiv, etc.) is blocked by ReleaseGate. Self-review cannot authorize external releases.",
            "mutation": "Automated codebase mutation outside isolated disposable workspaces is strictly forbidden.",
            "claim": "Model-generated proposals cannot claim higher than HYPOTHESIS. Simulation runs are capped at TESTED.",
        }
        for k, v in rules.items():
            if k in effect_name.lower():
                return v
        return "Action is subject to OCCR 3-Gate Control Plane and fails closed by default."
