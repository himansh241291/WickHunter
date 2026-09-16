"""Deterministic long-only WickHunter v0.1 state machine."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .models import Candle, Signal, SweepEvent
from .rules import is_bullish_signal, valid_long_geometry


class State(str, Enum):
    LEVELS_READY = "LEVELS_READY"
    WAIT_FOR_LOW_SWEEP = "WAIT_FOR_LOW_SWEEP"
    WAIT_FOR_BULLISH_SIGNAL = "WAIT_FOR_BULLISH_SIGNAL"
    LONG_READY = "LONG_READY"
    POSITION_OPEN = "POSITION_OPEN"
    DONE = "DONE"


@dataclass
class EngineConfig:
    minimum_reward_risk: float = 1.5
    stop_buffer: float = 0.0
    max_trades_per_day: int = 1
    sustained_below_pdl_closes: int = 2


class WickHunterEngine:
    """Pure strategy state machine; it never emits a short action."""

    def __init__(self, pdl: float, pdh: float, config: Optional[EngineConfig] = None):
        if pdh <= pdl:
            raise ValueError("PDH must be greater than PDL")
        self.pdl = pdl
        self.pdh = pdh
        self.config = config or EngineConfig()
        self.state = State.WAIT_FOR_LOW_SWEEP
        self.sweep: Optional[SweepEvent] = None
        self.signal: Optional[Signal] = None
        self.trades = 0
        self._below_pdl_closes = 0

    def on_candle(self, candle: Candle) -> Optional[dict]:
        """Process one completed M1 candle and return a BUY event or None."""
        if self.state in (State.DONE, State.POSITION_OPEN):
            return None

        if self.state == State.WAIT_FOR_LOW_SWEEP:
            if candle.low < self.pdl:
                self.sweep = SweepEvent(candle.time, self.pdl, candle.low)
                self._below_pdl_closes = 1 if candle.close < self.pdl else 0
                self.state = State.WAIT_FOR_BULLISH_SIGNAL
            return None

        if self.state == State.WAIT_FOR_BULLISH_SIGNAL:
            assert self.sweep is not None
            sweep_low = min(self.sweep.sweep_low, candle.low)
            self.sweep = SweepEvent(self.sweep.start_time, self.pdl, sweep_low)

            if candle.close < self.pdl:
                self._below_pdl_closes += 1
            else:
                self._below_pdl_closes = 0

            if is_bullish_signal(candle, self.pdl, previous_swept=True):
                self.signal = Signal(candle.time, candle.high, candle.low, sweep_low, self.pdl)
                self.state = State.LONG_READY
                return None

            if self._below_pdl_closes >= self.config.sustained_below_pdl_closes:
                self.state = State.DONE
            return None

        if self.state == State.LONG_READY:
            assert self.signal is not None
            # Confirmation is only the immediately following M1 candle.
            # Equality counts as a trigger because the execution rule is
            # "at/above SignalHigh".
            if candle.high < self.signal.signal_high:
                self.state = State.DONE
                return None

            entry = self.signal.signal_high
            stop = self.signal.sweep_low - self.config.stop_buffer
            target = self.pdh
            if self.trades >= self.config.max_trades_per_day:
                self.state = State.DONE
                return None
            if not valid_long_geometry(entry, stop, target, self.config.minimum_reward_risk):
                self.state = State.DONE
                return None

            self.trades += 1
            self.state = State.POSITION_OPEN
            return {
                "action": "BUY",
                "entry": entry,
                "stop": stop,
                "target": target,
                "signal_time": self.signal.time,
                "confirmation_time": candle.time,
            }

        return None
