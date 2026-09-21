"""Broker-neutral live BUY coordinator for WickHunter."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .engine import EngineConfig, State, WickHunterEngine
from .ledger import TradeLedger
from .models import Candle
from .ports import BuyExecutionPort, BuyOrder, OrderReceipt
from .reconcile import Reconciliation, reconcile_long_position
from .risk import BuyRiskGuard, RiskLimits, RiskState
from .safety import KillSwitch


@dataclass(frozen=True)
class ArmedBuy:
    order: BuyOrder
    expires_at: datetime
    signal_time: datetime


def buy_client_order_id(*, signal_time: datetime, trigger: float, stop: float, target: float) -> str:
    """Create a stable idempotency key for one strategy setup."""
    raw = f"{signal_time.isoformat()}|{trigger:.12g}|{stop:.12g}|{target:.12g}".encode()
    return "wh-buy-" + hashlib.sha256(raw).hexdigest()[:24]


class BuyCoordinator:
    """Coordinate completed M1 decisions into durable BUY-only execution."""

    def __init__(
        self,
        *,
        pdl: float,
        pdh: float,
        execution: BuyExecutionPort,
        risk_state: RiskState,
        risk_fraction: float = 0.01,
        risk_limits: RiskLimits | None = None,
        engine_config: EngineConfig | None = None,
        ledger: TradeLedger | None = None,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self.engine = WickHunterEngine(pdl, pdh, engine_config)
        self.execution = execution
        self.risk_state = risk_state
        self.risk_guard = BuyRiskGuard(risk_limits)
        self.risk_fraction = risk_fraction
        self.ledger = ledger
        self.kill_switch = kill_switch
        if not 0 < risk_fraction <= self.risk_guard.limits.max_risk_fraction:
            raise ValueError("risk_fraction exceeds configured BUY risk limit")
        self.armed: ArmedBuy | None = None
        self.receipt: OrderReceipt | None = None
        self.reconciliation: Reconciliation | None = None
        self.halted = bool(kill_switch and kill_switch.is_halted())

    def reconcile_startup(self) -> Reconciliation:
        """Fail closed unless ledger and broker agree on the open long."""
        snapshot = self.ledger.snapshot() if self.ledger else {"open_position": None, "halted": False}
        if snapshot.get("halted"):
            self.halted = True
        result = reconcile_long_position(snapshot["open_position"], self.execution.position())
        self.reconciliation = result
        if not result.safe_to_buy:
            self.halted = True
            self.engine.state = State.DONE
        return result

    def recover_pending_buy(self) -> ArmedBuy | None:
        """Restore an unfilled BUY intent after restart without creating a new ID."""
        if self.ledger is None or self.halted:
            return None
        snapshot = self.ledger.snapshot()
        pending = snapshot.get("pending_buy")
        if pending is None:
            return None
        required = {"time", "trigger", "stop", "target", "client_order_id",
                    "expires_at", "signal_time", "risk_fraction"}
        if not required.issubset(pending):
            raise ValueError("incomplete persisted BUY intent")
        broker_receipt = self.execution.find_buy_order(str(pending["client_order_id"]))
        if broker_receipt is not None:
            self._accept_receipt(broker_receipt, pending)
            return None

        order_time = datetime.fromisoformat(pending["time"])
        expires_at = datetime.fromisoformat(pending["expires_at"])
        signal_time = datetime.fromisoformat(pending["signal_time"])
        order = BuyOrder(
            time=order_time,
            quantity=float(pending.get("quantity", 0.0)),
            trigger=float(pending["trigger"]),
            stop=float(pending["stop"]),
            target=float(pending["target"]),
            client_order_id=str(pending["client_order_id"]),
        )
        self.armed = ArmedBuy(order, expires_at, signal_time)
        return self.armed

    def on_completed_candle(self, candle: Candle) -> ArmedBuy | None:
        if self.armed is not None or self.receipt is not None:
            return self.armed
        self.engine.on_candle(candle)
        if self.engine.state != State.LONG_READY or self.engine.signal is None:
            return None

        signal = self.engine.signal
        trigger = signal.signal_high
        stop = signal.sweep_low - self.engine.config.stop_buffer
        target = self.engine.pdh
        if target <= trigger or stop >= trigger:
            self.engine.state = State.DONE
            return None

        client_id = buy_client_order_id(
            signal_time=signal.time, trigger=trigger, stop=stop, target=target
        )
        order = BuyOrder(
            time=candle.time + timedelta(minutes=1),
            quantity=0.0,
            trigger=trigger,
            stop=stop,
            target=target,
            client_order_id=client_id,
        )
        self.armed = ArmedBuy(order, order.time + timedelta(minutes=1), signal.time)
        if self.ledger:
            self.ledger.append(
                "BUY_INTENT",
                time=order.time,
                trigger=order.trigger,
                stop=order.stop,
                target=order.target,
                quantity=0.0,
                client_order_id=order.client_order_id,
                expires_at=self.armed.expires_at.isoformat(),
                signal_time=signal.time.isoformat(),
                risk_fraction=self.risk_fraction,
            )
        return self.armed

    def on_tick(
        self, tick_time: datetime, price: float, *, spread: float = 0.0
    ) -> OrderReceipt | None:
        armed = self.armed
        if armed is None or self.receipt is not None or self.halted:
            return self.receipt
        if self.reconciliation is not None and not self.reconciliation.safe_to_buy:
            return None
        if tick_time <= armed.order.time:
            return None
        if tick_time >= armed.expires_at:
            self.armed = None
            self.engine.state = State.DONE
            if self.ledger:
                self.ledger.append(
                    "BUY_EXPIRED", time=tick_time,
                    client_order_id=armed.order.client_order_id
                )
            return None
        if price < armed.order.trigger:
            return None
        if armed.order.target <= price:
            self.armed = None
            self.engine.state = State.DONE
            if self.ledger:
                self.ledger.append(
                    "BUY_CANCELLED", time=tick_time,
                    client_order_id=armed.order.client_order_id,
                    reason="invalid_long_target_at_observed_price",
                )
            return None

        decision = self.risk_guard.check_buy(
            self.risk_state,
            entry=price,
            stop=armed.order.stop,
            requested_risk_fraction=self.risk_fraction,
            spread=spread,
            expected_slippage=0.0,
        )
        if not decision.allowed:
            self.armed = None
            self.engine.state = State.DONE
            if self.ledger:
                self.ledger.append(
                    "BUY_CANCELLED", time=tick_time,
                    client_order_id=armed.order.client_order_id,
                    reason=decision.reason or "risk_rejected",
                )
            return None

        order = BuyOrder(
            time=tick_time,
            quantity=decision.quantity,
            trigger=armed.order.trigger,
            stop=armed.order.stop,
            target=armed.order.target,
            client_order_id=armed.order.client_order_id,
        )
        # BUY_INTENT is durable before this call. If the process dies after the
        # broker accepts the order, restart can resubmit the same client ID.
        receipt = self.execution.submit_buy(order)
        self._accept_receipt(receipt, {"stop": order.stop, "target": order.target})
        return receipt

    def _accept_receipt(self, receipt: OrderReceipt, pending: dict[str, Any]) -> None:
        """Commit one broker acknowledgement exactly once to local state."""
        if self.receipt is not None:
            if self.receipt.order_id != receipt.order_id:
                raise RuntimeError("conflicting BUY receipt")
            return
        self.receipt = receipt
        self.armed = None
        self.risk_state.trades_today += 1
        self.engine.trades += 1
        self.engine.state = State.POSITION_OPEN
        if self.ledger:
            self.ledger.append(
                "BUY_FILLED",
                time=receipt.time,
                order_id=receipt.order_id,
                client_order_id=receipt.client_order_id,
                entry=receipt.fill_price,
                stop=float(pending["stop"]),
                target=float(pending["target"]),
                quantity=receipt.quantity,
            )
