"""Compose FYERS SymbolUpdate ticks into WickHunter M1 candles."""

from __future__ import annotations

from typing import Any, Callable

from .candles import M1Candle, M1CandleBuilder, fyers_tick
from .fyers_stream import FyersDataStream


class FyersM1Stream:
    """Read-only FYERS stream that emits completed M1 candles."""

    def __init__(
        self,
        *,
        symbol: str,
        on_candle: Callable[[M1Candle], None],
        builder: M1CandleBuilder | None = None,
        stream_factory: Any | None = None,
    ) -> None:
        self.symbol = symbol
        self.on_candle = on_candle
        self.builder = builder or M1CandleBuilder()
        self.stream_factory = stream_factory or FyersDataStream
        self.stream: Any | None = None

    def connect(self) -> None:
        self.stream = self.stream_factory(symbol=self.symbol, on_tick=self._on_tick)
        self.stream.connect()

    def close(self) -> None:
        if self.stream is not None and hasattr(self.stream, "close"):
            self.stream.close()

    def flush(self) -> M1Candle | None:
        """Explicitly emit the current partial minute when the caller requires it."""
        candle = self.builder.flush()
        if candle is not None:
            self.on_candle(candle)
        return candle

    def _on_tick(self, message: dict[str, Any]) -> None:
        if message.get("type") != "sf":
            return
        tick = fyers_tick(message)
        for candle in self.builder.add(tick):
            self.on_candle(candle)
