"""Broker-neutral ports for future live BUY execution.

The strategy does not know which broker, exchange, or transport is used.
Only explicit BUY submission and long-position lifecycle operations are
represented here; there is intentionally no SELL/short order port.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .tick import Tick


@dataclass(frozen=True)
class BuyOrder:
    """A fully specified BUY order request."""

    time: datetime
    quantity: float
    trigger: float
    stop: float
    target: float


@dataclass(frozen=True)
class OrderReceipt:
    """Broker acknowledgement for a BUY order."""

    order_id: str
    time: datetime
    fill_price: float
    quantity: float


class MarketDataPort(Protocol):
    """Minimal market-data contract required by a live adapter."""

    def ticks(self):
        """Yield timezone-aware ordered Tick objects."""
        ...


class BuyExecutionPort(Protocol):
    """Minimal execution contract for a BUY-only adapter."""

    def submit_buy(self, order: BuyOrder) -> OrderReceipt:
        ...

    def close_long(self, *, time: datetime, price: float) -> None:
        """Close an already-open long position for lifecycle management."""
        ...

    def position(self) -> dict | None:
        ...


class TickConsumer(Protocol):
    """Optional interface for components consuming live ticks."""

    def on_tick(self, tick: Tick) -> None:
        ...
