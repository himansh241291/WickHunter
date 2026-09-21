"""Deterministic live lifecycle monitoring for an existing BUY position."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

from .ledger import TradeLedger
from .ports import BuyExecutionPort, CloseReceipt
from .reconcile import Reconciliation, reconcile_long_position


@dataclass(frozen=True)
class CloseDecision:
    result: str
    price: float


class LongPositionMonitor:
    """Monitor one broker-confirmed long and close only on defined exits."""

    def __init__(self, *, execution: BuyExecutionPort, ledger: TradeLedger | None = None):
        self.execution = execution
        self.ledger = ledger
        self.halted = False
        self.closed = False
        self.position_snapshot: dict | None = None

    def reconcile(self) -> Reconciliation:
        """Require an existing ledger position to match the broker position."""
        if self.ledger is None:
            self.halted = True
            return Reconciliation(False, "ledger_required_for_live_monitor")
        snapshot = self.ledger.snapshot()
        self.position_snapshot = snapshot.get("open_position")
        result = reconcile_long_position(self.position_snapshot, self.execution.position())
        if not result.safe_to_buy:
            self.halted = True
        return result

    def on_price(
        self,
        *,
        time: datetime,
        price: float,
        stop: float,
        target: float,
        session_end: bool = False,
    ) -> CloseReceipt | None:
        """Close the existing long on stop, target, or explicit session end.

        Stop is evaluated first when both levels are observable at the same
        price. Session-end closure is used only when no stop/target fired.
        """
        if self.halted or self.closed:
            return None

        result: str | None = None
        trigger = price
        if price <= stop:
            result = "LOSS"
            trigger = stop
        elif price >= target:
            result = "WIN"
            trigger = target
        elif session_end:
            result = "SESSION_END"

        if result is None:
            return None

        client_order_id = self._close_client_order_id(result)
        if self.ledger:
            pending = self.ledger.snapshot().get("pending_close")
            if pending is not None:
                if pending.get("client_order_id") != client_order_id:
                    self.halted = True
                    return None
                existing = self.execution.find_close_order(client_order_id)
                if existing is not None:
                    self._record_close(existing, result)
                    return existing
            self.ledger.append(
                "LONG_CLOSE_INTENT",
                time=time,
                client_order_id=client_order_id,
                result=result,
                trigger=trigger,
            )

        receipt = self.execution.close_long(
            time=time, price=trigger, client_order_id=client_order_id
        )
        self._record_close(receipt, result)
        return receipt


    def _close_client_order_id(self, result: str) -> str:
        position_id = str((self.position_snapshot or {}).get("order_id", "unknown"))
        raw = f"{position_id}|{result}".encode()
        return "wh-close-" + hashlib.sha256(raw).hexdigest()[:24]

    def _record_close(self, receipt: CloseReceipt, result: str) -> None:
        if self.closed:
            return
        self.closed = True
        if self.ledger:
            self.ledger.append(
                "POSITION_CLOSED",
                time=receipt.time,
                order_id=receipt.order_id,
                client_order_id=receipt.client_order_id,
                result=result,
                exit=receipt.fill_price,
                quantity=receipt.quantity,
            )
