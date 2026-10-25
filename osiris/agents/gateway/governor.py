"""Deterministic Capability and Cost Governor enforcing fail-closed authorization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from .contracts import (
    ActionProposal,
    AuthorizedAgentRequest,
    BudgetClass,
    ExecutionGrant,
    HumanApproval,
    RiskTier,
    compute_sha256,
)


class GovernanceViolation(Exception):
    """Raised when an action proposal violates capability, path, or cost policy."""
    pass


class CapabilityGovernor:
    """Evaluates proposals and issues cryptographic ExecutionGrants."""

    POLICY_VERSION = "osiris-governor/1.1-local"

    #: Every capability the governor can ever grant, with its risk tier. Anything
    #: absent from this table is refused outright.
    CAPABILITY_TIERS: Mapping[str, RiskTier] = {
        "READ_ONLY_ANALYSIS": RiskTier.TIER_0_NO_RISK,
        "RETURN_STRUCTURED_PROPOSAL": RiskTier.TIER_0_NO_RISK,
        "REPLAY_FIXTURE": RiskTier.TIER_1_LOW_RISK,
        "SESSION_STATE_WRITE": RiskTier.TIER_1_LOW_RISK,
        "WORKSPACE_WRITE": RiskTier.TIER_3_ELEVATED,
        "SUBPROCESS_EXEC": RiskTier.TIER_4_HIGH,
    }
    ALLOWED_CAPABILITIES = frozenset(CAPABILITY_TIERS)

    #: At or above this tier a grant additionally requires a HumanApproval bound
    #: to the exact proposal digest.
    HUMAN_APPROVAL_FLOOR = RiskTier.TIER_3_ELEVATED

    def __init__(self, approved_root: Path):
        self._approved_root = Path(approved_root).resolve()
        self._used_nonces: set[str] = set()

    @property
    def approved_root(self) -> Path:
        return self._approved_root

    @classmethod
    def requires_human_approval(cls, capability: str) -> bool:
        tier = cls.CAPABILITY_TIERS.get(capability)
        return tier is None or tier >= cls.HUMAN_APPROVAL_FLOOR

    def evaluate(
        self,
        proposal: ActionProposal,
        request: AuthorizedAgentRequest,
        now: datetime | None = None,
        approval: HumanApproval | None = None,
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
            raise GovernanceViolation(f"Capability '{proposal.capability}' not permitted by policy")
        if proposal.capability not in request.allowed_capabilities:
            raise GovernanceViolation(f"Capability '{proposal.capability}' not granted in parent request")
        if (
            self.requires_human_approval(proposal.capability)
            and proposal.action_kind.value != proposal.capability
        ):
            raise GovernanceViolation(
                f"Action kind '{proposal.action_kind.value}' does not match elevated "
                f"capability '{proposal.capability}'"
            )

        # 4. Human approval for elevated tiers, bound to this exact proposal
        if self.requires_human_approval(proposal.capability):
            if approval is None:
                raise GovernanceViolation(
                    f"Capability '{proposal.capability}' requires a human approval bound to this proposal"
                )
            if approval.proposal_digest != proposal.proposal_digest:
                raise GovernanceViolation("Human approval is bound to a different proposal digest")
            if not approval.approver_id.strip():
                raise GovernanceViolation("Human approval carries no approver identity")

        # 5. Strict Path & Symlink Traversal Protection
        self.confine_path(proposal.target.locator)

        # 6. Cost & Budget Class Verification
        self._evaluate_cost(request)

        # 7. Issue Bound ExecutionGrant
        target_digest = compute_sha256(proposal.target.digest())
        args_digest = compute_sha256(proposal.arguments)
        grant_id = f"grant_{compute_sha256(proposal.proposal_digest)[:16]}"

        integrity_digest = compute_sha256(
            self._integrity_payload(grant_id, proposal.proposal_digest, target_digest,
                                    args_digest, proposal.expires_at)
        )

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

    def confine_path(self, locator: str) -> Path:
        """Resolve ``locator`` (symlinks included) and require it to stay under the approved root."""
        target_path = Path(locator)
        if target_path.is_absolute():
            resolved_target = target_path.resolve()
        else:
            resolved_target = (self._approved_root / target_path).resolve()

        try:
            resolved_target.relative_to(self._approved_root)
        except ValueError:
            raise GovernanceViolation(f"Path traversal escape detected: '{locator}' escapes '{self._approved_root}'")
        return resolved_target

    def verify_grant(
        self,
        grant: ExecutionGrant,
        proposal: ActionProposal,
        now: datetime | None = None,
    ) -> None:
        """Executor-side check that ``grant`` authorizes exactly ``proposal``, right now."""
        current_time = now or datetime.now(timezone.utc)
        if grant.expires_at <= current_time:
            raise GovernanceViolation("ExecutionGrant has expired")
        if grant.policy_version != self.POLICY_VERSION:
            raise GovernanceViolation("ExecutionGrant was issued under a different policy version")
        if grant.proposal_hash != proposal.proposal_digest:
            raise GovernanceViolation("ExecutionGrant is bound to a different proposal")
        target_digest = compute_sha256(proposal.target.digest())
        args_digest = compute_sha256(proposal.arguments)
        if grant.allowed_target_digest != target_digest:
            raise GovernanceViolation("ExecutionGrant target digest mismatch")
        if grant.allowed_arguments_digest != args_digest:
            raise GovernanceViolation("ExecutionGrant arguments digest mismatch")
        expected = compute_sha256(
            self._integrity_payload(grant.grant_id, grant.proposal_hash, target_digest,
                                    args_digest, grant.expires_at)
        )
        if grant.integrity_digest != expected:
            raise GovernanceViolation("ExecutionGrant integrity digest mismatch")

    def _integrity_payload(
        self,
        grant_id: str,
        proposal_hash: str,
        target_digest: str,
        args_digest: str,
        expires_at: datetime,
    ) -> dict:
        return {
            "grant_id": grant_id,
            "proposal_hash": proposal_hash,
            "policy_version": self.POLICY_VERSION,
            "target_digest": target_digest,
            "args_digest": args_digest,
            "expires_at": expires_at.isoformat(),
        }

    def _evaluate_cost(self, request: AuthorizedAgentRequest) -> None:
        """Enforces hard spend governor levels and credit eligibility."""
        if request.budget_class == BudgetClass.FREE_TIER:
            if request.max_cost_usd > 0.0:
                raise GovernanceViolation("FREE_TIER budget class cannot have non-zero cost")
        elif request.budget_class == BudgetClass.FREE_TRIAL_RESERVE:
            if request.max_cost_usd > 10.0:
                raise GovernanceViolation("FREE_TRIAL_RESERVE requests exceeding $10 require human approval")
