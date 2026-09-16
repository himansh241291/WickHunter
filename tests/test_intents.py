import json
from datetime import datetime, timezone

from wickhunter.backtest import DailyLevels
from wickhunter.intents import generate_buy_intents, intents_to_jsonable
from wickhunter.models import Candle


def test_generate_buy_intents_uses_confirmation_candle():
    sessions = {
        "2026-01-01": [Candle(datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc), 100, 105, 95, 104)],
        "2026-01-02": [
            Candle(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc), 96, 96.5, 94, 94.5),
            Candle(datetime(2026, 1, 2, 9, 1, tzinfo=timezone.utc), 94.5, 96.5, 94, 96),
            Candle(datetime(2026, 1, 2, 9, 2, tzinfo=timezone.utc), 96, 97, 95.5, 96.5),
        ],
    }
    levels = {"2026-01-02": DailyLevels("2026-01-02", pdh=105, pdl=95)}
    intents = generate_buy_intents(sessions, levels, minimum_reward_risk=1.5)

    assert len(intents) == 1
    intent = intents[0]
    assert intent.trigger == 96.5
    assert intent.stop == 94
    assert intent.target == 105
    assert intent.signal_time == datetime(2026, 1, 2, 9, 1, tzinfo=timezone.utc)
    assert intent.confirmation_time == datetime(2026, 1, 2, 9, 2, tzinfo=timezone.utc)
    assert intent.expires_at == datetime(2026, 1, 2, 9, 3, tzinfo=timezone.utc)


def test_intents_are_json_serializable():
    value = intents_to_jsonable([])
    assert json.dumps(value) == "[]"
