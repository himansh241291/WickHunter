"""Dependency-free CSV and session preparation helpers for WickHunter."""

import csv
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .backtest import DailyLevels
from .models import Candle


REQUIRED_COLUMNS = {"time", "open", "high", "low", "close"}


def load_m1_csv(path: str | Path) -> list[Candle]:
    """Load M1 OHLC CSV with ISO-8601, timezone-aware timestamps."""
    candles: list[Candle] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Missing CSV columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            timestamp = datetime.fromisoformat(row["time"])
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError(f"Timestamp at CSV line {line_number} must be timezone-aware")
            candles.append(Candle(
                time=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                spread=float(row.get("spread") or 0.0),
            ))

    candles.sort(key=lambda candle: candle.time)
    for previous, current in zip(candles, candles[1:]):
        if current.time == previous.time:
            raise ValueError(f"Duplicate candle timestamp: {current.time.isoformat()}")
    return candles


def prepare_sessions(
    candles: list[Candle],
    timezone_name: str = "UTC",
) -> tuple[dict[str, list[Candle]], dict[str, DailyLevels]]:
    """Group candles by explicit local trading date and derive prior levels.

    Missing calendar days are treated as non-trading days: the previous
    available session supplies PDH/PDL. Current and future candles are never
    used to construct a session's levels.
    """
    timezone = ZoneInfo(timezone_name)
    grouped: OrderedDict[str, list[Candle]] = OrderedDict()

    for candle in sorted(candles, key=lambda item: item.time):
        session = candle.time.astimezone(timezone).date().isoformat()
        grouped.setdefault(session, []).append(candle)

    sessions = dict(grouped)
    levels: dict[str, DailyLevels] = {}
    session_names = list(grouped)
    for index in range(1, len(session_names)):
        current = session_names[index]
        previous = grouped[session_names[index - 1]]
        levels[current] = DailyLevels(
            session=current,
            pdh=max(c.high for c in previous),
            pdl=min(c.low for c in previous),
        )

    return sessions, levels
