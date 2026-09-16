"""Dependency-free CSV adapter for portable WickHunter backtests."""

import csv
from datetime import datetime
from pathlib import Path

from .models import Candle


REQUIRED_COLUMNS = {"time", "open", "high", "low", "close"}


def load_m1_csv(path: str | Path) -> list[Candle]:
    """Load UTC/offset-aware M1 OHLC CSV.

    Expected columns: time,open,high,low,close[,spread].
    Timestamps should be ISO-8601; a timezone offset is strongly recommended.
    """
    candles: list[Candle] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"Missing CSV columns: {sorted(missing)}")
        for row in reader:
            candles.append(Candle(
                time=datetime.fromisoformat(row["time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                spread=float(row.get("spread") or 0.0),
            ))
    return candles
