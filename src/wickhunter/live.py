"""Broker-neutral live BUY coordinator for WickHunter.

This module contains timing/orchestration only. It does not contain broker
credentials or network code. A completed signal candle arms a BUY trigger for
the immediately following M1 candle; ordered ticks determine whether the
trigger is actually filled before expiry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .engine import EngineConfig, State, WickHunterEngine
from .models import Candle
from .ports import BuyExecutionPort, BuyOrder, OrderReceipt
from .risk import BuyRiskGuard, RiskLimits, RiskState


@dataclass(frozen=True)
class ArmedBuy:
    order: BuyOrder
    expires_at: datetime
    signal_time: datetime


class BuyCoordinator:
    """Coordinate completed M1 strategy decisions into BUY-only execution."""

    def __init__(
        self,
        *,
        pdl: float,
        pdh: float,
        execution: BuyExecutionPort,
        risk_state: RiskState,
        risk_limits: RiskLimits | None = None,
        engine_config: EngineConfig | None = None,
    ) -> None:
        self.engine = WickHunterEngine(pdl, pdh, engine_config)
        self.execution = execution
        self.risk_state = risk_state
        self.risk_guard = BuyRiskGuard(risk_limits)
        self.armed: ArmedBuy | None = None
        self.receipt: OrderReceipt | None = None

    def on_completed_candle(self, candle: Candle) -> ArmedBuy | None:
        """Process a completed M1 candle and arm the next-candle BUY trigger.

        The important timing rule is that the signal candle is complete before
        the order is armed. The confirmation candle has not completed yet.
        """
        if self.armed is not None or self.receipt is not None:
            return self.armed
        self.engine.on_candle(candle)
        if self.engine.state != State.LONG_READY or self.engine.signal is None:
            return None

        signal = self.engine.signal
        order = BuyOrder(
            time=candle.time + timedelta(minutes=1),
            quantity=0.0,
            trigger=signal.signal_high,
            stop=signal.sweep_low - self.engine.config.stop_buffer,
            target=self.engine.pdh,
        )
        if order.target <= order.trigger or order.stop >= order.trigger:
            self.engine.state = State.DONE
            return None
        self.armed = ArmedBuy(order, order.time + timedelta(minutes=1), signal.time)
        return self.armed

    def on_tick(self, tick_time: datetime, price: float, *, spread: float = 0.0) -> OrderReceipt | None:
        """Fill the armed BUY on the first eligible tick at/above trigger."""
        armed = self.armed
        if armed is None or self.receipt is not None:
            return self.receipt
        if tick_time <= armed.order.time:
            return None
        if tick_time >= armed.expires_at:
            self.armed = None
            self.engine.state = State.DONE
            return None
        if price < armed.order.trigger:
            return None

        decision = self.risk_guard.check_buy(
            self.risk_state,
            entry=price,
            stop=armed.order.stop,
            requested_risk_fraction=min(
                self.risk_guard.limits.max_risk_fraction, 0.01
            ),
            spread=spread,
            expected_slippage=0.0,
        )
        if not decision.allowed:
            self.armed = None
            self.engine.state = State.DONE
            return None

        order = BuyOrder(
            time=tick_time,
            quantity=decision.quantity,
            trigger=armed.order.trigger,
            stop=armed.order.stop,
            target=armed.order.target,
        )
        receipt = self.execution.submit_buy(order)
        self.receipt = receipt
        self.armed = None
        self.risk_state.trades_today += 1
        self.engine.trades += 1
        self.engine.state = State.POSITION_OPEN
        return receipt
