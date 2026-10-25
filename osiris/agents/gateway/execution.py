"""Inline governed execution: propose -> (human approval) -> grant -> verify -> execute.

``AgentGateway.process`` evaluates proposals *after* an adapter returns. Tool-using
agents cannot work that way: each tool result feeds the next model step, so every
call must be authorized inline. ``GovernedExecutor`` is that inline path, and it
uses the same ``CapabilityGovernor`` and the same ``ActionProposal`` /
``ExecutionGrant`` contracts, so nothing executes on a weaker check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

from .contracts import (
    ActionKind,
    ActionProposal,
    ActionTarget,
    AuthorizedAgentRequest,
    ExecutionGrant,
    HumanApproval,
    ProposalProvenance,
)
from .governor import CapabilityGovernor, GovernanceViolation

#: ``approver(proposal, description) -> HumanApproval | None``. Returning ``None``
#: is a denial. The default when no approver is wired is to deny.
Approver = Callable[[ActionProposal, str], Optional[HumanApproval]]

DEFAULT_PROPOSAL_TTL_S = 120.0


def build_proposal(
    *,
    request: AuthorizedAgentRequest,
    capability: str,
    locator: str,
    arguments: Mapping[str, Any],
    proposer_id: str,
    provider: str,
    backend: str = "local",
    model: Optional[str] = None,
    resource_type: str = "file",
    content_digest: Optional[str] = None,
    evidence_refs: tuple = (),
    ttl_s: float = DEFAULT_PROPOSAL_TTL_S,
    now: Optional[datetime] = None,
) -> ActionProposal:
    """Build a fresh single-use proposal (new nonce) bound to ``request``."""
    created = now or datetime.now(timezone.utc)
    nonce = uuid.uuid4().hex
    return ActionProposal(
        proposal_id=f"prop_{nonce[:16]}",
        request_id=request.request_id,
        proposer_id=proposer_id,
        action_kind=ActionKind(capability),
        capability=capability,
        target=ActionTarget(
            resource_type=resource_type,
            locator=locator,
            content_digest=content_digest,
        ),
        arguments=dict(arguments),
        provenance=ProposalProvenance(
            proposer_id=proposer_id,
            provider=provider,
            backend=backend,
            model=model,
            session_id=request.session_id,
            route_ref=f"{provider}:{capability}",
        ),
        evidence_refs=tuple(evidence_refs),
        created_at=created,
        expires_at=created + timedelta(seconds=ttl_s),
        nonce=nonce,
    )


@dataclass(frozen=True)
class GovernanceDecision:
    """Outcome of one authorization attempt, safe to log and render."""
    capability: str
    locator: str
    decision: str  # GRANTED | DENIED
    proposal_digest: str
    grant_id: Optional[str] = None
    approval_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def granted(self) -> bool:
        return self.decision == "GRANTED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "locator": self.locator,
            "decision": self.decision,
            "proposal_digest": self.proposal_digest,
            "grant_id": self.grant_id,
            "approval_id": self.approval_id,
            "reason": self.reason,
        }


@dataclass
class GovernedExecutor:
    """Authorizes individual actions against a governor, recording every decision."""
    governor: CapabilityGovernor
    proposer_id: str
    provider: str
    approver: Optional[Approver] = None
    model: Optional[str] = None
    ledger: List[GovernanceDecision] = field(default_factory=list)

    def authorize(
        self,
        request: AuthorizedAgentRequest,
        capability: str,
        locator: str,
        arguments: Mapping[str, Any],
        description: str,
        *,
        resource_type: str = "file",
        content_digest: Optional[str] = None,
    ) -> "tuple[GovernanceDecision, Optional[ActionProposal], Optional[ExecutionGrant]]":
        """Propose, collect a human approval when the tier needs one, and evaluate.

        Returns the decision plus, on success, the proposal and grant the caller
        must hand to ``governor.verify_grant`` immediately before acting.
        """
        try:
            proposal = build_proposal(
                request=request,
                capability=capability,
                locator=locator,
                arguments=arguments,
                proposer_id=self.proposer_id,
                provider=self.provider,
                model=self.model,
                resource_type=resource_type,
                content_digest=content_digest,
            )
        except ValueError as exc:  # unknown ActionKind
            decision = GovernanceDecision(capability, locator, "DENIED", "", reason=str(exc))
            self.ledger.append(decision)
            return decision, None, None

        approval: Optional[HumanApproval] = None
        if (
            self.governor.requires_human_approval(capability)
            and capability in request.allowed_capabilities
        ):
            # Only ask a human about actions the request scope could ever allow;
            # out-of-scope actions are refused by the governor without a prompt.
            approval = self.approver(proposal, description) if self.approver else None

        try:
            grant = self.governor.evaluate(proposal, request, approval=approval)
        except GovernanceViolation as exc:
            reason = str(exc)
            if approval is None and self.governor.requires_human_approval(capability):
                if capability in request.allowed_capabilities:
                    reason = f"{reason} (no human approval given)"
            decision = GovernanceDecision(
                capability, locator, "DENIED", proposal.proposal_digest, reason=reason,
                approval_id=approval.approval_id if approval else None,
            )
            self.ledger.append(decision)
            return decision, proposal, None

        decision = GovernanceDecision(
            capability, locator, "GRANTED", proposal.proposal_digest,
            grant_id=grant.grant_id,
            approval_id=approval.approval_id if approval else None,
        )
        self.ledger.append(decision)
        return decision, proposal, grant
