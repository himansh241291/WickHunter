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

    This function deliberately accepts BUY intents only; strategy generation
    remains in the WickHunter engine and is not duplicated here.
    """
    state = RiskState(starting_equity=starting_equity, equity=starting_equity)
    switch = KillSwitch(ledger) if ledger else None
    broker = PaperBroker(state, ledger=ledger, kill_switch=switch)
    intent_by_time = sorted(intents, key=lambda item: datetime.fromisoformat(item["time"]))
    index = 0
    for tick in ticks:
        while index < len(intent_by_time) and datetime.fromisoformat(intent_by_time[index]["time"]) <= tick.time:
            intent = intent_by_time[index]
            broker.submit_buy(
                time=datetime.fromisoformat(intent["time"]),
                trigger=float(intent["trigger"]),
                stop=float(intent["stop"]),
                target=float(intent["target"]),
                requested_risk_fraction=float(intent.get("risk_fraction", risk_fraction)),
                spread=float(intent.get("spread", 0.0)),
            )
            index += 1
        broker.process_tick(tick)
    return state
