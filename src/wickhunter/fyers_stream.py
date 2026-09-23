"""FYERS read-only live market-data stream adapter."""
from __future__ import annotations

import os
from typing import Any, Callable

from .env import load_local_env


class FyersDataStream:
    """Stream FYERS SymbolUpdate messages without placing orders."""

    def __init__(self, *, symbol: str, on_tick: Callable[[dict[str, Any]], None], socket_factory: Any | None = None) -> None:
        self.symbol = symbol
        self.on_tick = on_tick
        self.socket_factory = socket_factory
        self.socket: Any | None = None
        self.last_error: Any | None = None
        self.closed: Any | None = None

    def connect(self) -> None:
        load_local_env()
        app_id = os.environ.get("FYERS_APP_ID")
        token = os.environ.get("FYERS_ACCESS_TOKEN")
        if not token:
            token_file = os.environ.get("FYERS_TOKEN_FILE", ".fyers_token")
            try:
                with open(token_file, encoding="utf-8") as handle:
                    token = handle.read().strip()
            except FileNotFoundError:
                token = None
        if not app_id or not token:
            raise RuntimeError("FYERS_APP_ID and FYERS_ACCESS_TOKEN (or .fyers_token) are required")

        factory = self.socket_factory
        if factory is None:
            from fyers_apiv3.FyersWebsocket import data_ws
            factory = data_ws.FyersDataSocket

        def on_message(message: Any) -> None:
            if isinstance(message, dict):
                self.on_tick(message)

        def on_error(message: Any) -> None:
            self.last_error = message

        def on_close(message: Any) -> None:
            self.closed = message

        def on_connect() -> None:
            self.socket.subscribe(symbols=[self.symbol], data_type="SymbolUpdate")
            self.socket.keep_running()

        self.socket = factory(
            access_token=f"{app_id}:{token}",
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=on_connect,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message,
        )
        self.socket.connect()
