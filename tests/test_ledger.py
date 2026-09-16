from datetime import datetime, timezone

import pytest

from wickhunter.ledger import TradeLedger
from wickhunter.safety import KillSwitch, recover_open_position


def t():
    return datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)


def test_ledger_round_trip_and_recovery(tmp_path):
    ledger = TradeLedger(tmp_path / "trades.jsonl")
    ledger.append("BUY_FILLED", time=t(), entry=101.0, stop=99.0, target=110.0, quantity=5.0)
    snapshot = ledger.snapshot()
    assert snapshot["open_position"]["entry"] == 101.0
    assert recover_open_position(ledger)["target"] == 110.0

    ledger.append("POSITION_CLOSED", time=t(), result="WIN", exit=110.0, net_pnl=45.0)
    assert ledger.snapshot()["open_position"] is None


def test_kill_switch_persists(tmp_path):
    path = tmp_path / "trades.jsonl"
    ledger = TradeLedger(path)
    switch = KillSwitch(ledger)
    assert switch.allow_buy()
    switch.engage(time=t(), reason="operator")
    assert not KillSwitch(TradeLedger(path)).allow_buy()
    switch.release(time=t(), reason="operator")
    assert KillSwitch(TradeLedger(path)).allow_buy()


def test_corrupt_ledger_fails_closed(tmp_path):
    path = tmp_path / "trades.jsonl"
    path.write_text('{"bad": true}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        TradeLedger(path).events()
