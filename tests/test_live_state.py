from datetime import datetime, timezone

from wickhunter.ledger import TradeLedger
from wickhunter.live_state import recover_runtime


def test_runtime_recovery_restores_open_buy_without_creating_order(tmp_path):
    ledger = TradeLedger(tmp_path / "trades.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    ledger.append(
        "BUY_FILLED",
        time=now,
        entry=101.0,
        stop=99.0,
        target=106.0,
        quantity=500.0,
    )

    snapshot = recover_runtime(ledger, starting_equity=100_000.0, as_of=now)

    assert snapshot.open_position is not None
    assert snapshot.open_position["entry"] == 101.0
    assert snapshot.risk_state.equity == 100_000.0
    assert snapshot.risk_state.trades_today == 1


def test_runtime_recovery_applies_closed_trade_to_equity(tmp_path):
    ledger = TradeLedger(tmp_path / "trades.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    ledger.append("BUY_FILLED", time=now, entry=101.0, stop=99.0, target=106.0, quantity=500.0)
    ledger.append("POSITION_CLOSED", time=now.replace(hour=10), result="WIN", exit=106.0, net_pnl=2500.0)

    snapshot = recover_runtime(ledger, starting_equity=100_000.0, as_of=now.replace(hour=10))

    assert snapshot.open_position is None
    assert snapshot.risk_state.equity == 102_500.0
    assert snapshot.risk_state.trades_today == 1
