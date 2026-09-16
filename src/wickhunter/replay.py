"""Deterministic paper replay from ordered tick CSV and approved BUY intents."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .ledger import TradeLedger
from .paper import PaperBroker
from .risk import BuyRiskGuard, RiskLimits, RiskState
from .safety import KillSwitch, recover_open_position, recover_risk_state
from .tick import Tick


def load_ticks(path: str | Path) -> list[Tick]:
    """Load and validate ordered ticks with `time,price` columns."""
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
    _validate_ticks(ticks)
    return ticks


def _validate_ticks(ticks: list[Tick]) -> None:
    previous: datetime | None = None
    for tick in ticks:
        if tick.time.tzinfo is None or tick.time.utcoffset() is None:
            raise ValueError("tick timestamps must be timezone-aware")
        if previous is not None and tick.time <= previous:
            raise ValueError("replay ticks must be strictly increasing")
        previous = tick.time


def _intent_time(intent: dict) -> datetime:
    try:
        timestamp = datetime.fromisoformat(intent["time"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("intent requires a valid ISO-8601 time") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("intent timestamps must be timezone-aware")
    return timestamp


def _intent_expiry(intent: dict) -> datetime:
    """Return explicit expiry, with compatibility for older intents."""
    intent_time = _intent_time(intent)
    if "expires_at" in intent:
        expiry = datetime.fromisoformat(intent["expires_at"])
    else:
        expiry = intent_time + timedelta(minutes=1)
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ValueError("intent timestamps must be timezone-aware")
    if expiry <= intent_time:
        raise ValueError("intent expires_at must be later than intent time")
    return expiry


def _validate_intents(intents: list[dict]) -> None:
    previous: datetime | None = None
    for intent in intents:
        timestamp = _intent_time(intent)
        _intent_expiry(intent)
        for field in ("trigger", "stop", "target"):
            if field not in intent:
                raise ValueError(f"intent requires {field}")
        if previous is not None and timestamp < previous:
            raise ValueError("replay intents must be chronological")
        previous = timestamp


def replay_buy_intents(
    ticks: list[Tick], intents: list[dict], *, starting_equity: float = 100_000.0,
    risk_fraction: float = 0.01, risk_limits: RiskLimits | None = None,
    ledger: TradeLedger | None = None, timezone_name: str = "UTC", resume: bool = False,
) -> RiskState:
    """Replay approved BUY intents against ordered ticks."""
    session_tz = ZoneInfo(timezone_name)
    _validate_ticks(ticks)
    _validate_intents(intents)
    if not ticks:
        raise ValueError("at least one tick is required for replay")
    if resume and ledger is None:
        raise ValueError("resume requires a ledger")

    cutoff: datetime | None = None
    if resume and ledger is not None:
        last_event = ledger.latest()
        cutoff = last_event.time if last_event is not None else None
        state = recover_risk_state(ledger, starting_equity=starting_equity, as_of=ticks[-1].time)
    else:
        state = RiskState(starting_equity=starting_equity, equity=starting_equity)

    switch = KillSwitch(ledger) if ledger else None
    broker = PaperBroker(state, risk_guard=BuyRiskGuard(risk_limits), ledger=ledger, kill_switch=switch)
    if resume and ledger is not None:
        persisted = recover_open_position(ledger)
        if persisted is not None:
            broker.restore_open_position(persisted)
            entry_session = datetime.fromisoformat(persisted["entry_time"]).astimezone(session_tz).date()
            first_session = ticks[0].time.astimezone(session_tz).date()
            if entry_session != first_session:
                raise ValueError("resume tick stream must include the open position's session")

    intent_by_time = sorted(intents, key=_intent_time)
    if cutoff is not None:
        intent_by_time = [item for item in intent_by_time if _intent_time(item) > cutoff]

    pending: list[dict] = []
    index = 0
    previous_tick: Tick | None = None
    session_date = None
    for tick in ticks:
        if cutoff is not None and tick.time <= cutoff:
            continue
        tick_session_date = tick.time.astimezone(session_tz).date()
        if session_date is None:
            session_date = tick_session_date
        elif tick_session_date != session_date:
            if broker.position is not None and previous_tick is not None:
                broker.close_session(time=previous_tick.time, price=previous_tick.price)
            state.reset_day()
            pending.clear()
            session_date = tick_session_date

        while index < len(intent_by_time) and _intent_time(intent_by_time[index]) <= tick.time:
            pending.append(intent_by_time[index])
            index += 1
        pending[:] = [item for item in pending if tick.time < _intent_expiry(item)]

        if broker.position is None:
            for intent in pending:
                intent_time = _intent_time(intent)
                if tick.time <= intent_time or tick.price < float(intent["trigger"]):
                    continue
                submitted = broker.submit_buy(
                    time=tick.time, trigger=tick.price, stop=float(intent["stop"]),
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
