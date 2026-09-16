from datetime import datetime, timedelta, timezone

import pytest

from wickhunter.tick import Tick, resolve_long_entry, resolve_long_exit


def ticks(*prices):
    start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    return [Tick(start + timedelta(seconds=i), price) for i, price in enumerate(prices)]


def test_entry_uses_first_ordered_tick_at_trigger():
    result = resolve_long_entry(ticks(100, 100.4, 100.5, 101), 100.5)
    assert result is not None
    assert result.price == 100.5


def test_exit_uses_first_ordered_threshold():
    result = resolve_long_exit(ticks(101, 99, 105), stop=100, target=105)
    assert result is None
    result = resolve_long_exit(ticks(101, 100, 105), stop=100, target=105)
    assert result is not None
    assert result[1] == "LOSS"


def test_invalid_tick_execution_levels_rejected():
    with pytest.raises(ValueError):
        resolve_long_entry(ticks(100), 0)
    with pytest.raises(ValueError):
        resolve_long_exit(ticks(100), 105, 100)
