"""Feed completed FYERS M1 candles into the BUY-only WickHunter engine."""
from __future__ import annotations
from datetime import date
from typing import Callable
from zoneinfo import ZoneInfo
from .candles import M1Candle
from .engine import EngineConfig, WickHunterEngine
from .models import Candle

class FyersM1Strategy:
    """Run one WickHunter engine per trading session without lookahead."""
    def __init__(self, *, initial_pdl: float, initial_pdh: float,
                 timezone_name: str = "Asia/Kolkata",
                 engine_config: EngineConfig | None = None,
                 on_event: Callable[[dict], None] | None = None) -> None:
        self.zone = ZoneInfo(timezone_name)
        self.next_pdl = float(initial_pdl)
        self.next_pdh = float(initial_pdh)
        self.engine_config = engine_config
        self.on_event = on_event
        self.session: date | None = None
        self.session_high: float | None = None
        self.session_low: float | None = None
        self.engine: WickHunterEngine | None = None

    def on_candle(self, candle: M1Candle) -> dict | None:
        local_date = candle.time.astimezone(self.zone).date()
        if self.session != local_date:
            self._start_session(local_date)
        self.session_high = candle.high if self.session_high is None else max(self.session_high, candle.high)
        self.session_low = candle.low if self.session_low is None else min(self.session_low, candle.low)
        assert self.engine is not None
        event = self.engine.on_candle(Candle(
            time=candle.time, open=candle.open, high=candle.high,
            low=candle.low, close=candle.close,
        ))
        if event is not None and self.on_event is not None:
            self.on_event(event)
        return event

    def _start_session(self, session: date) -> None:
        if self.session is not None:
            if self.session_high is None or self.session_low is None:
                raise RuntimeError("cannot roll an empty session")
            self.next_pdh = self.session_high
            self.next_pdl = self.session_low
        self.session = session
        self.session_high = None
        self.session_low = None
        self.engine = WickHunterEngine(self.next_pdl, self.next_pdh, self.engine_config)
