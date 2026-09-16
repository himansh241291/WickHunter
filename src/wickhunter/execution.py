"""Portable execution-cost primitives for WickHunter research.

The strategy remains BUY-only. This module contains no order-direction logic;
it only models adverse execution effects for a long entry/exit.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionConfig:
    """Deterministic transaction-cost assumptions for backtests."""

    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    commission_per_unit: float = 0.0

    def __post_init__(self) -> None:
        if self.entry_slippage < 0:
            raise ValueError("entry_slippage cannot be negative")
        if self.exit_slippage < 0:
            raise ValueError("exit_slippage cannot be negative")
        if self.commission_per_unit < 0:
            raise ValueError("commission_per_unit cannot be negative")


class LongExecutionModel:
    """Apply adverse execution costs to a long trade.

    Entry slippage raises the executed BUY price. Exit slippage lowers the
    executed long-exit price. Commission is charged per unit on each side.
    """

    def __init__(self, config: ExecutionConfig | None = None):
        self.config = config or ExecutionConfig()

    def entry_price(self, trigger_price: float) -> float:
        return trigger_price + self.config.entry_slippage

    def exit_price(self, trigger_price: float) -> float:
        return trigger_price - self.config.exit_slippage

    def commission(self, quantity: float) -> float:
        if quantity < 0:
            raise ValueError("quantity cannot be negative")
        return quantity * self.config.commission_per_unit * 2.0

    def net_pnl(self, entry: float, exit: float, quantity: float) -> float:
        if quantity < 0:
            raise ValueError("quantity cannot be negative")
        executed_entry = self.entry_price(entry)
        executed_exit = self.exit_price(exit)
        gross = (executed_exit - executed_entry) * quantity
        return gross - self.commission(quantity)
