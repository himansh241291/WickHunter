"""Fail-closed broker/ledger reconciliation for BUY-only live runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reconciliation:
    safe_to_buy: bool
    reason: str | None = None


def reconcile_long_position(
    ledger_position: dict[str, Any] | None,
    broker_position: dict[str, Any] | None,
) -> Reconciliation:
    """Require durable ledger and broker to agree before a new BUY.

    Missing broker/ledger state is not treated as equivalent to an empty
    position when the other side reports a position.
    """
    if ledger_position is None and broker_position is None:
        return Reconciliation(True)

    if ledger_position is None and broker_position is not None:
        return Reconciliation(False, "broker_position_missing_from_ledger")

    if ledger_position is not None and broker_position is None:
        return Reconciliation(False, "ledger_position_missing_at_broker")

    assert ledger_position is not None and broker_position is not None
    for field in ("quantity", "entry", "stop", "target"):
        if field not in ledger_position or field not in broker_position:
            return Reconciliation(False, f"position_field_missing:{field}")
        if float(ledger_position[field]) != float(broker_position[field]):
            return Reconciliation(False, f"position_mismatch:{field}")

    return Reconciliation(True)
