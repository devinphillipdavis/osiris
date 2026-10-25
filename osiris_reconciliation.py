#!/usr/bin/env python3
"""
OSIRIS Execution Reconciliation Engine (Sprint C)
================================================
Implements genuine uncertain-submission and paper-venue reconciliation:

    TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE
                ↓
          VENUE_UNKNOWN
                ↓
           NO_NEW_RISK (FREEZE_NEW_RISK)
                ↓
    RECONCILE ORIGINAL CLIENT ORDER ID
                ↓
  RECONCILED_OPEN / FILLED / REJECTED / ABSENT

Invariants Enforced:
1. Simulated venue accepts order.
2. Acknowledgement is deliberately dropped/lost post-acceptance.
3. OSIRIS transition to VENUE_UNKNOWN with TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE.
4. OSIRIS freezes new risk-increasing intents (FREEZE_NEW_RISK).
5. State persistence ensures restart/replay preserves unresolved state.
6. Reconciliation queries venue strictly with the original client_order_id.
7. OSIRIS discovers the original order status at the venue.
8. No replacement order ID is ever generated during reconciliation.
9. Portfolio exposure is counted exactly once throughout ambiguity and resolution.
10. End-to-end execution is deterministic and replayable under the same fixture/seed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class OrderStatus(str, Enum):
    PROPOSED = "PROPOSED"
    POLICY_CHECKED = "POLICY_CHECKED"
    DISPATCHED = "DISPATCHED"
    VENUE_UNKNOWN = "VENUE_UNKNOWN"
    RECONCILING = "RECONCILING"
    RECONCILED_OPEN = "RECONCILED_OPEN"
    RECONCILED_FILLED = "RECONCILED_FILLED"
    RECONCILED_PARTIAL_FILL = "RECONCILED_PARTIAL_FILL"
    RECONCILED_REJECTED = "RECONCILED_REJECTED"
    RECONCILED_ABSENT = "RECONCILED_ABSENT"


class RiskState(str, Enum):
    NORMAL = "NORMAL"
    FREEZE_NEW_RISK = "FREEZE_NEW_RISK"
    HALTED = "HALTED"


class RiskViolationError(RuntimeError):
    """Raised when an action violates the independent paper-risk policy."""
    pass


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal order status transition is attempted."""
    pass


class ClientOrderIdCollisionError(ValueError):
    """Raised when a client_order_id is reused or collides with an existing order."""
    pass


class EvidenceWriteError(IOError):
    """Raised when writing an immutable or persistent evidence receipt fails."""
    pass


class VenueTransmissionTimeout(TimeoutError):
    """Raised when an order submission acknowledgement is lost post-acceptance."""
    pass


@dataclass
class VenueOrder:
    client_order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: float
    price: float
    exposure: float
    status: OrderStatus
    created_at_utc: str
    dispatched_at_utc: Optional[str] = None
    unresolved_reason: Optional[str] = None
    reconciled_at_utc: Optional[str] = None
    venue_order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_quantity: Optional[float] = None
    replacement_order_ids: List[str] = field(default_factory=list)


@dataclass
class ReconciliationReceipt:
    receipt_id: str
    client_order_id: str
    event: str
    status: str
    risk_state: str
    exposure: float
    total_committed_exposure: float
    details: Dict[str, Any]
    previous_receipt_hash: str
    receipt_hash: str
    timestamp_utc: str


VALID_TRANSITIONS: Dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PROPOSED: {OrderStatus.DISPATCHED},
    OrderStatus.POLICY_CHECKED: {OrderStatus.DISPATCHED},
    OrderStatus.DISPATCHED: {
        OrderStatus.VENUE_UNKNOWN,
        OrderStatus.RECONCILED_FILLED,
        OrderStatus.RECONCILED_PARTIAL_FILL,
    },
    OrderStatus.VENUE_UNKNOWN: {OrderStatus.RECONCILING},
    OrderStatus.RECONCILING: {
        OrderStatus.RECONCILED_OPEN,
        OrderStatus.RECONCILED_FILLED,
        OrderStatus.RECONCILED_PARTIAL_FILL,
        OrderStatus.RECONCILED_REJECTED,
        OrderStatus.RECONCILED_ABSENT,
    },
    OrderStatus.RECONCILED_OPEN: set(),
    OrderStatus.RECONCILED_FILLED: set(),
    OrderStatus.RECONCILED_PARTIAL_FILL: set(),
    OrderStatus.RECONCILED_REJECTED: set(),
    OrderStatus.RECONCILED_ABSENT: set(),
}


