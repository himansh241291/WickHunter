"""Persistent BUY-only operational safety controls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .ledger import TradeLedger
from .risk import RiskState


@dataclass
class KillSwitch:
    """Fail-closed manual halt persisted in the event ledger."""
    ledger: TradeLedger

    def is_halted(self) -> bool:
        return bool(self.ledger.snapshot()["halted"])

    def engage(self, *, time: datetime, reason: str = "manual") -> None:
        self.ledger.append("KILL_SWITCH_ON", time=time, reason=reason)

    def release(self, *, time: datetime, reason: str = "manual") -> None:
        self.ledger.append("KILL_SWITCH_OFF", time=time, reason=reason)

    def allow_buy(self) -> bool:
        return not self.is_halted()


def recover_open_position(ledger: TradeLedger) -> dict | None:
    """Return persisted BUY position facts after a process restart."""
    return ledger.snapshot()["open_position"]


def operational_buy_allowed(
    *,
    kill_switch: KillSwitch,
    risk_state: RiskState,
    daily_loss_fraction: float | None = None,
    max_daily_loss_fraction: float | None = None,
) -> tuple[bool, str | None]:
    if kill_switch.is_halted():
        return False, "kill_switch_engaged"
    if max_daily_loss_fraction is not None and daily_loss_fraction is not None and daily_loss_fraction <= -max_daily_loss_fraction:
        return False, "daily_loss_limit"
    return True, None
