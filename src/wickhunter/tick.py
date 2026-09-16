"""Tick-level execution primitives for WickHunter research.

This module is intentionally strategy-agnostic: it models how a BUY trigger,
stop and target can be resolved when ordered ticks are available.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class Tick:
    time: datetime
    price: float

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("tick price must be positive")


@dataclass(frozen=True)
class TickExecution:
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    result: str


def resolve_long_entry(ticks: Iterable[Tick], trigger: float) -> Tick | None:
    """Return the first tick at or above a BUY trigger."""
    if trigger <= 0:
        raise ValueError("trigger must be positive")
    for tick in ticks:
        if tick.price >= trigger:
            return tick
    return None


def resolve_long_exit(
    ticks: Iterable[Tick],
    stop: float,
    target: float,
) -> tuple[Tick, str] | None:
    """Resolve the first ordered stop/target touch after entry.

    With actual ordered ticks there is no OHLC ambiguity: whichever threshold
    is observed first determines the exit.
    """
    if stop <= 0 or target <= 0 or target <= stop:
        raise ValueError("require 0 < stop < target")
    for tick in ticks:
        if tick.price <= stop:
            return tick, "LOSS"
        if tick.price >= target:
            return tick, "WIN"
    return None
