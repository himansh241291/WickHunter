"""Deterministic paper replay from ordered tick CSV and approved BUY intents."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .ledger import TradeLedger
from .paper import PaperBroker
from .risk import BuyRiskGuard, RiskLimits, RiskState
from .safety import KillSwitch
from .tick import Tick


def load_ticks(path: str | Path) -> list[Tick]:
    """Load ordered ticks with `time,price` columns."""
    ticks: list[Tick] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"time", "price"}.issubset(reader.fieldnames):
            raise ValueError("Tick CSV requires time,price columns")
        for row in reader:
            timestamp = datetime.fromisoformat(row["time"])
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("tick timestamps must be timezone-aware")
            ticks.append(Tick(timestamp, float(row["price"])))
    ticks.sort(key=lambda item: item.time)
    return ticks


def _intent_expiry(intent: dict) -> datetime:
    """Return explicit expiry, with v0.1 compatibility for older intents."""
    if "expires_at" in intent:
        expiry = datetime.fromisoformat(intent["expires_at"])
    else:
        expiry = datetime.fromisoformat(intent["time"]) + timedelta(minutes=1)
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ValueError("intent timestamps must be timezone-aware")
    return expiry


def replay_buy_intents(
    ticks: list[Tick],
    intents: list[dict],
    *,
    starting_equity: float = 100_000.0,
    risk_fraction: float = 0.01,
    risk_limits: RiskLimits | None = None,
    ledger: TradeLedger | None = None,
    timezone_name: str = "UTC",
) -> RiskState:
    """Replay pre-approved BUY intents against ordered ticks.

    An intent is eligible only during its immediate confirmation M1 candle.
    It fills on the first ordered tick at/after its intent timestamp and
    before expiry that reaches the BUY trigger. The observed tick price is
    the fill price, so gap-through-trigger execution is modeled without
    inventing an unobserved price.

    Session boundaries are determined in the supplied IANA timezone rather
    than from the source timestamp's UTC date. This keeps daily risk limits
    aligned with the same session calendar used by strategy data preparation.
    """
    session_tz = ZoneInfo(timezone_name)
    state = RiskState(starting_equity=starting_equity, equity=starting_equity)
    switch = KillSwitch(ledger) if ledger else None
    broker = PaperBroker(
        state,
        risk_guard=BuyRiskGuard(risk_limits),
        ledger=ledger,
        kill_switch=switch,
    )
    intent_by_time = sorted(intents, key=lambda item: datetime.fromisoformat(item["time"]))
    pending: list[dict] = []
    index = 0
    previous_tick: Tick | None = None
    session_date = None

    for tick in ticks:
        tick_session_date = tick.time.astimezone(session_tz).date()
        if session_date is None:
            session_date = tick_session_date
        elif tick_session_date != session_date:
            if broker.position is not None and previous_tick is not None:
                broker.close_session(time=previous_tick.time, price=previous_tick.price)
            state.reset_day()
            pending.clear()
            session_date = tick_session_date

        while index < len(intent_by_time) and datetime.fromisoformat(intent_by_time[index]["time"]) <= tick.time:
            pending.append(intent_by_time[index])
            index += 1

        if pending:
            pending[:] = [item for item in pending if tick.time < _intent_expiry(item)]

        if broker.position is None:
            for intent in pending:
                if tick.price < float(intent["trigger"]):
                    continue
                submitted = broker.submit_buy(
                    time=tick.time,
                    trigger=tick.price,
                    stop=float(intent["stop"]),
                    target=float(intent["target"]),
                    requested_risk_fraction=float(intent.get("risk_fraction", risk_fraction)),
                    spread=float(intent.get("spread", 0.0)),
                )
                pending.remove(intent)
                if submitted is not None:
                    break

        broker.process_tick(tick)
        previous_tick = tick

    if broker.position is not None and previous_tick is not None:
        broker.close_session(time=previous_tick.time, price=previous_tick.price)
    return state
