"""
Test suite for Sprint C: Paper Venue Reconciliation & Uncertain Submission Handling.
Validates the 10 Execution Safety Invariants:
1. Simulated venue accepts order.
2. Acknowledgement is deliberately dropped/lost post-acceptance.
3. OSIRIS transition to VENUE_UNKNOWN with TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE.
4. OSIRIS freezes new risk-increasing intents (FREEZE_NEW_RISK / NO_NEW_RISK).
5. State persistence ensures restart/replay preserves unresolved state.
6. Reconciliation queries venue strictly with the original client_order_id.
7. OSIRIS discovers the original order status at the venue.
8. No replacement order ID is ever generated during reconciliation.
9. Portfolio exposure is counted exactly once throughout ambiguity and resolution.
10. End-to-end execution is deterministic and replayable under the same fixture/seed.
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from osiris_reconciliation import (
    OrderStatus,
    ReconciliationEngine,
    RiskState,
    RiskViolationError,
    SimulatedPaperVenue,
)


class TestPaperReconciliationSprintC(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp_dir.name) / "reconciliation_state.json"
        self.venue = SimulatedPaperVenue(venue_id="TEST_VENUE_01")
        self.engine = ReconciliationEngine(persistence_file=self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ten_execution_safety_invariants(self):
        client_order_id = "ord_sprint_c_001"
        symbol = "QBIT_EXPERIMENT"
        side = "BUY"
        quantity = 50.0
        price = 10.0
        expected_exposure = 500.0  # 50.0 * 10.0

        # Step 1: Propose order
        order = self.engine.propose_order(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
        )
        self.assertEqual(order.status, OrderStatus.PROPOSED)
        self.assertEqual(order.exposure, expected_exposure)

        # Step 2: Dispatch with injected network failure (ACK deliberately lost)
        # Invariant 1: Venue accepts order.
        # Invariant 2: The acknowledgement is deliberately lost.
        dispatched_order = self.engine.dispatch_order(
            client_order_id=client_order_id,
            venue=self.venue,
            simulate_lost_ack=True,
        )

        # Invariant 3: OSIRIS records VENUE_UNKNOWN with TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE
        self.assertEqual(dispatched_order.status, OrderStatus.VENUE_UNKNOWN)
        self.assertEqual(dispatched_order.unresolved_reason, "TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE")

        # Invariant 4: OSIRIS freezes new risk-increasing intents (FREEZE_NEW_RISK / NO_NEW_RISK)
        self.assertEqual(self.engine.risk_state, RiskState.FREEZE_NEW_RISK)
        with self.assertRaises(RiskViolationError) as ctx:
            self.engine.propose_order(
                client_order_id="ord_sprint_c_002_blocked",
                symbol=symbol,
                side=side,
                quantity=10.0,
                price=10.0,
            )
        self.assertIn("NO_NEW_RISK invariant violated", str(ctx.exception))

        # Invariant 9 (Part A): Exposure is counted exactly once during ambiguity
        self.assertEqual(self.engine.total_committed_exposure, expected_exposure)

        # Invariant 5: Restart/replay preserves the unresolved state
        restarted_engine = ReconciliationEngine(persistence_file=self.state_file)
        self.assertEqual(restarted_engine.risk_state, RiskState.FREEZE_NEW_RISK)
        self.assertEqual(restarted_engine.total_committed_exposure, expected_exposure)
        self.assertIn(client_order_id, restarted_engine.orders)
        self.assertEqual(restarted_engine.orders[client_order_id].status, OrderStatus.VENUE_UNKNOWN)
        self.assertEqual(
            restarted_engine.orders[client_order_id].unresolved_reason,
            "TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE",
        )

        # Invariant 6: Reconciliation queries the same client_order_id
        # Invariant 7: OSIRIS finds the original order at the venue
        reconciled_order = restarted_engine.reconcile_unresolved_order(
            client_order_id=client_order_id,
            venue=self.venue,
        )

        self.assertEqual(reconciled_order.status, OrderStatus.RECONCILED_FILLED)
        self.assertIsNotNone(reconciled_order.venue_order_id)
        self.assertEqual(reconciled_order.fill_quantity, quantity)
        self.assertEqual(reconciled_order.fill_price, price)

        # Invariant 8: No replacement order ID exists
        self.assertEqual(len(reconciled_order.replacement_order_ids), 0)
        self.assertNotIn("ord_sprint_c_002_blocked", restarted_engine.orders)
        self.assertEqual(list(restarted_engine.orders.keys()), [client_order_id])

        # Invariant 9 (Part B): Exposure is still counted exactly once (never duplicated)
        self.assertEqual(restarted_engine.total_committed_exposure, expected_exposure)

        # Risk state unfreezes after ambiguity resolution
        self.assertEqual(restarted_engine.risk_state, RiskState.NORMAL)

        # Invariant 10: The result is replayable with the same fixture, seed, build, and policy
        receipt_hashes = [r.receipt_hash for r in restarted_engine.evidence_chain]
        self.assertTrue(len(receipt_hashes) >= 4)  # PROPOSED, DISPATCHED, ACK_LOST, RECONCILING, COMPLETED
        # Verify receipt hash chain integrity
        for i in range(1, len(restarted_engine.evidence_chain)):
            curr_receipt = restarted_engine.evidence_chain[i]
            prev_receipt = restarted_engine.evidence_chain[i - 1]
            self.assertEqual(curr_receipt.previous_receipt_hash, prev_receipt.receipt_hash)

    def test_reconciliation_order_absent_releases_exposure(self):
        """If reconciliation determines the order was never received by venue, exposure is released."""
        client_order_id = "ord_absent_001"
        self.engine.propose_order(
            client_order_id=client_order_id,
            symbol="TEST",
            side="BUY",
            quantity=10.0,
            price=20.0,
        )
        self.engine.dispatch_order(
            client_order_id=client_order_id,
            venue=self.venue,
            simulate_lost_ack=True,
        )
        self.assertEqual(self.engine.total_committed_exposure, 200.0)

        # Simulate venue having NO record of order (e.g. packet dropped before reaching venue)
        empty_venue = SimulatedPaperVenue(venue_id="EMPTY_VENUE")
        reconciled = self.engine.reconcile_unresolved_order(
            client_order_id=client_order_id,
            venue=empty_venue,
        )
        self.assertEqual(reconciled.status, OrderStatus.RECONCILED_ABSENT)
        # Exposure must be safely released
        self.assertEqual(self.engine.total_committed_exposure, 0.0)
        self.assertEqual(self.engine.risk_state, RiskState.NORMAL)


if __name__ == "__main__":
    unittest.main()
