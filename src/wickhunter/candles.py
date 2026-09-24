"""Build completed NSE M1 candles from ordered market-data ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketTick:
    """Normalized market-data tick used by the candle builder."""

    time: datetime
    price: float
    cumulative_volume: int | None = None

    def __post_init__(self) -> None:
        if self.time.tzinfo is None:
            raise ValueError("tick time must be timezone-aware")
        if self.price <= 0:
            raise ValueError("tick price must be positive")
        if self.cumulative_volume is not None and self.cumulative_volume < 0:
            raise ValueError("cumulative volume cannot be negative")


@dataclass(frozen=True)
class M1Candle:
    """Completed one-minute OHLCV candle."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self) -> None:
        if self.time.tzinfo is None:
            raise ValueError("candle time must be timezone-aware")
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise ValueError("candle prices must be positive")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= open and close")
        if self.low > self.high:
            raise ValueError("low must be <= high")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")


def fyers_tick(message: Mapping[str, Any], *, timezone_name: str = "Asia/Kolkata") -> MarketTick:
    """Convert a FYERS SymbolUpdate message into a normalized tick."""
    raw_time = message.get("exch_feed_time", message.get("last_traded_time"))
    if raw_time is None:
        raise ValueError("FYERS tick is missing exch_feed_time/last_traded_time")
    price = message.get("ltp")
    if price is None:
        raise ValueError("FYERS tick is missing ltp")
    timestamp = datetime.fromtimestamp(float(raw_time), tz=timezone.utc)
    local_time = timestamp.astimezone(ZoneInfo(timezone_name))
    cumulative_volume = message.get("vol_traded_today")
    if cumulative_volume is not None:
        cumulative_volume = int(cumulative_volume)
    return MarketTick(time=local_time, price=float(price), cumulative_volume=cumulative_volume)


class M1CandleBuilder:
    """Aggregate ordered ticks into completed session-bound M1 candles."""

    def __init__(
        self,
        *,
        timezone_name: str = "Asia/Kolkata",
        session_start: time = time(9, 15),
        session_end: time = time(15, 30),
    ) -> None:
        if session_start >= session_end:
            raise ValueError("session_start must be before session_end")
        self.zone = ZoneInfo(timezone_name)
        self.session_start = session_start
        self.session_end = session_end
        self._minute: datetime | None = None
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._close: float | None = None
        self._volume = 0
        self._last_time: datetime | None = None
        self._last_cumulative_volume: int | None = None

    def add(self, tick: MarketTick) -> list[M1Candle]:
        """Accept one tick and return any newly completed candles."""
        local = tick.time.astimezone(self.zone)
        if not self._in_session(local):
            return self._advance_outside_session(local)
        if self._last_time is not None and local < self._last_time:
            return []

        minute = local.replace(second=0, microsecond=0)
        completed: list[M1Candle] = []
        if self._minute is not None and minute > self._minute:
            completed.append(self._emit())
            self._reset_minute()

        if self._minute is None:
            self._minute = minute
            self._open = tick.price
            self._high = tick.price
            self._low = tick.price
            self._close = tick.price
        else:
            self._high = max(self._high, tick.price)
            self._low = min(self._low, tick.price)
            self._close = tick.price

        if tick.cumulative_volume is not None:
            if self._last_cumulative_volume is None:
                self._last_cumulative_volume = tick.cumulative_volume
            else:
                delta = tick.cumulative_volume - self._last_cumulative_volume
                self._last_cumulative_volume = tick.cumulative_volume
                if delta >= 0:
                    self._volume += delta

        self._last_time = local
        return completed

    def flush(self) -> M1Candle | None:
        """Explicitly emit the current partial minute."""
        if self._minute is None:
            return None
        candle = self._emit()
        self._reset_minute()
        return candle

    def _advance_outside_session(self, local: datetime) -> list[M1Candle]:
        if self._minute is None:
            return []
        if local.date() != self._minute.date() or local.time() >= self.session_end:
            candle = self._emit()
            self._reset_minute()
            return [candle]
        return []

    def _in_session(self, local: datetime) -> bool:
        return self.session_start <= local.time() < self.session_end

    def _emit(self) -> M1Candle:
        assert self._minute is not None
        assert self._open is not None
        assert self._high is not None
        assert self._low is not None
        assert self._close is not None
        return M1Candle(
            time=self._minute,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
        )

    def _reset_minute(self) -> None:
        self._minute = None
        self._open = None
        self._high = None
        self._low = None
        self._close = None
        self._volume = 0