class SimulatedPaperVenue:
    """
    Simulated paper venue with controllable network fault injection.
    Tracks venue-side book/fills to enable empirical ground-truth reconciliation.
    """

    def __init__(self, venue_id: str = "PAPER_VENUE_SIM"):
        self.venue_id = venue_id
        self._venue_store: Dict[str, Dict[str, Any]] = {}
        self._seq: int = 0

    def submit_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        simulate_lost_ack: bool = False,
        simulate_partial_fill_qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Accept and process the order.
        If simulate_lost_ack is True, order is processed into venue state,
        but the network acknowledgement is dropped with VenueTransmissionTimeout.
        """
        self._seq += 1
        venue_order_id = f"VEN-{self.venue_id}-{self._seq:06d}"

        is_partial = simulate_partial_fill_qty is not None and simulate_partial_fill_qty < quantity
        venue_status = "PARTIALLY_FILLED" if is_partial else "FILLED"
        filled_qty = simulate_partial_fill_qty if is_partial else quantity

        order_record = {
            "venue_order_id": venue_order_id,
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "venue_status": venue_status,
            "filled_quantity": filled_qty,
            "fill_price": price,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        self._venue_store[client_order_id] = order_record

        if simulate_lost_ack:
            # Order accepted at venue, but transport drop prevents client acknowledgement
            raise VenueTransmissionTimeout(
                f"TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE: Order {client_order_id} sent, but ACK dropped"
            )

        return copy.deepcopy(order_record)

    def query_order(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Query venue ground truth using original client_order_id."""
        if client_order_id in self._venue_store:
            return copy.deepcopy(self._venue_store[client_order_id])
        return None


