"""Generate deterministic BUY intents from the WickHunter strategy engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .engine import EngineConfig, WickHunterEngine
from .models import Candle


@dataclass(frozen=True)
class BuyIntent:
    """Broker-neutral approved BUY intent produced by the strategy layer."""

    session: str
    time: datetime
    trigger: float
    stop: float
    target: float
    risk_fraction: float
    spread: float
    signal_time: datetime
    confirmation_time: datetime
    expires_at: datetime

    def as_dict(self) -> dict:
        data = asdict(self)
        for key in ("time", "signal_time", "confirmation_time", "expires_at"):
            data[key] = data[key].isoformat()
        return data


def generate_buy_intents(
    sessions: dict[str, Iterable[Candle]],
    levels: dict,
    *,
    minimum_reward_risk: float = 1.5,
    stop_buffer: float = 0.0,
    max_trades_per_day: int = 1,
    risk_fraction: float = 0.01,
) -> list[BuyIntent]:
    """Generate at most the configured number of BUY intents per session.

    The engine remains the sole source of strategy decisions. The exported
    intent is valid only during the immediate confirmation M1 candle.
    """
    if not 0 < risk_fraction <= 1:
        raise ValueError("risk_fraction must be in (0, 1]")
    intents: list[BuyIntent] = []
    config = EngineConfig(
        minimum_reward_risk=minimum_reward_risk,
        stop_buffer=stop_buffer,
        max_trades_per_day=max_trades_per_day,
    )
    for session in sorted(sessions):
        if session not in levels:
            continue
        day = levels[session]
        engine = WickHunterEngine(day.pdl, day.pdh, config)
        for candle in sessions[session]:
            event = engine.on_candle(candle)
            if not event or event.get("action") != "BUY":
                continue
            confirmation_time = event["confirmation_time"]
            intents.append(BuyIntent(
                session=session,
                time=confirmation_time,
                trigger=float(event["entry"]),
                stop=float(event["stop"]),
                target=float(event["target"]),
                risk_fraction=risk_fraction,
                spread=float(candle.spread),
                signal_time=event["signal_time"],
                confirmation_time=confirmation_time,
                expires_at=confirmation_time + timedelta(minutes=1),
            ))
            break
    return intents


def intents_to_jsonable(intents: list[BuyIntent]) -> list[dict]:
    """Return JSON-safe dictionaries for CLI/report serialization."""
    return [intent.as_dict() for intent in intents]
