"""Read-only FYERS v3 market-data adapter."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .env import load_local_env


class FyersMarketData:
    """Read-only FYERS access; never places or modifies orders."""

    def __init__(self, *, symbol: str = "NSE:RELIANCE-EQ", client: Any | None = None) -> None:
        self.symbol = symbol
        self.client = client or self._build_client()

    @staticmethod
    def _build_client() -> Any:
        load_local_env()
        app_id = os.environ.get("FYERS_APP_ID")
        token = os.environ.get("FYERS_ACCESS_TOKEN")
        if not app_id or not token:
            token_file = os.environ.get("FYERS_TOKEN_FILE", ".fyers_token")
            try:
                token = open(token_file, encoding="utf-8").read().strip()
            except FileNotFoundError:
                token = None
        if not app_id or not token:
            raise RuntimeError("FYERS_APP_ID and FYERS_ACCESS_TOKEN (or .fyers_token) are required")
        from fyers_apiv3 import fyersModel
        return fyersModel.FyersModel(client_id=app_id, token=token, is_async=False, log_path="")

    def profile(self) -> dict[str, Any]:
        return self._response(self.client.get_profile())

    def quote(self) -> dict[str, Any]:
        return self._response(self.client.quotes({"symbols": self.symbol}))

    def historical_m1(self, *, start: str, end: str) -> list[list[Any]]:
        response = self.client.history(
            data={
                "symbol": self.symbol,
                "resolution": "1",
                "date_format": "1",
                "range_from": start,
                "range_to": end,
                "cont_flag": "0",
            }
        )
        payload = self._response(response)
        candles = payload.get("candles", [])
        if not isinstance(candles, list):
            raise RuntimeError("FYERS historical response has invalid candles")
        return candles

    @staticmethod
    def _response(response: Any) -> dict[str, Any]:
        if not isinstance(response, dict):
            raise RuntimeError("FYERS API returned a non-object response")
        if response.get("s") not in (None, "ok"):
            raise RuntimeError(f"FYERS API error: {response.get('code')}: {response.get('message')}")
        return response

    @staticmethod
    def candle_timestamp(value: int | float) -> datetime:
        return datetime.fromtimestamp(value, tz=timezone.utc)
