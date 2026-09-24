from datetime import datetime
from zoneinfo import ZoneInfo

from wickhunter.fyers_m1 import FyersM1Stream
from wickhunter.fyers_stream import FyersDataStream


class FakeM1Stream:
    def __init__(self, *, symbol, on_tick):
        self.symbol = symbol
        self.on_tick = on_tick
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def close(self):
        self.closed = True


def fyers_message(h, m, s, price, volume):
    local = datetime(2026, 9, 24, h, m, s, tzinfo=ZoneInfo("Asia/Kolkata"))
    return {
        "type": "sf",
        "symbol": "NSE:RELIANCE-EQ",
        "ltp": price,
        "exch_feed_time": local.timestamp(),
        "vol_traded_today": volume,
    }


def test_fyers_m1_stream_emits_completed_candle():
    candles = []
    stream = FyersM1Stream(
        symbol="NSE:RELIANCE-EQ",
        on_candle=candles.append,
        stream_factory=FakeM1Stream,
    )
    stream.connect()
    assert stream.stream.connected

    stream.stream.on_tick({"type": "cn", "code": 200})
    stream.stream.on_tick(fyers_message(9, 15, 1, 100, 1000))
    stream.stream.on_tick(fyers_message(9, 15, 30, 101, 1005))
    assert candles == []

    stream.stream.on_tick(fyers_message(9, 16, 0, 99, 1012))
    assert len(candles) == 1
    assert candles[0].open == 100
    assert candles[0].high == 101
    assert candles[0].low == 100
    assert candles[0].close == 101
    assert candles[0].volume == 5


def test_fyers_m1_stream_flushes_explicitly():
    candles = []
    stream = FyersM1Stream(
        symbol="NSE:RELIANCE-EQ",
        on_candle=candles.append,
        stream_factory=FakeM1Stream,
    )
    stream.connect()
    stream.stream.on_tick(fyers_message(9, 15, 1, 100, 1000))
    candle = stream.flush()
    assert candle is not None
    assert candles == [candle]


def test_fyers_m1_stream_closes_underlying_stream():
    stream = FyersM1Stream(
        symbol="NSE:RELIANCE-EQ",
        on_candle=lambda _: None,
        stream_factory=FakeM1Stream,
    )
    stream.connect()
    stream.close()
    assert stream.stream.closed


def test_fyers_stream_close_calls_socket():
    class FakeSocket:
        def __init__(self):
            self.closed = False

        def close_connection(self):
            self.closed = True

    stream = FyersDataStream(
        symbol="NSE:RELIANCE-EQ",
        on_tick=lambda _: None,
    )
    stream.socket = FakeSocket()
    stream.close()
    assert stream.socket.closed
