from datetime import datetime, timezone

import pytest

from wickhunter.replay import replay_buy_intents
from wickhunter.tick import Tick


def test_direct_replay_rejects_duplicate_tick_timestamps():
    t = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="strictly increasing"):
        replay_buy_intents([Tick(t, 100), Tick(t, 101)], [])


def test_replay_rejects_expired_intent_definition():
    ticks = [Tick(datetime(2026, 1, 2, 9, tzinfo=timezone.utc), 100)]
    intents = [{"time": "2026-01-02T09:00:00+00:00", "expires_at": "2026-01-02T09:00:00+00:00",
                "trigger": 101, "stop": 99, "target": 105}]
    with pytest.raises(ValueError, match="expires_at"):
        replay_buy_intents(ticks, intents)


def test_replay_rejects_missing_intent_geometry():
    ticks = [Tick(datetime(2026, 1, 2, 9, tzinfo=timezone.utc), 100)]
    with pytest.raises(ValueError, match="requires target"):
        replay_buy_intents(ticks, [{"time": "2026-01-02T09:00:00+00:00", "trigger": 101, "stop": 99}])
