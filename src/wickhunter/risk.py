"""BUY-only risk guardrails for paper and future broker-neutral execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_risk_fraction: float = 0.01
    max_trades_per_day: int = 1
    max_daily_loss_fraction: float | None = None
    max_consecutive_losses: int | None = None
    max_spread: float | None = None
    max_slippage: float | None = None

    def __post_init__(self):
        if not 0 < self.max_risk_fraction <= 1:
            raise ValueError("max_risk_fraction must be in (0, 1]")
        if self.max_trades_per_day < 1:
            raise ValueError("max_trades_per_day must be >= 1")
        for name in ("max_daily_loss_fraction", "max_spread", "max_slippage"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.max_consecutive_losses is not None and self.max_consecutive_losses < 1:
            raise ValueError("max_consecutive_losses must be >= 1")


@dataclass
class RiskState:
    starting_equity: float
    equity: float
    trades_today: int = 0
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    day_starting_equity: float | None = None

    def __post_init__(self):
        if self.starting_equity <= 0 or self.equity <= 0:
            raise ValueError("equity must be positive")
        if self.day_starting_equity is None:
            self.day_starting_equity = self.equity
        if self.day_starting_equity <= 0:
            raise ValueError("day_starting_equity must be positive")

    def reset_day(self):
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.day_starting_equity = self.equity

    def record_close(self, pnl: float):
        self.equity += pnl
        self.daily_pnl += pnl
        if self.equity <= 0:
            raise ValueError("equity cannot become non-positive")
        if pnl < 0:
            self.consecutive_losses += 1
        elif pnl > 0:
            self.consecutive_losses = 0


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str | None = None
    quantity: float = 0.0


class BuyRiskGuard:
    """Checks whether a proposed BUY may be opened and sizes it by stop risk."""

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def check_buy(
        self,
        state: RiskState,
        *,
        entry: float,
        stop: float,
        requested_risk_fraction: float,
        spread: float = 0.0,
        expected_slippage: float = 0.0,
    ) -> RiskDecision:
        if stop >= entry:
            return RiskDecision(False, "invalid_long_stop")
        if not 0 < requested_risk_fraction <= self.limits.max_risk_fraction:
            return RiskDecision(False, "risk_fraction_limit")
        if state.trades_today >= self.limits.max_trades_per_day:
            return RiskDecision(False, "max_trades_per_day")
        if self.limits.max_consecutive_losses is not None and state.consecutive_losses >= self.limits.max_consecutive_losses:
            return RiskDecision(False, "max_consecutive_losses")
        if self.limits.max_daily_loss_fraction is not None:
            loss_limit = state.day_starting_equity * self.limits.max_daily_loss_fraction
            if state.daily_pnl <= -loss_limit:
                return RiskDecision(False, "max_daily_loss")
        if self.limits.max_spread is not None and spread > self.limits.max_spread:
            return RiskDecision(False, "max_spread")
        if self.limits.max_slippage is not None and expected_slippage > self.limits.max_slippage:
            return RiskDecision(False, "max_slippage")
        risk_per_unit = entry - stop
        quantity = state.equity * requested_risk_fraction / risk_per_unit
        if quantity <= 0:
            return RiskDecision(False, "invalid_quantity")
        return RiskDecision(True, quantity=quantity)
