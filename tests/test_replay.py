from datetime import datetime, timezone

from wickhunter.ledger import TradeLedger
from wickhunter.replay import load_ticks, replay_buy_intents
from wickhunter.tick import Tick


def test_load_ticks_orders_input(tmp_path):
    path = tmp_path / "ticks.csv"
    path.write_text(
        "time,price\n"
        "2026-01-02T09:02:00+00:00,105\n"
        "2026-01-02T09:01:00+00:00,101\n",
        encoding="utf-8",
    )
    ticks = load_ticks(path)
    assert ticks[0].price == 101


def test_replay_buy_intent_closes_on_target(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    ticks = [
        Tick(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc), 100),
        Tick(datetime(2026, 1, 2, 9, 1, tzinfo=timezone.utc), 101),
        Tick(datetime(2026, 1, 2, 9, 2, tzinfo=timezone.utc), 105),
    ]
    state = replay_buy_intents(
        ticks,
        [{"time": "2026-01-02T09:01:00+00:00", "trigger": 101, "stop": 99, "target": 105}],
        ledger=ledger,
    )
    assert state.equity > state.starting_equity
    assert state.trades_today == 1
    assert ledger.snapshot()["open_position"] is None


def test_replay_waits_for_trigger_and_uses_observed_gap_price():
    ticks = [
        Tick(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc), 100),
        Tick(datetime(2026, 1, 2, 9, 1, tzinfo=timezone.utc), 100.5),
        Tick(datetime(2026, 1, 2, 9, 2, tzinfo=timezone.utc), 101.25),
        Tick(datetime(2026, 1, 2, 9, 3, tzinfo=timezone.utc), 105),
    ]
    state = replay_buy_intents(
        ticks,
        [{"time": "2026-01-02T09:00:00+00:00", "trigger": 101, "stop": 99, "target": 105}],
    )
    assert state.trades_today == 1
    assert state.equity > state.starting_equity


def test_replay_does_not_fill_when_trigger_is_never_reached():
    ticks = [
        Tick(datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc), 100),
        Tick(datetime(2026, 1, 2, 9, 1, tzinfo=timezone.utc), 100.5),
    ]
    state = replay_buy_intents(
        ticks,
        [{"time": "2026-01-02T09:00:00+00:00", "trigger": 101, "stop": 99, "target": 105}],
    )
    assert state.trades_today == 0
    assert state.equity == state.starting_equity
