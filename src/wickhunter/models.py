"""Core immutable data models used by the portable WickHunter engine."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    spread: float = 0.0

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= open and close")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= open and close")
        if self.low > self.high:
            raise ValueError("low must be <= high")
        if self.spread < 0:
            raise ValueError("spread cannot be negative")

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def close_location(self) -> float:
        """Close location in [0, 1], measured from candle low to high."""
        if self.range == 0:
            return 0.0
        return (self.close - self.low) / self.range


@dataclass(frozen=True)
class SweepEvent:
    start_time: datetime
    pdl: float
    sweep_low: float


@dataclass(frozen=True)
class Signal:
    time: datetime
    signal_high: float
    signal_low: float
    sweep_low: float
    pdl: float


@dataclass(frozen=True)
class Trade:
    entry_time: datetime
    entry: float
    stop: float
    target: float
    risk_per_unit: float
    reward_per_unit: float
    reward_risk: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    result: Optional[str] = None


@dataclass(frozen=True)
class SetupRejection:
    time: datetime
    reason: str
