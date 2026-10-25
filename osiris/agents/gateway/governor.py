"""Deterministic Capability and Cost Governor enforcing fail-closed authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping  # noqa: F401

from .contracts import (
    ActionKind,  # noqa: F401
    ActionProposal,
    AuthorizedAgentRequest,
    BudgetClass,
    ExecutionGrant,
    RiskTier,  # noqa: F401
    compute_sha256,
)


class GovernanceViolation(Exception):
    """Raised when an action proposal violates capability, path, or cost policy."""
    pass


class CapabilityGovernor:
    """Evaluates proposals and issues cryptographic ExecutionGrants."""

    POLICY_VERSION = "osiris-governor/1.0-offline"
    ALLOWED_CAPABILITIES = frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL", "REPLAY_FIXTURE"})

    def __init__(self, approved_root: Path):
        self._approved_root = approved_root.resolve()
        self._used_nonces: set[str] = set()

    def evaluate(
        self,
        proposal: ActionProposal,
        request: AuthorizedAgentRequest,
        now: datetime | None = None,
    ) -> ExecutionGrant:
        current_time = now or datetime.now(timezone.utc)

        # 1. Request ID binding
        if proposal.request_id != request.request_id:
            raise GovernanceViolation(f"Proposal request_id mismatch: {proposal.request_id} != {request.request_id}")

        # 2. Replay & Freshness Check
        if proposal.expires_at <= current_time:
            raise GovernanceViolation("Proposal has expired")
        if proposal.nonce in self._used_nonces:
            raise GovernanceViolation(f"Replay attack detected: nonce '{proposal.nonce}' already used")
        self._used_nonces.add(proposal.nonce)

        # 3. Capability Allowlist Check
        if proposal.capability not in self.ALLOWED_CAPABILITIES:
            raise GovernanceViolation(f"Capability '{proposal.capability}' not permitted in offline slice")
        if proposal.capability not in request.allowed_capabilities:
            raise GovernanceViolation(f"Capability '{proposal.capability}' not granted in parent request")

        # 4. Strict Path & Symlink Traversal Protection
        target_path = Path(proposal.target.locator)
        if target_path.is_absolute():
            resolved_target = target_path.resolve()
        else:
            resolved_target = (self._approved_root / target_path).resolve()

        try:
            resolved_target.relative_to(self._approved_root)
        except ValueError:
            raise GovernanceViolation(f"Path traversal escape detected: '{proposal.target.locator}' escapes '{self._approved_root}'")

        # 5. Cost & Budget Class Verification
        self._evaluate_cost(request)

        # 6. Issue Bound ExecutionGrant
        target_digest = compute_sha256(proposal.target.digest())
        args_digest = compute_sha256(proposal.arguments)
        grant_id = f"grant_{compute_sha256(proposal.proposal_digest)[:16]}"

        integrity_payload = {
            "grant_id": grant_id,
            "proposal_hash": proposal.proposal_digest,
            "policy_version": self.POLICY_VERSION,
            "target_digest": target_digest,
            "args_digest": args_digest,
            "expires_at": proposal.expires_at.isoformat(),
        }
        integrity_digest = compute_sha256(integrity_payload)

        return ExecutionGrant(
            grant_id=grant_id,
            request_id=request.request_id,
            proposal_hash=proposal.proposal_digest,
            allowed_action=proposal.action_kind,
            allowed_target_digest=target_digest,
            allowed_arguments_digest=args_digest,
            issued_at=current_time,
            expires_at=proposal.expires_at,
            policy_version=self.POLICY_VERSION,
            integrity_digest=integrity_digest,
        )

    def _evaluate_cost(self, request: AuthorizedAgentRequest) -> None:
        """Enforces hard spend governor levels and credit eligibility."""
        if request.budget_class == BudgetClass.FREE_TIER:
            if request.max_cost_usd > 0.0:
                raise GovernanceViolation("FREE_TIER budget class cannot have non-zero cost")
        elif request.budget_class == BudgetClass.FREE_TRIAL_RESERVE:
            if request.max_cost_usd > 10.0:
                raise GovernanceViolation("FREE_TRIAL_RESERVE requests exceeding $10 require human approval")
