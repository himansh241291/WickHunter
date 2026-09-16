from datetime import datetime, timedelta, timezone

import pytest

from wickhunter.backtest import BacktestConfig, DailyLevels
from wickhunter.models import Candle
from wickhunter.research import ResearchCase
from wickhunter.walkforward import make_rolling_windows, run_walk_forward


def bars(day: int):
    start = datetime(2026, 1, day, 9, 0, tzinfo=timezone.utc)
    return [
        Candle(start, 100.5, 100.8, 99.0, 99.5),
        Candle(start + timedelta(minutes=1), 99.5, 101.5, 99.2, 101.2),
        Candle(start + timedelta(minutes=2), 101.2, 105.0, 101.0, 104.0),
        Candle(start + timedelta(minutes=3), 104.0, 106.0, 103.8, 105.5),
    ]


def test_rolling_windows_are_chronological_and_non_overlapping():
    windows = make_rolling_windows(
        [f"2026-01-{day:02d}" for day in range(1, 11)],
        train_size=4,
        test_size=2,
        step=2,
    )
    assert len(windows) == 3
    assert windows[0].train_sessions == ("2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04")
    assert windows[0].test_sessions == ("2026-01-05", "2026-01-06")
    for window in windows:
        assert set(window.train_sessions).isdisjoint(window.test_sessions)
        assert max(window.train_sessions) < min(window.test_sessions)


def test_invalid_window_sizes_rejected():
    with pytest.raises(ValueError):
        make_rolling_windows(["2026-01-01"], 0, 1)
    with pytest.raises(ValueError):
        make_rolling_windows(["2026-01-01"], 1, 1, step=0)


def test_walk_forward_returns_separate_train_and_test_metrics():
    sessions = {f"2026-01-{day:02d}": bars(day) for day in range(1, 7)}
    levels = {
        f"2026-01-{day:02d}": DailyLevels(f"2026-01-{day:02d}", pdh=106.0, pdl=100.0)
        for day in range(1, 7)
    }
    case = ResearchCase("baseline", BacktestConfig())
    window = make_rolling_windows(sorted(sessions), train_size=3, test_size=2)[0]
    results = run_walk_forward(sessions, levels, [case], [window])
    assert len(results) == 1
    assert results[0].window == "WF001"
    assert results[0].case == "baseline"
    assert results[0].train_metrics["total_trades"] == 3
    assert results[0].test_metrics["total_trades"] == 2
