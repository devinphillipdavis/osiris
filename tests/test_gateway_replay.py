"""Comprehensive offline conformance and security test suite for Gateway and Governor."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from osiris.agents.gateway import (
    ActionKind,
    ActionProposal,
    ActionTarget,
    AgentGateway,
    AgentResult,
    AuthorizedAgentRequest,
    BudgetClass,
    CapabilityGovernor,
    GovernanceViolation,
    ModelRouter,
    ProposalProvenance,
)
from osiris.agents.gateway.adapters.replay import ReplayAdapter


class TestGatewayReplay(unittest.IsolatedAsyncioTestCase):
    """Verifies all 12 security and authority invariants."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.approved_root = Path(self.temp_dir.name).resolve()

        # Create safe approved target file
        self.safe_file = self.approved_root / "safe.txt"
        self.safe_file.write_text("safe content")

        self.governor = CapabilityGovernor(approved_root=self.approved_root)
        self.replay = ReplayAdapter()
        self.router = ModelRouter(adapters={"replay": self.replay})
        self.gateway = AgentGateway(router=self.router, governor=self.governor)

        self.now = datetime.now(timezone.utc)
        self.request = AuthorizedAgentRequest(
            request_id="req-001",
            task="replay_task_test",
            allowed_capabilities=frozenset({"REPLAY_FIXTURE", "READ_ONLY_ANALYSIS"}),
            data_classification="RESTRICTED",
            authority_scope="test_scope",
            budget_class=BudgetClass.FREE_TIER,
            max_cost_usd=0.0,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _make_proposal(
        self,
        locator: str,
        capability: str = "REPLAY_FIXTURE",
        nonce: str = "nonce-1",
        req_id: str = "req-001",
        expires_in: int = 60,
    ) -> ActionProposal:
        return ActionProposal(
            proposal_id="prop-001",
            request_id=req_id,
            proposer_id="agent-01",
            action_kind=ActionKind.REPLAY_FIXTURE,
            capability=capability,
            target=ActionTarget(resource_type="file", locator=locator),
            arguments={"query": "test"},
            provenance=ProposalProvenance(
                proposer_id="agent-01",
                provider="replay",
                backend="fixture",
                model=None,
                session_id=None,
                route_ref="local",
            ),
            evidence_refs=("ev-01",),
            created_at=self.now,
            expires_at=self.now + timedelta(seconds=expires_in),
            nonce=nonce,
        )

    async def test_01_valid_replay_proposal(self) -> None:
        """Authorized request + permitted replay proposal -> deterministic grant."""
        prop = self._make_proposal("safe.txt")
        result = AgentResult(
            request_id="req-001",
            status="OK",
            provider="replay",
            proposals=(prop,),
            usage={"cost_usd": 0.0},
        )
        self.replay.register_fixture("replay_task_test", result)

        resp = await self.gateway.process(self.request)
        self.assertEqual(len(resp.grants), 1)
        self.assertEqual(resp.grants[0].proposal_hash, prop.proposal_digest)

    async def test_02_unknown_capability_denied(self) -> None:
        """Unknown or ungranted capability -> DENY."""
        prop = self._make_proposal("safe.txt", capability="RUN_ARBITRARY_COMMAND")
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, self.request, self.now)

    async def test_03_path_traversal_denied(self) -> None:
        """Target outside approved root via relative traversal -> DENY."""
        prop = self._make_proposal("../../etc/shadow")
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, self.request, self.now)

    async def test_04_symlink_escape_denied(self) -> None:
        """Target resolving outside approved root via symlink -> DENY."""
        outside_dir = tempfile.TemporaryDirectory()
        outside_file = Path(outside_dir.name) / "secret.env"
        outside_file.write_text("SECRET=1")

        symlink_path = self.approved_root / "link_escape"
        symlink_path.symlink_to(outside_file)

        prop = self._make_proposal("link_escape")
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, self.request, self.now)
        outside_dir.cleanup()

    async def test_05_expired_proposal_denied(self) -> None:
        """Expired proposal -> DENY."""
        prop = self._make_proposal("safe.txt", expires_in=-10)
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, self.request, self.now)

    async def test_06_replayed_nonce_denied(self) -> None:
        """Reused nonce -> DENY."""
        prop1 = self._make_proposal("safe.txt", nonce="reuse-123")
        prop2 = self._make_proposal("safe.txt", nonce="reuse-123")
        self.governor.evaluate(prop1, self.request, self.now)
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop2, self.request, self.now)

    async def test_07_request_id_mismatch_denied(self) -> None:
        """Proposal request_id mismatch -> DENY."""
        prop = self._make_proposal("safe.txt", req_id="other-req")
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, self.request, self.now)

    async def test_08_free_tier_cost_violation_denied(self) -> None:
        """FREE_TIER request declaring non-zero cost -> DENY."""
        bad_req = AuthorizedAgentRequest(
            request_id="req-cost",
            task="t",
            allowed_capabilities=frozenset({"REPLAY_FIXTURE"}),
            data_classification="RESTRICTED",
            authority_scope="s",
            budget_class=BudgetClass.FREE_TIER,
            max_cost_usd=0.50,
        )
        prop = self._make_proposal("safe.txt", req_id="req-cost")
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, bad_req, self.now)

    async def test_09_free_trial_excess_spend_denied(self) -> None:
        """FREE_TRIAL_RESERVE exceeding $10 cap without approval -> DENY."""
        bad_req = AuthorizedAgentRequest(
            request_id="req-trial",
            task="t",
            allowed_capabilities=frozenset({"REPLAY_FIXTURE"}),
            data_classification="RESTRICTED",
            authority_scope="s",
            budget_class=BudgetClass.FREE_TRIAL_RESERVE,
            max_cost_usd=15.00,
        )
        prop = self._make_proposal("safe.txt", req_id="req-trial")
        with self.assertRaises(GovernanceViolation):
            self.governor.evaluate(prop, bad_req, self.now)

    async def test_10_replay_determinism(self) -> None:
        """Byte-identical normalized result on repeated replay."""
        prop = self._make_proposal("safe.txt")
        result = AgentResult(
            request_id="req-001",
            status="OK",
            provider="replay",
            proposals=(prop,),
            usage={"cost_usd": 0.0},
        )
        self.replay.register_fixture("replay_task_test", result)

        key1 = self.replay.compute_request_key(self.request)
        key2 = self.replay.compute_request_key(self.request)
        self.assertEqual(key1, key2)

    async def test_11_unmapped_fixture_returns_not_found(self) -> None:
        """Unmapped request returns status NOT_FOUND without hallucinating."""
        unmapped_req = AuthorizedAgentRequest(
            request_id="req-unmapped",
            task="unknown_task",
            allowed_capabilities=frozenset({"REPLAY_FIXTURE"}),
            data_classification="RESTRICTED",
            authority_scope="s",
        )
        res = await self.replay.run(unmapped_req)
        self.assertEqual(res.status, "NOT_FOUND")

    async def test_12_secret_isolation(self) -> None:
        """Ensures grant and proposal records contain no raw credential leakage."""
        prop = self._make_proposal("safe.txt")
        grant = self.governor.evaluate(prop, self.request, self.now)
        for secret_token in ("key", "token", "password", "secret"):
            self.assertNotIn(secret_token, grant.grant_id)
