from datetime import datetime, timezone

from wickhunter.ledger import TradeLedger
from wickhunter.safety import recover_risk_state


def test_recover_risk_state_rebuilds_equity_and_daily_counters(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    day1 = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 1, 3, 9, 0, tzinfo=timezone.utc)
    ledger.append("BUY_FILLED", time=day1, entry=101, stop=99, target=105, quantity=10)
    ledger.append("POSITION_CLOSED", time=day1, result="LOSS", exit=99, net_pnl=-20)
    ledger.append("BUY_FILLED", time=day1.replace(hour=10), entry=100, stop=98, target=105, quantity=10)
    ledger.append("POSITION_CLOSED", time=day1.replace(hour=10), result="WIN", exit=105, net_pnl=50)
    ledger.append("BUY_FILLED", time=day2, entry=102, stop=100, target=106, quantity=10)

    state = recover_risk_state(ledger, starting_equity=100_000, as_of=day2)
    assert state.equity == 100_030
    assert state.trades_today == 1
    assert state.daily_pnl == 0
    assert state.day_starting_equity == 100_030
    assert state.consecutive_losses == 0


def test_recover_risk_state_preserves_consecutive_losses(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    base = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    for i, pnl in enumerate((-10, -20, -5)):
        t = base.replace(minute=i)
        ledger.append("BUY_FILLED", time=t, entry=101, stop=99, target=105, quantity=10)
        ledger.append("POSITION_CLOSED", time=t, result="LOSS", exit=99, net_pnl=pnl)

    state = recover_risk_state(ledger, starting_equity=100_000, as_of=base.replace(minute=5))
    assert state.equity == 99_965
    assert state.consecutive_losses == 3


def test_recover_risk_state_uses_requested_timezone(tmp_path):
    from datetime import timedelta
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    india = timezone(timedelta(hours=5, minutes=30))
    utc = timezone.utc
    late = datetime(2026, 1, 2, 23, 45, tzinfo=utc)
    ledger.append("BUY_FILLED", time=late, entry=101, stop=99, target=105, quantity=10)
    state = recover_risk_state(ledger, starting_equity=100_000, as_of=datetime(2026, 1, 3, 1, 0, tzinfo=utc), timezone_name="Asia/Kolkata")
    assert state.trades_today == 1
    assert state.day_starting_equity == 100_000
