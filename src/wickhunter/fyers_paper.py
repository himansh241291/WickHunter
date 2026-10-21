"""FYERS M1-to-paper execution pipeline; this module never places live orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .candles import M1Candle, MarketTick
from .engine import EngineConfig, State, WickHunterEngine
from .fyers_m1 import FyersM1Stream
from .heartbeat import FeedHealth
from .ledger import TradeLedger
from .live import buy_client_order_id
from .models import Candle
from .paper import PaperBroker, PaperClose, PaperPosition
from .rules import valid_long_geometry
from .safety import KillSwitch
from .tick import Tick


@dataclass(frozen=True)
class ArmedPaperBuy:
    signal_time: datetime
    order_time: datetime
    expires_at: datetime
    trigger: float
    stop: float
    target: float
    client_order_id: str


class FyersPaperPipeline:
    """Route FYERS ticks/candles through WickHunter and a durable paper broker.

    Startup recovery is explicit: call ``recover()`` before ``connect()`` when
    resuming an existing ledger. Initial PDH/PDL must be supplied from a
    completed prior session; subsequent sessions use the prior observed
    session's completed M1 high/low.
    """

    def __init__(
        self,
        *,
        symbol: str,
        initial_pdl: float,
        initial_pdh: float,
        broker: PaperBroker,
        ledger: TradeLedger,
        risk_fraction: float = 0.01,
        timezone_name: str = "Asia/Kolkata",
        engine_config: EngineConfig | None = None,
        feed_health: FeedHealth | None = None,
        kill_switch: KillSwitch | None = None,
        stream_factory: Any | None = None,
    ) -> None:
        if not 0 < risk_fraction <= 1:
            raise ValueError("risk_fraction must be in (0, 1]")
        self.symbol = symbol
        self.zone = ZoneInfo(timezone_name)
        self.broker = broker
        self.ledger = ledger
        self.risk_fraction = risk_fraction
        self.engine_config = engine_config or EngineConfig()
        self.feed_health = feed_health or FeedHealth(timedelta(seconds=5))
        self.kill_switch = kill_switch or broker.kill_switch or KillSwitch(ledger)
        self.broker.ledger = ledger
        self.broker.kill_switch = self.kill_switch
        self.engine = WickHunterEngine(initial_pdl, initial_pdh, self.engine_config)
        self.pdh = float(initial_pdh)
        self.pdl = float(initial_pdl)
        self.session_date = None
        self.session_high: float | None = None
        self.session_low: float | None = None
        self.armed: ArmedPaperBuy | None = None
        self.last_tick_time: datetime | None = None
        self.last_tick_price: float | None = None
        self.stream = FyersM1Stream(
            symbol=symbol, on_candle=self.on_candle, on_tick=self.on_tick,
            stream_factory=stream_factory,
        )

    def connect(self) -> None:
        """Connect read-only FYERS market data after caller performs recovery."""
        self.stream.connect()

    def close(self) -> None:
        self.stream.close()

    def recover(self) -> None:
        """Restore the persisted position or pending BUY; fail on conflicts."""
        snapshot = self.ledger.snapshot()
        if snapshot["open_position"] is not None:
            if self.broker.position is not None:
                raise RuntimeError("paper broker already has a position during recovery")
            self.broker.restore_open_position(snapshot["open_position"])
            self.engine.state = State.POSITION_OPEN
        pending = snapshot["pending_buy"]
        if pending is not None:
            required = {"trigger", "stop", "target", "client_order_id", "expires_at", "signal_time"}
            if not required.issubset(pending):
                raise ValueError("incomplete persisted paper BUY intent")
            if self.broker.position is not None:
                raise RuntimeError("ledger contains both an open position and pending BUY")
            self.armed = ArmedPaperBuy(
                signal_time=datetime.fromisoformat(pending["signal_time"]),
                order_time=datetime.fromisoformat(pending["time"]),
                expires_at=datetime.fromisoformat(pending["expires_at"]),
                trigger=float(pending["trigger"]), stop=float(pending["stop"]),
                target=float(pending["target"]), client_order_id=str(pending["client_order_id"]),
            )
            self.engine.state = State.LONG_READY

    def heartbeat(self, now: datetime) -> bool:
        """Check silence even when no ticks arrive; halt new BUYs on stale feed."""
        healthy = self.feed_health.allow_buy(now)
        if not healthy and not self.kill_switch.is_halted():
            self.kill_switch.engage(time=now, reason=self.feed_health.reason or "stale_market_data")
        return healthy and not self.kill_switch.is_halted()

    def on_candle(self, candle: M1Candle) -> None:
        local = candle.time.astimezone(self.zone)
        print(
            f"M1 CLOSED {local.isoformat()} | O={candle.open:.2f} H={candle.high:.2f} "
            f"L={candle.low:.2f} C={candle.close:.2f} V={candle.volume} "
            f"| PDL={self.pdl:.2f} PDH={self.pdh:.2f}",
            flush=True,
        )
        if self.session_date != local.date():
            self._start_session(local.date(), candle.time)
        self.session_high = candle.high if self.session_high is None else max(self.session_high, candle.high)
        self.session_low = candle.low if self.session_low is None else min(self.session_low, candle.low)

        # A completed confirmation minute without a tick-triggered fill expires
        # the setup. Do not let OHLC retrospectively create an entry.
        if self.kill_switch.is_halted():
            pass
        elif self.armed is not None and candle.time >= self.armed.order_time:
            self._cancel_armed(candle.time, "confirmation_minute_completed_without_trigger")
        elif self.broker.position is None and self.armed is None and self.engine.state not in (State.DONE, State.POSITION_OPEN):
            self.engine.on_candle(Candle(candle.time, candle.open, candle.high, candle.low, candle.close))
            if self.engine.state == State.LONG_READY and self.engine.signal is not None:
                self._arm(candle.time)

        # NSE session closes at 15:30 IST. Use the final completed candle's
        # close as the paper liquidation reference, not a future tick.
        if local.time() == time(15, 29):
            if self.armed is not None:
                self._cancel_armed(candle.time + timedelta(minutes=1), "session_end")
            if self.broker.position is not None:
                self.broker.close_session(time=candle.time + timedelta(minutes=1), price=candle.close)
                self.engine.state = State.DONE

    def on_tick(self, tick: MarketTick) -> PaperPosition | PaperClose | None:
        if self.last_tick_time is None or tick.time > self.last_tick_time:
            self.last_tick_time = tick.time
            self.last_tick_price = tick.price
            self.feed_health.observe(tick.time)
        # Equal-timestamp price updates are useful for execution, but older
        # ticks are ignored to preserve deterministic event ordering.
        elif tick.time < self.last_tick_time:
            return None

        if self.broker.position is not None:
            closed = self.broker.process_tick(Tick(tick.time, tick.price))
            if closed is not None:
                self.engine.state = State.DONE
                self.armed = None
            return closed

        if self.armed is None or self.kill_switch.is_halted():
            return None
        if not self.feed_health.allow_buy(tick.time):
            if not self.kill_switch.is_halted():
                self.kill_switch.engage(time=tick.time, reason=self.feed_health.reason or "stale_market_data")
            return None
        # The rollover tick arrives after the completed signal candle callback,
        # so a trigger exactly at the confirmation minute boundary is valid.
        if tick.time < self.armed.order_time:
            return None
        if tick.time >= self.armed.expires_at:
            self._cancel_armed(tick.time, "BUY_intent_expired")
            return None
        if tick.price < self.armed.trigger:
            return None
        if tick.price >= self.armed.target:
            self._cancel_armed(tick.time, "target_not_above_observed_entry")
            return None

        armed = self.armed
        position = self.broker.submit_buy(
            time=tick.time, trigger=tick.price, stop=armed.stop, target=armed.target,
            requested_risk_fraction=self.risk_fraction,
        )
        if position is None:
            self.ledger.append("BUY_CANCELLED", time=tick.time,
                               client_order_id=armed.client_order_id,
                               reason=self.broker.audit[-1].get("reason", "paper_broker_rejected"))
            self.armed = None
            self.engine.state = State.DONE
            return None
        # PaperBroker has persisted BUY_FILLED. Attach the same stable client ID
        # as a separate audit event, avoiding a duplicate lifecycle fill event.
        self.ledger.append("PAPER_BUY_ACK", time=tick.time,
                           client_order_id=armed.client_order_id, entry=position.entry,
                           stop=position.stop, target=position.target, quantity=position.quantity)
        self.armed = None
        self.engine.trades += 1
        self.engine.state = State.POSITION_OPEN
        return position

    def _arm(self, candle_time: datetime) -> None:
        signal = self.engine.signal
        assert signal is not None
        trigger = signal.signal_high
        stop = signal.sweep_low - self.engine.config.stop_buffer
        target = self.engine.pdh
        if not valid_long_geometry(trigger, stop, target, self.engine.config.minimum_reward_risk):
            self.engine.state = State.DONE
            return
        order_time = candle_time + timedelta(minutes=1)
        expires_at = order_time + timedelta(minutes=1)
        client_id = buy_client_order_id(signal_time=signal.time, trigger=trigger, stop=stop, target=target)
        self.armed = ArmedPaperBuy(signal.time, order_time, expires_at, trigger, stop, target, client_id)
        self.ledger.append("BUY_INTENT", time=order_time, trigger=trigger, stop=stop, target=target,
                           quantity=0.0, client_order_id=client_id, expires_at=expires_at.isoformat(),
                           signal_time=signal.time.isoformat(), risk_fraction=self.risk_fraction)

    def _cancel_armed(self, when: datetime, reason: str) -> None:
        if self.armed is None:
            return
        self.ledger.append("BUY_CANCELLED", time=when, client_order_id=self.armed.client_order_id, reason=reason)
        self.armed = None
        self.engine.state = State.DONE

    def _start_session(self, session_date, when: datetime) -> None:
        if self.session_date is not None:
            if self.session_high is None or self.session_low is None:
                raise RuntimeError("cannot roll an empty session")
            self.pdh = self.session_high
            self.pdl = self.session_low
            if self.armed is not None:
                self._cancel_armed(when, "session_boundary")
            if self.broker.position is not None:
                if self.last_tick_price is None:
                    self.kill_switch.engage(time=when, reason="session_rollover_without_market_price")
                    raise RuntimeError("cannot safely paper-liquidate open position without a market price")
                self.broker.close_session(time=when, price=self.last_tick_price)
            self.broker.risk_state.reset_day()
        self.session_date = session_date
        self.session_high = None
        self.session_low = None
        self.engine = WickHunterEngine(self.pdl, self.pdh, self.engine_config)
        if self.broker.position is not None:
            self.engine.state = State.POSITION_OPEN
