#!/usr/bin/env python3
"""Short read-only FYERS WebSocket smoke test."""
from __future__ import annotations

import os
import threading

from wickhunter.env import load_local_env
from wickhunter.fyers_stream import FyersDataStream


done = threading.Event()
ticks: list[dict] = []


def on_tick(message):
    # Ignore FYERS connection/subscription control messages.
    if message.get("type") != "sf":
        return
    ticks.append(message)
    print(message, flush=True)
    if len(ticks) >= 5:
        done.set()


load_local_env()
stream = FyersDataStream(
    symbol=os.environ.get("FYERS_SYMBOL", "NSE:RELIANCE-EQ"),
    on_tick=on_tick,
)
stream.connect()

try:
    if not done.wait(timeout=30):
        raise SystemExit("Timed out waiting for 5 FYERS market-data ticks")
finally:
    socket = stream.socket
    if socket is not None and hasattr(socket, "close_connection"):
        socket.close_connection()

print(f"Received {len(ticks)} market-data ticks; smoke test complete.")
