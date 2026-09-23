#!/usr/bin/env python3
"""Short read-only FYERS WebSocket smoke test."""
from __future__ import annotations

import os

from wickhunter.env import load_local_env
from wickhunter.fyers_stream import FyersDataStream


count = 0

def on_tick(message):
    global count
    count += 1
    print(message)
    if count >= 5:
        raise SystemExit(0)

load_local_env()
stream = FyersDataStream(symbol=os.environ.get("FYERS_SYMBOL", "NSE:RELIANCE-EQ"), on_tick=on_tick)
stream.connect()