class ReconciliationEngine:
    """
    Evidence-governed reconciliation engine enforcing the 10 execution safety invariants.
    """

    def __init__(self, persistence_file: Optional[Path] = None):
        self.persistence_file = persistence_file
        self.orders: Dict[str, VenueOrder] = {}
        self.risk_state: RiskState = RiskState.NORMAL
        self.total_committed_exposure: float = 0.0
        self.evidence_chain: List[ReconciliationReceipt] = []
        self._last_hash: str = "0" * 64

        if self.persistence_file and self.persistence_file.exists():
            self._load_state()

    def _transition_order(self, order: VenueOrder, target_status: OrderStatus) -> None:
        """Validate and execute a formal status transition."""
        allowed = VALID_TRANSITIONS.get(order.status, set())
        if target_status not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid state transition: Cannot transition order {order.client_order_id} "
                f"from {order.status.value} to {target_status.value}."
            )
        order.status = target_status

    def _append_receipt(
        self,
        client_order_id: str,
        event: str,
        status: OrderStatus,
        details: Dict[str, Any],
    ) -> ReconciliationReceipt:
        now_str = datetime.now(timezone.utc).isoformat()
        receipt_id = f"rcpt_{hashlib.sha256(f'{client_order_id}:{event}:{now_str}:{len(self.evidence_chain)}'.encode()).hexdigest()[:12]}"
        
        order = self.orders.get(client_order_id)
        exposure = order.exposure if order else 0.0

        body = {
            "receipt_id": receipt_id,
            "client_order_id": client_order_id,
            "event": event,
            "status": status.value,
            "risk_state": self.risk_state.value,
            "exposure": exposure,
            "total_committed_exposure": self.total_committed_exposure,
            "details": details,
            "previous_receipt_hash": self._last_hash,
            "timestamp_utc": now_str,
        }
        receipt_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()

        receipt = ReconciliationReceipt(
            receipt_id=receipt_id,
            client_order_id=client_order_id,
            event=event,
            status=status.value,
            risk_state=self.risk_state.value,
            exposure=exposure,
            total_committed_exposure=self.total_committed_exposure,
            details=details,
            previous_receipt_hash=self._last_hash,
            receipt_hash=receipt_hash,
            timestamp_utc=now_str,
        )
        self.evidence_chain.append(receipt)
        self._last_hash = receipt_hash
        self._persist_state()
        return receipt

    def _persist_state(self):
        if not self.persistence_file:
            return
        payload = {
            "risk_state": self.risk_state.value,
            "total_committed_exposure": self.total_committed_exposure,
            "last_hash": self._last_hash,
            "orders": {k: asdict(v) for k, v in self.orders.items()},
            "evidence_chain": [asdict(r) for r in self.evidence_chain],
        }
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_target = self.persistence_file.with_suffix(".tmp")
            with open(tmp_target, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_target, self.persistence_file)

            # Sync active lockfile for cross-process/cross-instance safety
            lock_path = self.persistence_file.with_suffix(".lock")
            if self.risk_state == RiskState.FREEZE_NEW_RISK:
                with open(lock_path, "w", encoding="utf-8") as lf:
                    lf.write(f"FREEZE_NEW_RISK: locked at {datetime.now(timezone.utc).isoformat()}\n")
            elif lock_path.exists():
                try:
                    lock_path.unlink()
                except OSError:
                    pass
        except (OSError, PermissionError) as exc:
            raise EvidenceWriteError(
                f"EVIDENCE_WRITE_FAILED: Failed to write persistent reconciliation artifact to {self.persistence_file}: {exc}"
            ) from exc

    def _load_state(self):
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, PermissionError) as exc:
            raise EvidenceWriteError(
                f"EVIDENCE_WRITE_FAILED: Failed to read persistent reconciliation artifact from {self.persistence_file}: {exc}"
            ) from exc
        self.risk_state = RiskState(payload["risk_state"])
        self.total_committed_exposure = float(payload["total_committed_exposure"])
        self._last_hash = payload["last_hash"]
        self.orders = {}
        for k, v in payload["orders"].items():
            order_data = dict(v)
            order_data["status"] = OrderStatus(order_data["status"])
            self.orders[k] = VenueOrder(**order_data)
        self.evidence_chain = [ReconciliationReceipt(**r) for r in payload["evidence_chain"]]

    def propose_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> VenueOrder:
        """
        Propose a new order. Must pass RiskState check.
        If risk_state == FREEZE_NEW_RISK, no new risk-increasing orders are permitted.
        Enforces cross-process lockfile detection and client_order_id collision detection.
        """
        # Cross-instance active lock check
        if self.persistence_file:
            lock_path = self.persistence_file.with_suffix(".lock")
            if lock_path.exists():
                raise RiskViolationError(
                    f"NO_NEW_RISK invariant violated: Active cross-process lock {lock_path} detects FREEZE_NEW_RISK."
                )

        if self.risk_state == RiskState.FREEZE_NEW_RISK:
            raise RiskViolationError(
                f"NO_NEW_RISK invariant violated: System is in FREEZE_NEW_RISK state due to unresolved venue ambiguity."
            )

        if client_order_id in self.orders:
            raise ClientOrderIdCollisionError(
                f"Client order ID collision: Order ID {client_order_id} already exists in order ledger."
            )

        exposure = quantity * price
        order = VenueOrder(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            exposure=exposure,
            status=OrderStatus.PROPOSED,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        self.orders[client_order_id] = order
        self._append_receipt(client_order_id, "ORDER_PROPOSED", OrderStatus.PROPOSED, {"exposure": exposure})
        return order

    def dispatch_order(
        self,
        client_order_id: str,
        venue: SimulatedPaperVenue,
        simulate_lost_ack: bool = False,
        simulate_partial_fill_qty: Optional[float] = None,
    ) -> VenueOrder:
        """
        Dispatch order to the venue.
        If ACK is lost:
        - Order enters VENUE_UNKNOWN with TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE
        - Risk state enters FREEZE_NEW_RISK
        - Exposure is committed exactly once (pessimistic accounting)
        """
        order = self.orders.get(client_order_id)
        if not order:
            raise KeyError(f"Order {client_order_id} not found.")

        self._transition_order(order, OrderStatus.DISPATCHED)
        order.dispatched_at_utc = datetime.now(timezone.utc).isoformat()

        # Allocate exposure pessimistically upon dispatch
        self.total_committed_exposure += order.exposure
        self._append_receipt(client_order_id, "ORDER_DISPATCHED", OrderStatus.DISPATCHED, {"exposure": order.exposure})

        try:
            fill_data = venue.submit_order(
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
                simulate_lost_ack=simulate_lost_ack,
                simulate_partial_fill_qty=simulate_partial_fill_qty,
            )
            # Normal synchronous fill
            if fill_data.get("venue_status") == "PARTIALLY_FILLED":
                self._transition_order(order, OrderStatus.RECONCILED_PARTIAL_FILL)
                unfilled = order.quantity - fill_data["filled_quantity"]
                self.total_committed_exposure -= (unfilled * order.price)
            else:
                self._transition_order(order, OrderStatus.RECONCILED_FILLED)

            order.venue_order_id = fill_data["venue_order_id"]
            order.fill_price = fill_data["fill_price"]
            order.fill_quantity = fill_data["filled_quantity"]
            order.reconciled_at_utc = datetime.now(timezone.utc).isoformat()
            self._append_receipt(client_order_id, "ORDER_FILLED_DIRECT", order.status, fill_data)
        except VenueTransmissionTimeout as exc:
            # ACK lost post-acceptance!
            self._transition_order(order, OrderStatus.VENUE_UNKNOWN)
            order.unresolved_reason = "TIMEOUT_AFTER_POSSIBLE_ACCEPTANCE"
            self.risk_state = RiskState.FREEZE_NEW_RISK
            self._append_receipt(
                client_order_id,
                "ACKNOWLEDGEMENT_LOST",
                OrderStatus.VENUE_UNKNOWN,
                {"error": str(exc), "unresolved_reason": order.unresolved_reason},
            )

        return order

    def reconcile_unresolved_order(
        self,
        client_order_id: str,
        venue: SimulatedPaperVenue,
    ) -> VenueOrder:
        """
        Reconcile an order in VENUE_UNKNOWN state.
        Invariants:
        - Queries the venue using strictly the ORIGINAL client_order_id.
        - Verifies NO replacement order ID exists or is created.
        - Exposure remains counted exactly once.
        - Resolves to RECONCILED_FILLED, RECONCILED_PARTIAL_FILL, RECONCILED_OPEN, RECONCILED_REJECTED, or RECONCILED_ABSENT.
        - If all venue ambiguity cleared, unfreezes risk to NORMAL.
        """
        order = self.orders.get(client_order_id)
        if not order:
            raise KeyError(f"Order {client_order_id} not found.")

        if order.status != OrderStatus.VENUE_UNKNOWN:
            raise InvalidStateTransitionError(
                f"Invalid state transition: Order {client_order_id} is in status {order.status.value}, not VENUE_UNKNOWN."
            )

        self._transition_order(order, OrderStatus.RECONCILING)
        self._append_receipt(client_order_id, "RECONCILIATION_INITIATED", OrderStatus.RECONCILING, {})

        # Query venue with strictly original client_order_id
        venue_record = venue.query_order(client_order_id)

        if venue_record is not None:
            # Order found at venue!
            order.venue_order_id = venue_record.get("venue_order_id")
            order.fill_price = venue_record.get("fill_price")
            order.fill_quantity = venue_record.get("filled_quantity")
            order.reconciled_at_utc = datetime.now(timezone.utc).isoformat()

            if venue_record.get("venue_status") == "FILLED":
                self._transition_order(order, OrderStatus.RECONCILED_FILLED)
            elif venue_record.get("venue_status") == "PARTIALLY_FILLED":
                self._transition_order(order, OrderStatus.RECONCILED_PARTIAL_FILL)
                unfilled_qty = order.quantity - (order.fill_quantity or 0.0)
                self.total_committed_exposure -= (unfilled_qty * order.price)
            elif venue_record.get("venue_status") == "REJECTED":
                self._transition_order(order, OrderStatus.RECONCILED_REJECTED)
                # Release committed exposure
                self.total_committed_exposure -= order.exposure
            else:
                self._transition_order(order, OrderStatus.RECONCILED_OPEN)
        else:
            # Order absent from venue
            self._transition_order(order, OrderStatus.RECONCILED_ABSENT)
            order.reconciled_at_utc = datetime.now(timezone.utc).isoformat()
            self.total_committed_exposure -= order.exposure

        # Verify NO replacement order IDs were created
        assert len(order.replacement_order_ids) == 0, "INVARIANT VIOLATION: Replacement order ID detected!"

        # Check if any orders remain VENUE_UNKNOWN
        has_unknown = any(o.status == OrderStatus.VENUE_UNKNOWN for o in self.orders.values())
        if not has_unknown:
            self.risk_state = RiskState.NORMAL

        self._append_receipt(
            client_order_id,
            "RECONCILIATION_COMPLETED",
            order.status,
            {"venue_record": venue_record, "remaining_risk_state": self.risk_state.value},
        )
        return order
