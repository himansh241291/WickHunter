from datetime import datetime, timezone

from wickhunter.models import Candle
from wickhunter.rules import is_bullish_signal, reward_risk, valid_long_geometry


def candle(open_, high, low, close):
    return Candle(datetime(2026, 1, 1, tzinfo=timezone.utc), open_, high, low, close)


def test_valid_bullish_reclaim_signal():
    c = candle(99.0, 101.0, 98.5, 100.5)
    assert is_bullish_signal(c, 100.0, previous_swept=True)


def test_signal_must_reclaim_pdl():
    c = candle(98.5, 100.2, 98.0, 99.5)
    assert not is_bullish_signal(c, 100.0, previous_swept=True)


def test_signal_requires_bullish_candle():
    c = candle(100.5, 101.0, 98.5, 99.0)
    assert not is_bullish_signal(c, 100.0, previous_swept=True)


def test_signal_requires_20_percent_body():
    c = candle(100.0, 102.0, 98.0, 100.1)
    assert not is_bullish_signal(c, 99.5, previous_swept=True)


def test_reward_risk():
    assert reward_risk(101.0, 99.0, 105.0) == 2.0


def test_long_geometry_rejects_target_below_entry():
    assert not valid_long_geometry(101.0, 99.0, 100.0, 1.5)


def test_long_geometry_accepts_required_rr():
    assert valid_long_geometry(101.0, 99.0, 104.0, 1.5)
