"""
Extended safety tests for Sprint C Paper Venue Reconciliation & Execution Safety.
Validates the 5 Execution & Governance Safety Invariants:
1. Cross-process / cross-instance NO_NEW_RISK lock enforcement.
2. Event semantic validation (rejecting illegal transitions like PROPOSED -> RECONCILED_FILLED).
3. Client-order-ID collision handling (rejecting duplicate / reused client_order_id).
4. Partial-fill restart replay (verifying exposure rebuild and accounting post-restart).
5. Read-only evidence-output failure (ensuring failure to persist raises EVIDENCE_WRITE_FAILED).
"""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from osiris_reconciliation import (
    ClientOrderIdCollisionError,
    EvidenceWriteError,
    InvalidStateTransitionError,
    OrderStatus,
    ReconciliationEngine,
    RiskState,
    RiskViolationError,
    SimulatedPaperVenue,
)


class TestReconciliationExtendedSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "reconciliation_state.json"
        self.venue = SimulatedPaperVenue(venue_id="TEST_VENUE_EXT")
        self.engine = ReconciliationEngine(persistence_file=self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cross_instance_no_new_risk_lock(self):
        """Proves another adapter/engine instance cannot bypass a NO_NEW_RISK lock."""
        client_order_id = "ord_lock_test_001"
        self.engine.propose_order(
            client_order_id=client_order_id,
            symbol="BTC-USD",
            side="BUY",
            quantity=1.0,
            price=50000.0,
        )
        # Dispatch with lost ACK to enter FREEZE_NEW_RISK
        self.engine.dispatch_order(
            client_order_id=client_order_id,
            venue=self.venue,
            simulate_lost_ack=True,
        )
        self.assertEqual(self.engine.risk_state, RiskState.FREEZE_NEW_RISK)

        # Instance 2 boots concurrently pointing to the same state/lock
        engine_2 = ReconciliationEngine(persistence_file=self.state_file)
        self.assertEqual(engine_2.risk_state, RiskState.FREEZE_NEW_RISK)

        # Instance 2 MUST NOT be able to propose new risk
        with self.assertRaises(RiskViolationError) as ctx:
            engine_2.propose_order(
                client_order_id="ord_lock_test_002_bypass",
                symbol="BTC-USD",
                side="BUY",
                quantity=0.5,
                price=50000.0,
            )
        self.assertIn("NO_NEW_RISK invariant violated", str(ctx.exception))

        # Even with an empty in-memory engine, the active on-disk .lock prevents new risk
        engine_uninitialized = ReconciliationEngine()
        engine_uninitialized.persistence_file = self.state_file
        with self.assertRaises(RiskViolationError) as ctx:
            engine_uninitialized.propose_order(
                client_order_id="ord_lock_test_003_raw",
                symbol="BTC-USD",
                side="BUY",
                quantity=0.1,
                price=50000.0,
            )
        self.assertIn("NO_NEW_RISK invariant violated", str(ctx.exception))

    def test_event_semantic_validation_rejects_illegal_transitions(self):
        """Detects and rejects illegal transitions (e.g. PROPOSED -> RECONCILED_FILLED directly)."""
        client_order_id = "ord_transition_test_001"
        order = self.engine.propose_order(
            client_order_id=client_order_id,
            symbol="ETH-USD",
            side="BUY",
            quantity=10.0,
            price=3000.0,
        )
        self.assertEqual(order.status, OrderStatus.PROPOSED)

        # Attempt illegal transition: PROPOSED -> RECONCILED_FILLED directly bypassing DISPATCHED
        with self.assertRaises(InvalidStateTransitionError) as ctx:
            self.engine._transition_order(order, OrderStatus.RECONCILED_FILLED)
        self.assertIn("Invalid state transition", str(ctx.exception))
        self.assertEqual(order.status, OrderStatus.PROPOSED)

        # Attempt illegal reconciliation call on PROPOSED order
        with self.assertRaises(InvalidStateTransitionError) as ctx:
            self.engine.reconcile_unresolved_order(client_order_id, self.venue)
        self.assertIn("not VENUE_UNKNOWN", str(ctx.exception))

        # Dispatch order normally
        self.engine.dispatch_order(client_order_id, self.venue)
        self.assertEqual(order.status, OrderStatus.RECONCILED_FILLED)

        # Attempt transition from terminal RECONCILED_FILLED to DISPATCHED
        with self.assertRaises(InvalidStateTransitionError) as ctx:
            self.engine._transition_order(order, OrderStatus.DISPATCHED)
        self.assertIn("Invalid state transition", str(ctx.exception))

    def test_client_order_id_collision_handling(self):
        """Rejects distinct intents that map to an existing ID or reuse an existing ID."""
        client_order_id = "ord_unique_collision_001"
        self.engine.propose_order(
            client_order_id=client_order_id,
            symbol="SOL-USD",
            side="BUY",
            quantity=5.0,
            price=150.0,
        )

        # Attempt duplicate proposal while PROPOSED
        with self.assertRaises(ClientOrderIdCollisionError) as ctx:
            self.engine.propose_order(
                client_order_id=client_order_id,
                symbol="SOL-USD",
                side="BUY",
                quantity=10.0,
                price=150.0,
            )
        self.assertIn("Client order ID collision", str(ctx.exception))

        # Dispatch and complete the order
        self.engine.dispatch_order(client_order_id, self.venue)
        self.assertEqual(self.engine.orders[client_order_id].status, OrderStatus.RECONCILED_FILLED)

        # Attempt reuse of client_order_id after order is filled/closed
        with self.assertRaises(ClientOrderIdCollisionError) as ctx:
            self.engine.propose_order(
                client_order_id=client_order_id,
                symbol="SOL-USD",
                side="SELL",
                quantity=5.0,
                price=160.0,
            )
        self.assertIn("Client order ID collision", str(ctx.exception))

    def test_partial_fill_restart_replay(self):
        """Confirms reservation and exposure rebuild correctly after a simulated restart during partial fill."""
        client_order_id = "ord_partial_fill_001"
        qty = 100.0
        price = 10.0
        total_initial_exposure = 1000.0

        # Step 1: Propose order
        self.engine.propose_order(
            client_order_id=client_order_id,
            symbol="AVAX-USD",
            side="BUY",
            quantity=qty,
            price=price,
        )
        self.assertEqual(self.engine.total_committed_exposure, 0.0)

        # Step 2: Dispatch with injected lost ACK and partial fill (40 filled out of 100)
        dispatched = self.engine.dispatch_order(
            client_order_id=client_order_id,
            venue=self.venue,
            simulate_lost_ack=True,
            simulate_partial_fill_qty=40.0,
        )
        self.assertEqual(dispatched.status, OrderStatus.VENUE_UNKNOWN)
        # Pessimistic exposure commits full 1000.0 during ambiguity
        self.assertEqual(self.engine.total_committed_exposure, total_initial_exposure)
        self.assertEqual(self.engine.risk_state, RiskState.FREEZE_NEW_RISK)

        # Step 3: Reconcile the partial fill
        reconciled = self.engine.reconcile_unresolved_order(client_order_id, self.venue)
        self.assertEqual(reconciled.status, OrderStatus.RECONCILED_PARTIAL_FILL)
        self.assertEqual(reconciled.fill_quantity, 40.0)
        self.assertEqual(reconciled.fill_price, 10.0)
        # Committed exposure after partial fill is adjusted: 40 filled * 10 = 400.0, remaining 600 released
        expected_committed = 400.0
        self.assertEqual(self.engine.total_committed_exposure, expected_committed)
        self.assertEqual(self.engine.risk_state, RiskState.NORMAL)

        # Step 4: Simulate restart from disk persistence
        restarted = ReconciliationEngine(persistence_file=self.state_file)
        self.assertEqual(restarted.total_committed_exposure, expected_committed)
        self.assertEqual(restarted.risk_state, RiskState.NORMAL)
        self.assertIn(client_order_id, restarted.orders)
        restarted_order = restarted.orders[client_order_id]
        self.assertEqual(restarted_order.status, OrderStatus.RECONCILED_PARTIAL_FILL)
        self.assertEqual(restarted_order.fill_quantity, 40.0)
        self.assertEqual(restarted_order.exposure, total_initial_exposure)

        # Hash chain verification post-restart
        self.assertTrue(len(restarted.evidence_chain) >= 4)
        for i in range(1, len(restarted.evidence_chain)):
            self.assertEqual(
                restarted.evidence_chain[i].previous_receipt_hash,
                restarted.evidence_chain[i - 1].receipt_hash,
            )

    def test_readonly_evidence_output_raises_evidence_write_failed(self):
        """Ensures inability to write an artifact results in EVIDENCE_WRITE_FAILED."""
        read_only_file = Path(self.temp_dir.name) / "non_writable_dir" / "evidence.json"
        engine_ro = ReconciliationEngine(persistence_file=read_only_file)

        # Mock mkdir to simulate permission denied or read-only filesystem
        with patch.object(Path, "mkdir", side_effect=PermissionError("Permission denied: read-only filesystem")):
            with self.assertRaises(EvidenceWriteError) as ctx:
                engine_ro.propose_order(
                    client_order_id="ord_fail_001",
                    symbol="DOT-USD",
                    side="BUY",
                    quantity=1.0,
                    price=10.0,
                )
            self.assertIn("EVIDENCE_WRITE_FAILED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
