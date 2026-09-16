from datetime import datetime, timedelta, timezone

from wickhunter.backtest import BacktestConfig, DailyLevels, WickHunterBacktester
from wickhunter.models import Candle


def winning_setup(day, pdh=106.0, pdl=100.0, spread=0.0):
    start = datetime(2026, 1, day, 9, 0, tzinfo=timezone.utc)
    data = [
        Candle(start, 100.5, 100.8, 99.0, 99.5, spread),
        Candle(start + timedelta(minutes=1), 99.5, 101.5, 99.2, 101.2, spread),
        Candle(start + timedelta(minutes=2), 101.2, 105.0, 101.0, 104.0, spread),
        Candle(start + timedelta(minutes=3), 104.0, pdh, 103.8, pdh - 0.5, spread),
    ]
    return data, DailyLevels(f"2026-01-{day:02d}", pdh=pdh, pdl=pdl)


def losing_setup(day, pdh=106.0, pdl=100.0):
    start = datetime(2026, 1, day, 9, 0, tzinfo=timezone.utc)
    return [
        Candle(start, 100.5, 100.8, 99.0, 99.5),
        Candle(start + timedelta(minutes=1), 99.5, 101.5, 99.2, 101.2),
        Candle(start + timedelta(minutes=2), 101.2, 101.6, 100.8, 101.4),
        Candle(start + timedelta(minutes=3), 101.4, 101.5, 98.0, 100.0),
    ], DailyLevels(f"2026-01-{day:02d}", pdh=pdh, pdl=pdl)


def test_max_spread_rejects_buy():
    data, level = winning_setup(2, spread=2.0)
    result = WickHunterBacktester(BacktestConfig(max_spread=1.0)).run(
        {"2026-01-02": data}, {"2026-01-02": level}
    )
    assert result.total_trades == 0
    assert result.rejected[-1]["reason"] == "max_spread"


def test_max_slippage_rejects_buy():
    data, level = winning_setup(2)
    result = WickHunterBacktester(BacktestConfig(entry_slippage=0.2, max_slippage=0.1)).run(
        {"2026-01-02": data}, {"2026-01-02": level}
    )
    assert result.total_trades == 0
    assert result.rejected[-1]["reason"] == "max_slippage"


def test_max_daily_loss_blocks_later_setup_same_session():
    start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    data = [
        Candle(start, 100.5, 100.8, 99.0, 99.5),
        Candle(start + timedelta(minutes=1), 99.5, 101.5, 99.2, 101.2),
        Candle(start + timedelta(minutes=2), 101.2, 101.6, 100.8, 101.4),
        Candle(start + timedelta(minutes=3), 101.4, 101.5, 98.0, 100.0),
        Candle(start + timedelta(minutes=4), 100.0, 101.5, 99.2, 101.2),
        Candle(start + timedelta(minutes=5), 101.2, 105.0, 101.0, 104.0),
        Candle(start + timedelta(minutes=6), 104.0, 106.0, 103.8, 105.5),
    ]
    result = WickHunterBacktester(BacktestConfig(max_trades_per_day=2, max_daily_loss_fraction=0.001)).run(
        {"2026-01-02": data}, {"2026-01-02": DailyLevels("2026-01-02", 106, 100)}
    )
    assert result.total_trades == 1
    assert any(item["reason"] == "max_daily_loss" for item in result.rejected)


def test_consecutive_loss_guard_carries_across_sessions():
    day1, level1 = losing_setup(2)
    day2, level2 = losing_setup(3)
    result = WickHunterBacktester(BacktestConfig(max_consecutive_losses=1)).run(
        {"2026-01-02": day1, "2026-01-03": day2},
        {"2026-01-02": level1, "2026-01-03": level2},
    )
    assert result.total_trades == 1
    assert any(item["session"] == "2026-01-03" and item["reason"] == "max_consecutive_losses" for item in result.rejected)
