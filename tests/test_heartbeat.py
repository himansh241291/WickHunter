from datetime import datetime, timedelta, timezone

import pytest

from wickhunter.heartbeat import FeedHealth


def test_feed_health_accepts_fresh_ordered_ticks():
    base = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    feed = FeedHealth(timedelta(seconds=5))
    feed.observe(base)
    feed.observe(base + timedelta(seconds=1))
    assert feed.allow_buy(base + timedelta(seconds=5))


def test_feed_health_halts_on_stale_data():
    base = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    feed = FeedHealth(timedelta(seconds=5))
    feed.observe(base)
    assert not feed.allow_buy(base + timedelta(seconds=6))
    assert feed.halted
    assert feed.reason == "stale_market_data"


def test_feed_health_requires_ordered_timezone_aware_ticks():
    base = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    feed = FeedHealth(timedelta(seconds=5))
    feed.observe(base)
    with pytest.raises(ValueError):
        feed.observe(base)
    with pytest.raises(ValueError):
        FeedHealth(timedelta(seconds=5)).observe(datetime(2026, 1, 2, 9))


def test_feed_health_recovery_requires_new_tick():
    base = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    feed = FeedHealth(timedelta(seconds=5))
    feed.observe(base)
    assert not feed.allow_buy(base + timedelta(seconds=6))
    assert not feed.allow_buy(base + timedelta(seconds=7))
    feed.observe(base + timedelta(seconds=8))
    assert feed.allow_buy(base + timedelta(seconds=8))
