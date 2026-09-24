from datetime import datetime
from zoneinfo import ZoneInfo
from wickhunter.candles import M1Candle
from wickhunter.engine import EngineConfig
from wickhunter.fyers_m1_strategy import FyersM1Strategy

IST = ZoneInfo("Asia/Kolkata")

def test_fyers_m1_strategy_emits_buy():
    strategy = FyersM1Strategy(initial_pdl=100, initial_pdh=110,
                               engine_config=EngineConfig(minimum_reward_risk=1.5))
    strategy.on_candle(M1Candle(datetime(2026, 9, 21, 9, 15, tzinfo=IST), 101, 102, 99, 99.5, 0))
    strategy.on_candle(M1Candle(datetime(2026, 9, 21, 9, 16, tzinfo=IST), 99.5, 101, 99, 100.5, 0))
    event = strategy.on_candle(M1Candle(datetime(2026, 9, 21, 9, 17, tzinfo=IST), 100.5, 103, 100, 102, 0))
    assert event is not None
    assert event["action"] == "BUY"
    assert event["entry"] == 101
    assert event["stop"] == 99
    assert event["target"] == 110

def test_next_session_uses_completed_previous_session_levels():
    strategy = FyersM1Strategy(initial_pdl=90, initial_pdh=120)
    strategy.on_candle(M1Candle(datetime(2026, 9, 21, 9, 15, tzinfo=IST), 100, 105, 95, 101, 0))
    strategy.on_candle(M1Candle(datetime(2026, 9, 21, 9, 16, tzinfo=IST), 101, 108, 94, 106, 0))
    strategy.on_candle(M1Candle(datetime(2026, 9, 22, 9, 15, tzinfo=IST), 105, 107, 100, 106, 0))
    assert strategy.engine is not None
    assert strategy.engine.pdl == 94
    assert strategy.engine.pdh == 108

def test_initial_levels_remain_until_first_session_completes():
    strategy = FyersM1Strategy(initial_pdl=90, initial_pdh=120)
    strategy.on_candle(M1Candle(datetime(2026, 9, 21, 9, 15, tzinfo=IST), 100, 105, 95, 101, 0))
    assert strategy.engine is not None
    assert strategy.engine.pdl == 90
    assert strategy.engine.pdh == 120
