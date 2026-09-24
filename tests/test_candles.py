from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from wickhunter.candles import M1CandleBuilder, MarketTick, fyers_tick


def local_tick(h, m, s, price, volume):
    return MarketTick(
        datetime(2026, 9, 24, h, m, s, tzinfo=ZoneInfo("Asia/Kolkata")),
        price,
        volume,
    )


def test_builds_completed_ohlcv_from_ticks():
    builder = M1CandleBuilder()
    assert builder.add(local_tick(9, 15, 1, 100, 1000)) == []
    assert builder.add(local_tick(9, 15, 20, 101, 1005)) == []
    completed = builder.add(local_tick(9, 16, 0, 99, 1012))
    assert len(completed) == 1
    candle = completed[0]
    assert candle.time.hour == 9 and candle.time.minute == 15
    assert (candle.open, candle.high, candle.low, candle.close) == (100, 101, 100, 101)
    assert candle.volume == 12


def test_out_of_order_tick_is_ignored():
    builder = M1CandleBuilder()
    builder.add(local_tick(9, 15, 10, 100, 1000))
    builder.add(local_tick(9, 15, 20, 102, 1005))
    assert builder.add(local_tick(9, 15, 15, 90, 1008)) == []
    candle = builder.flush()
    assert candle is not None
    assert candle.low == 100
    assert candle.close == 102


def test_premarket_and_postmarket_ticks_do_not_create_new_candles():
    builder = M1CandleBuilder()
    assert builder.add(local_tick(9, 14, 59, 100, 1000)) == []
    assert builder.flush() is None
    builder.add(local_tick(9, 15, 1, 100, 1000))
    completed = builder.add(local_tick(15, 30, 0, 101, 1010))
    assert len(completed) == 1
    assert builder.flush() is None


def test_flush_emits_current_candle():
    builder = M1CandleBuilder()
    builder.add(local_tick(9, 15, 1, 100, 1000))
    candle = builder.flush()
    assert candle is not None
    assert candle.close == 100
    assert builder.flush() is None


def test_cumulative_volume_reset_is_handled():
    builder = M1CandleBuilder()
    builder.add(local_tick(9, 15, 1, 100, 500))
    builder.add(local_tick(9, 15, 10, 101, 510))
    builder.add(local_tick(9, 15, 20, 102, 3))
    candle = builder.flush()
    assert candle is not None
    assert candle.volume == 13


def test_fyers_tick_prefers_exchange_feed_time():
    tick = fyers_tick({
        "exch_feed_time": 1790224957,
        "last_traded_time": 1790224900,
        "ltp": 1237.8,
        "vol_traded_today": 2414486,
    })
    assert tick.price == 1237.8
    assert tick.cumulative_volume == 2414486
    assert tick.time.tzinfo is not None
    assert tick.time.hour == 10
    assert tick.time.minute == 12


def test_fyers_tick_requires_timestamp_and_price():
    with pytest.raises(ValueError):
        fyers_tick({"ltp": 100})
    with pytest.raises(ValueError):
        fyers_tick({"exch_feed_time": 1})


def test_invalid_session_window_rejected():
    with pytest.raises(ValueError):
        M1CandleBuilder(session_start=time(15, 30), session_end=time(9, 15))
