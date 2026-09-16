"""Deterministic broker-neutral paper execution for WickHunter.

Only BUY entries exist. Position closure is lifecycle management for an
existing long position, never a short/SELL strategy signal.
"""

from dataclasses import dataclass
from datetime import datetime

from .execution import ExecutionConfig, LongExecutionModel
from .ledger import TradeLedger
from .risk import BuyRiskGuard, RiskState
from .safety import KillSwitch
from .tick import Tick


@dataclass(frozen=True)
class PaperPosition:
    entry_time: datetime
    entry: float
    stop: float
    target: float
    quantity: float


@dataclass(frozen=True)
class PaperClose:
    exit_time: datetime
    exit_price: float
    result: str
    gross_pnl: float
    commission: float
    net_pnl: float


class PaperBroker:
    """Single-position deterministic paper broker for BUY-only research."""

    def __init__(self, risk_state: RiskState, risk_guard: BuyRiskGuard | None = None,
                 execution: ExecutionConfig | None = None, ledger: TradeLedger | None = None,
                 kill_switch: KillSwitch | None = None):
        self.risk_state = risk_state
        self.risk_guard = risk_guard or BuyRiskGuard()
        self.execution = LongExecutionModel(execution)
        self.ledger = ledger
        self.kill_switch = kill_switch
        self.position: PaperPosition | None = None
        self.audit: list[dict] = []

    def submit_buy(self, *, time: datetime, trigger: float, stop: float, target: float,
                   requested_risk_fraction: float, spread: float = 0.0) -> PaperPosition | None:
        if self.position is not None:
            return self._reject(time, "position_already_open")
        if self.ledger is not None and self.ledger.snapshot()["open_position"] is not None:
            return self._reject(time, "unreconciled_open_position")
        if self.kill_switch is not None and not self.kill_switch.allow_buy():
            return self._reject(time, "kill_switch_engaged")
        if target <= trigger:
            return self._reject(time, "invalid_long_target")
        entry = self.execution.entry_price(trigger)
        decision = self.risk_guard.check_buy(self.risk_state, entry=entry, stop=stop,
            requested_risk_fraction=requested_risk_fraction, spread=spread,
            expected_slippage=self.execution.config.entry_slippage)
        if not decision.allowed:
            return self._reject(time, decision.reason or "risk_rejected")
        self.position = PaperPosition(time, entry, stop, target, decision.quantity)
        self.risk_state.trades_today += 1
        record = {"time": time, "event": "BUY_FILLED", "entry": entry,
                  "stop": stop, "target": target, "quantity": decision.quantity}
        self.audit.append(record)
        if self.ledger:
            self.ledger.append("BUY_FILLED", time=time, entry=entry, stop=stop, target=target, quantity=decision.quantity)
        return self.position

    def _reject(self, time: datetime, reason: str) -> None:
        self.audit.append({"time": time, "event": "REJECT", "reason": reason})
        if self.ledger:
            self.ledger.append("REJECT", time=time, reason=reason)
        return None

    def process_tick(self, tick: Tick) -> PaperClose | None:
        if self.position is None:
            return None
        if tick.time <= self.position.entry_time:
            return None
        if tick.price <= self.position.stop:
            return self._close(tick.time, self.position.stop, "LOSS")
        if tick.price >= self.position.target:
            return self._close(tick.time, self.position.target, "WIN")
        return None

    def close_session(self, *, time: datetime, price: float) -> PaperClose | None:
        if self.position is None:
            return None
        return self._close(time, price, "SESSION_END")

    def _close(self, time: datetime, trigger_price: float, result: str) -> PaperClose:
        position = self.position
        if position is None:
            raise RuntimeError("no open position")
        exit_price = self.execution.exit_price(trigger_price)
        gross = (exit_price - position.entry) * position.quantity
        commission = self.execution.commission(position.quantity)
        net = gross - commission
        close = PaperClose(time, exit_price, result, gross, commission, net)
        self.risk_state.record_close(net)
        record = {"time": time, "event": "POSITION_CLOSED", "result": result,
                  "exit": exit_price, "net_pnl": net}
        self.audit.append(record)
        if self.ledger:
            self.ledger.append("POSITION_CLOSED", time=time, result=result, exit=exit_price, net_pnl=net)
        self.position = None
        return close
