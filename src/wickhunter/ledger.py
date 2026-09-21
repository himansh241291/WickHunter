"""Durable append-only JSONL ledger for WickHunter paper/live-safe state."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LedgerEvent:
    time: datetime
    event: str
    data: dict[str, Any]


class TradeLedger:
    """Append-only event ledger with flush+fsync durability."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, *, time: datetime, **data: Any) -> None:
        record = {"time": time.isoformat(), "event": event, "data": data}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def events(self) -> list[LedgerEvent]:
        if not self.path.exists():
            return []
        result: list[LedgerEvent] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    event_time = datetime.fromisoformat(raw["time"])
                    if event_time.tzinfo is None or event_time.utcoffset() is None:
                        raise ValueError("ledger timestamp must be timezone-aware")
                    result.append(LedgerEvent(event_time, raw["event"], raw.get("data", {})))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid ledger record at line {line_no}") from exc
        return result

    def latest(self, event: str | None = None) -> LedgerEvent | None:
        items = self.events()
        if event is not None:
            items = [item for item in items if item.event == event]
        return items[-1] if items else None

    def snapshot(self) -> dict[str, Any]:
        """Recover latest lifecycle facts without mutating the ledger."""
        position: dict[str, Any] | None = None
        pending_buy: dict[str, Any] | None = None
        pending_close: dict[str, Any] | None = None
        halted = False
        for item in self.events():
            if item.event == "BUY_INTENT":
                pending_buy = {"time": item.time.isoformat(), **item.data}
            elif item.event == "BUY_FILLED":
                pending_buy = None
                position = {"entry_time": item.time.isoformat(), **item.data}
            elif item.event in {"BUY_EXPIRED", "BUY_CANCELLED"}:
                pending_buy = None
            elif item.event == "SESSION_END":
                pending_close = None
                position = None
            elif item.event == "LONG_CLOSE_INTENT":
                pending_close = {"time": item.time.isoformat(), **item.data}
            elif item.event == "POSITION_CLOSED":
                pending_close = None
                position = None
            elif item.event == "KILL_SWITCH_ON":
                halted = True
            elif item.event == "KILL_SWITCH_OFF":
                halted = False
        return {
            "open_position": position,
            "pending_buy": pending_buy,
            "pending_close": pending_close,
            "halted": halted,
        }
