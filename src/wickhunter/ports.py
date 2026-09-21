"""Broker-neutral BUY execution ports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .tick import Tick


@dataclass(frozen=True)
class BuyOrder:
    time: datetime
    quantity: float
    trigger: float
    stop: float
    target: float
    client_order_id: str = ""


@dataclass(frozen=True)
class OrderReceipt:
    order_id: str
    time: datetime
    fill_price: float
    quantity: float
    client_order_id: str = ""


class MarketDataPort(Protocol):
    def ticks(self):
        """Yield timezone-aware ordered Tick objects."""
        ...


class BuyExecutionPort(Protocol):
    """Minimal execution contract for a BUY-only adapter."""

    def submit_buy(self, order: BuyOrder) -> OrderReceipt:
        """Submit idempotently by client_order_id."""
        ...

    def find_buy_order(self, client_order_id: str) -> OrderReceipt | None:
        """Return an accepted/fill receipt for an existing client ID."""
        ...

    def close_long(self, *, time: datetime, price: float) -> None:
        """Close an already-open long position for lifecycle management."""
        ...

    def position(self) -> dict | None:
        """Return the broker's actual open long position, if any."""
        ...


class TickConsumer(Protocol):
    def on_tick(self, tick: Tick) -> None:
        ...
