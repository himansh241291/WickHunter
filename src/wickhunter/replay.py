"""Deterministic paper replay from ordered tick CSV and approved BUY intents."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .ledger import TradeLedger
from .paper import PaperBroker
from .risk import RiskState
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
            ticks.append(Tick(datetime.fromisoformat(row["time"]), float(row["price"])))
    ticks.sort(key=lambda item: item.time)
    return ticks


def replay_buy_intents(
    ticks: list[Tick],
    intents: list[dict],
    *,
    starting_equity: float = 100_000.0,
    risk_fraction: float = 0.01,
    ledger: TradeLedger | None = None,
) -> RiskState:
    """Replay pre-approved BUY intents against ordered ticks.

    An intent becomes eligible after its confirmation-candle timestamp and is
    not filled until a strictly later ordered tick reaches its BUY trigger.
    This prevents ticks belonging to the already-completed confirmation
    candle from leaking into execution. The observed tick price is used as
    the fill trigger, so gap-through-trigger execution is modeled.

    Sessions are separated by the tick's local offset date: an open position
    is liquidated at the last tick of the prior date and daily risk counters
    reset before the next date begins. Pending intents do not cross sessions.

    This function deliberately accepts BUY intents only; strategy generation
    remains in the WickHunter engine and is not duplicated here.
    """
    state = RiskState(starting_equity=starting_equity, equity=starting_equity)
    switch = KillSwitch(ledger) if ledger else None
    broker = PaperBroker(state, ledger=ledger, kill_switch=switch)
    intent_by_time = sorted(intents, key=lambda item: datetime.fromisoformat(item["time"]))
    pending: list[dict] = []
    index = 0
    previous_tick: Tick | None = None
    session_date = None

    for tick in ticks:
        if session_date is None:
            session_date = tick.time.date()
        elif tick.time.date() != session_date:
            if broker.position is not None and previous_tick is not None:
                broker.close_session(time=previous_tick.time, price=previous_tick.price)
            state.reset_day()
            pending.clear()
            session_date = tick.time.date()

        while index < len(intent_by_time) and datetime.fromisoformat(intent_by_time[index]["time"]) < tick.time:
            pending.append(intent_by_time[index])
            index += 1

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
    return state
