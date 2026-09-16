"""Durable BUY-only runtime state for WickHunter.

The runtime state is rebuilt from the append-only ledger. Recovery is
conservative: an existing persisted BUY position blocks a new BUY until it is
explicitly reconciled or closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .ledger import TradeLedger
from .risk import RiskState
from .safety import recover_open_position, recover_risk_state


@dataclass(frozen=True)
class RuntimeSnapshot:
    open_position: dict[str, Any] | None
    risk_state: RiskState


def recover_runtime(
    ledger: TradeLedger,
    *,
    starting_equity: float,
    as_of: datetime | None = None,
) -> RuntimeSnapshot:
    """Recover durable position and risk state without placing an order."""
    position = recover_open_position(ledger)
    risk = recover_risk_state(ledger, starting_equity=starting_equity, as_of=as_of)
    return RuntimeSnapshot(open_position=position, risk_state=risk)
