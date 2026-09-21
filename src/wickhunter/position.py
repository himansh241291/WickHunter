"""Deterministic live lifecycle monitoring for an existing BUY position."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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

    def reconcile(self) -> Reconciliation:
        """Require an existing ledger position to match the broker position."""
        if self.ledger is None:
            self.halted = True
            return Reconciliation(False, "ledger_required_for_live_monitor")
        snapshot = self.ledger.snapshot()
        result = reconcile_long_position(snapshot["open_position"], self.execution.position())
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

        receipt = self.execution.close_long(time=time, price=trigger)
        self.closed = True
        if self.ledger:
            self.ledger.append(
                "POSITION_CLOSED",
                time=receipt.time,
                order_id=receipt.order_id,
                result=result,
                exit=receipt.fill_price,
                quantity=receipt.quantity,
            )
        return receipt
