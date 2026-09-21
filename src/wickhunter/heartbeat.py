"""Market-data heartbeat and stale-feed safety guard."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FeedHealth:
    max_age: timedelta
    last_tick: datetime | None = None
    halted: bool = False
    reason: str | None = None

    def observe(self, tick_time: datetime) -> None:
        if tick_time.tzinfo is None or tick_time.utcoffset() is None:
            raise ValueError("tick_time must be timezone-aware")
        if self.last_tick is not None and tick_time <= self.last_tick:
            raise ValueError("tick timestamps must increase")
        self.last_tick = tick_time
        self.halted = False
        self.reason = None

    def check(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if self.last_tick is None:
            self.halted = True
            self.reason = "no_market_data"
            return False
        age = now - self.last_tick
        if age > self.max_age:
            self.halted = True
            self.reason = "stale_market_data"
            return False
        return True

    def allow_buy(self, now: datetime) -> bool:
        return self.check(now) and not self.halted
