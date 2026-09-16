from datetime import datetime, timedelta, timezone

from wickhunter.backtest import BacktestConfig, DailyLevels, WickHunterBacktester
from wickhunter.models import Candle


def bars(*ohlc):
    start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    return [Candle(start + timedelta(minutes=i), *values) for i, values in enumerate(ohlc)]


def levels(pdh=106.0, pdl=100.0):
    return {"2026-01-02": DailyLevels("2026-01-02", pdh=pdh, pdl=pdl)}


def test_buy_setup_reaches_target_on_following_candle():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 101.5, 99.2, 101.2), (101.2, 105.0, 101.0, 104.0), (104.0, 106.0, 103.8, 105.5))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels())
    assert result.total_trades == 1
    assert result.trades[0].result == "WIN"
    assert result.trades[0].entry == 101.5


def test_no_entry_when_signal_high_not_broken():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 101.5, 99.2, 101.2), (101.2, 101.4, 100.9, 101.1))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels(pdh=105.0))
    assert result.total_trades == 0


def test_missing_levels_skip_session():
    result = WickHunterBacktester().run({"2026-01-02": bars((100.5, 101.0, 99.0, 100.0))}, {})
    assert result.total_trades == 0
    assert result.rejected[0]["reason"] == "MISSING_PREVIOUS_DAY_LEVELS"


def test_long_trade_has_positive_risk_and_target():
    data = bars((100.2, 100.5, 98.5, 99.0), (99.0, 102.0, 98.8, 101.8), (101.8, 107.5, 101.5, 107.0), (107.0, 108.0, 106.5, 107.5))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels(pdh=108.0))
    trade = result.trades[0]
    assert trade.entry > trade.stop
    assert trade.target > trade.entry
    assert trade.quantity > 0


def test_two_consecutive_closes_below_pdl_invalidate_sweep():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 99.9, 98.5, 99.0), (99.0, 99.5, 98.2, 98.7), (98.7, 102.0, 98.0, 101.8), (101.8, 103.0, 101.5, 102.5))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels(pdh=105.0))
    assert result.total_trades == 0


def test_slippage_can_prevent_confirmation_fill():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 101.5, 99.2, 101.2), (101.2, 101.5, 101.0, 101.3))
    result = WickHunterBacktester(BacktestConfig(slippage=0.1)).run({"2026-01-02": data}, levels(pdh=105.0))
    assert result.total_trades == 0
    assert result.rejected[-1]["reason"] == "ENTRY_NOT_FILLED_SLIPPAGE"


def test_confirmation_candle_is_not_used_for_exit():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 101.5, 99.2, 101.2), (101.2, 106.0, 98.0, 105.0), (105.0, 105.5, 98.5, 104.0))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels())
    assert result.total_trades == 1
    assert result.trades[0].result == "LOSS"
    assert result.trades[0].exit_time == data[3].time


def test_open_trade_is_liquidated_at_session_end():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 101.5, 99.2, 101.2), (101.2, 103.0, 101.0, 102.0))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels(pdh=106.0))
    assert result.total_trades == 1
    trade = result.trades[0]
    assert trade.result == "SESSION_CLOSE"
    assert trade.exit_time == data[-1].time
    assert trade.exit_price == data[-1].close
    assert result.rejected == []


def test_audit_records_buy_and_exit():
    data = bars((100.5, 100.8, 99.0, 99.5), (99.5, 101.5, 99.2, 101.2), (101.2, 106.0, 101.0, 105.0), (105.0, 106.0, 104.0, 105.5))
    result = WickHunterBacktester().run({"2026-01-02": data}, levels())
    assert [event["event"] for event in result.audit] == ["BUY", "EXIT"]
    assert result.audit[1]["result"] == "WIN"
