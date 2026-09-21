"""Broker-neutral BUY-only live runtime startup orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .heartbeat import FeedHealth
from .ledger import TradeLedger
from .live import BuyCoordinator
from .position import LongPositionMonitor
from .ports import BuyExecutionPort
from .risk import RiskLimits, RiskState
from .safety import KillSwitch, recover_risk_state


@dataclass(frozen=True)
class RuntimeStart:
    coordinator: BuyCoordinator
    position_monitor: LongPositionMonitor | None
    risk_state: RiskState
    pending_buy_recovered: bool
    pending_close_recovered: bool


class LiveRuntime:
    """Run the deterministic startup sequence before accepting BUY activity."""

    def __init__(
        self,
        *,
        pdl: float,
        pdh: float,
        execution: BuyExecutionPort,
        ledger: TradeLedger,
        starting_equity: float,
        risk_fraction: float = 0.01,
        risk_limits: RiskLimits | None = None,
        kill_switch: KillSwitch | None = None,
        feed_health: FeedHealth | None = None,
        timezone_name: str = "UTC",
    ) -> None:
        self.ledger = ledger
        self.execution = execution
        self.kill_switch = kill_switch or KillSwitch(ledger)
        self.feed_health = feed_health
        self.timezone_name = timezone_name
        self.risk_state = recover_risk_state(
            ledger,
            starting_equity=starting_equity,
            timezone_name=timezone_name,
        )
        self.coordinator = BuyCoordinator(
            pdl=pdl,
            pdh=pdh,
            execution=execution,
            risk_state=self.risk_state,
            risk_fraction=risk_fraction,
            risk_limits=risk_limits,
            ledger=ledger,
            kill_switch=self.kill_switch,
            feed_health=feed_health,
        )
        self.position_monitor: LongPositionMonitor | None = None

    def start(self) -> RuntimeStart:
        """Reconcile broker state, then recover durable in-flight lifecycle work."""
        reconciliation = self.coordinator.reconcile_startup()
        if not reconciliation.safe_to_buy:
            return RuntimeStart(
                self.coordinator, None, self.risk_state, False, False
            )

        pending_buy = self.coordinator.recover_pending_buy()
        pending_buy_recovered = pending_buy is not None

        snapshot = self.ledger.snapshot()
        if snapshot["open_position"] is None:
            return RuntimeStart(
                self.coordinator, None, self.risk_state,
                pending_buy_recovered, False,
            )

        self.position_monitor = LongPositionMonitor(
            execution=self.execution,
            ledger=self.ledger,
        )
        position_reconciliation = self.position_monitor.reconcile()
        if not position_reconciliation.safe_to_buy:
            self.coordinator.halted = True
            return RuntimeStart(
                self.coordinator, self.position_monitor, self.risk_state,
                pending_buy_recovered, False,
            )

        recovered_close = self.position_monitor.recover_pending_close()
        return RuntimeStart(
            self.coordinator,
            self.position_monitor,
            self.risk_state,
            pending_buy_recovered,
            recovered_close is not None,
        )

    def heartbeat(self, now: datetime) -> bool:
        """Check market-data health; existing positions remain broker-protected."""
        return self.coordinator.on_heartbeat(now)
