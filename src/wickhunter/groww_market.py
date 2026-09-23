"""Read-only Groww market-data adapter."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .env import load_local_env


class GrowwMarketData:
    """Read-only market data access; never places or modifies orders."""

    def __init__(
        self,
        *,
        trading_symbol: str,
        exchange: str = "NSE",
        segment: str = "CASH",
        api: Any | None = None,
    ) -> None:
        self.trading_symbol = trading_symbol
        self.exchange = exchange
        self.segment = segment
        self.api = api or self._build_api()

    @staticmethod
    def _build_api() -> Any:
        load_local_env()
        api_key = __import__("os").environ.get("GROWW_API_KEY")
        secret = __import__("os").environ.get("GROWW_API_SECRET")
        if not api_key or not secret:
            raise RuntimeError("GROWW_API_KEY and GROWW_API_SECRET are required")
        from growwapi import GrowwAPI
        return GrowwAPI(GrowwAPI.get_access_token(api_key=api_key, secret=secret))

    def instrument(self) -> dict[str, Any]:
        response = self.api.get_instrument_by_exchange_and_trading_symbol(
            exchange=self.exchange,
            trading_symbol=self.trading_symbol,
        )
        payload = response.get("payload", response) if isinstance(response, dict) else response
        return payload if isinstance(payload, dict) else {}

    def ltp(self) -> float:
        response = self.api.get_ltp(
            segment=self.segment,
            exchange_trading_symbols=(f"{self.exchange}_{self.trading_symbol}",),
        )
        payload = response.get("payload", response) if isinstance(response, dict) else response
        key = f"{self.exchange}_{self.trading_symbol}"
        value = payload.get(key) if isinstance(payload, dict) else None
        if value is None:
            raise RuntimeError(f"Groww LTP response has no {key}")
        return float(value)

    def quote(self) -> dict[str, Any]:
        response = self.api.get_quote(
            exchange=self.exchange,
            segment=self.segment,
            trading_symbol=self.trading_symbol,
        )
        payload = response.get("payload", response) if isinstance(response, dict) else response
        return payload if isinstance(payload, dict) else {}

    def historical_m1(
        self,
        *,
        start_time: str,
        end_time: str,
    ) -> list[list[Any]]:
        instrument = self.instrument()
        groww_symbol = str(instrument.get("groww_symbol") or f"{self.exchange}-{self.trading_symbol}")
        response = self.api.get_historical_candles(
            exchange=self.exchange,
            segment=self.segment,
            groww_symbol=groww_symbol,
            start_time=start_time,
            end_time=end_time,
            candle_interval=self.api.CANDLE_INTERVAL_MIN_1,
        )
        payload = response.get("payload", response) if isinstance(response, dict) else response
        if not isinstance(payload, dict):
            raise RuntimeError("Groww historical candle response is not an object")
        candles = payload.get("candles", [])
        if not isinstance(candles, list):
            raise RuntimeError("Groww historical candle response has invalid candles")
        return candles

    @staticmethod
    def candle_timestamp(value: str) -> datetime:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            result = result.replace(tzinfo=timezone.utc)
        return result
