"""Persistent BUY-only operational safety controls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

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


def recover_risk_state(
    ledger: TradeLedger,
    *,
    starting_equity: float,
    as_of: datetime | None = None,
    timezone_name: str = "UTC",
) -> RiskState:
    """Reconstruct account/risk counters from the append-only ledger."""
    events = ledger.events()
    tz = ZoneInfo(timezone_name)
    if as_of is None:
        as_of = events[-1].time if events else datetime.now(tz)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of_local_date = as_of.astimezone(tz).date()

    equity = starting_equity
    day_starting_equity = starting_equity
    daily_pnl = 0.0
    trades_today = 0
    consecutive_losses = 0
    current_day_started = False

    for item in events:
        if item.time > as_of:
            raise ValueError("ledger contains future event relative to as_of")
        if item.event == "BUY_FILLED":
            if item.time.astimezone(tz).date() == as_of_local_date
                if not current_day_started:
                    day_starting_equity = equity
                    current_day_started = True
                trades_today += 1
        elif item.event == "POSITION_CLOSED":
            pnl = float(item.data.get("net_pnl", 0.0))
            if item.time.date() == as_of.date():
                if not current_day_started:
                    day_starting_equity = equity
                    current_day_started = True
                daily_pnl += pnl
            equity += pnl
            if item.time.astimezone(tz).date() != as_of_local_date
                day_starting_equity = equity
            if pnl < 0:
                consecutive_losses += 1
            elif pnl > 0:
                consecutive_losses = 0

    if not current_day_started:
        day_starting_equity = equity

    return RiskState(
        starting_equity=starting_equity,
        equity=equity,
        trades_today=trades_today,
        daily_pnl=daily_pnl,
        consecutive_losses=consecutive_losses,
        day_starting_equity=day_starting_equity,
    )


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
