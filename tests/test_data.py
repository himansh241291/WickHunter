from datetime import datetime, timedelta, timezone

import pytest

from wickhunter.data import load_m1_csv, prepare_sessions
from wickhunter.models import Candle


def test_prepare_sessions_uses_previous_available_session_only():
    day1 = datetime(2026, 1, 2, 23, 58, tzinfo=timezone.utc)
    day2 = datetime(2026, 1, 3, 0, 0, tzinfo=timezone.utc)
    candles = [
        Candle(day1, 100, 103, 98, 101),
        Candle(day1 + timedelta(minutes=1), 101, 105, 99, 104),
        Candle(day2, 104, 110, 102, 108),
    ]
    sessions, levels = prepare_sessions(candles, "UTC")
    assert list(sessions) == ["2026-01-02", "2026-01-03"]
    assert levels["2026-01-03"].pdh == 105
    assert levels["2026-01-03"].pdl == 98


def test_load_m1_csv_rejects_naive_timestamp(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("time,open,high,low,close\n2026-01-02T09:00:00,100,101,99,100.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timezone-aware"):
        load_m1_csv(path)


def test_load_m1_csv_sorts_and_preserves_spread(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(
        "time,open,high,low,close,spread\n"
        "2026-01-02T09:01:00+00:00,101,102,100,101.5,0.2\n"
        "2026-01-02T09:00:00+00:00,100,101,99,100.5,0.1\n",
        encoding="utf-8",
    )
    candles = load_m1_csv(path)
    assert candles[0].time.minute == 0
    assert candles[0].spread == 0.1
    assert candles[1].spread == 0.2
