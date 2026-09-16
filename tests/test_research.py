from datetime import datetime, timedelta, timezone

import pytest

from wickhunter.backtest import BacktestConfig, DailyLevels
from wickhunter.models import Candle
from wickhunter.research import ResearchCase, run_cases, sensitivity_cases


def bars(*ohlc):
    start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    return [Candle(start + timedelta(minutes=i), *values) for i, values in enumerate(ohlc)]


def test_sensitivity_cases_are_deterministic_and_buy_only():
    cases = sensitivity_cases(
        minimum_rr_values=(1.5,), stop_buffers=(0.0,), slippages=(0.0, 0.1),
        exit_slippages=(0.0,), commissions_per_unit=(0.0,)
    )
    assert [case.name for case in cases] == [
        "rr=1.5|buffer=0|entry_slip=0|exit_slip=0|commission=0",
        "rr=1.5|buffer=0|entry_slip=0.1|exit_slip=0|commission=0",
    ]
    assert all(case.config.minimum_reward_risk > 0 for case in cases)


def test_run_cases_uses_independent_backtests():
    sessions = {
        "2026-01-02": bars(
            (100.5, 100.8, 99.0, 99.5),
            (99.5, 101.5, 99.2, 101.2),
            (101.2, 105.0, 101.0, 104.0),
            (104.0, 106.0, 103.8, 105.5),
        )
    }
    levels = {"2026-01-02": DailyLevels("2026-01-02", pdh=106.0, pdl=100.0)}
    cases = [
        ResearchCase("baseline", BacktestConfig()),
        ResearchCase("higher_rr", BacktestConfig(minimum_reward_risk=2.0)),
    ]
    results = run_cases(sessions, levels, cases)
    assert [result.name for result in results] == ["baseline", "higher_rr"]
    assert results[0].metrics["total_trades"] == 1
    assert results[1].metrics["total_trades"] == 1
