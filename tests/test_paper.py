from datetime import datetime, timezone

from wickhunter.execution import ExecutionConfig
from wickhunter.paper import PaperBroker
from wickhunter.risk import BuyRiskGuard, RiskLimits, RiskState
from wickhunter.tick import Tick


def _time(minute=0):
    return datetime(2026, 1, 2, 9, minute, tzinfo=timezone.utc)


def test_paper_buy_and_target_close_updates_equity():
    state = RiskState(starting_equity=100_000, equity=100_000)
    broker = PaperBroker(state, execution=ExecutionConfig(commission_per_unit=0.01))
    position = broker.submit_buy(
        time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01
    )
    assert position is not None
    assert state.trades_today == 1
    close = broker.process_tick(Tick(_time(1), 105))
    assert close is not None
    assert close.result == "WIN"
    assert close.net_pnl > 0
    assert broker.position is None
    assert state.equity > 100_000


def test_paper_stop_is_first_ordered_tick_threshold():
    state = RiskState(starting_equity=100_000, equity=100_000)
    broker = PaperBroker(state)
    broker.submit_buy(time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01)
    close = broker.process_tick(Tick(_time(1), 98.5))
    assert close is not None
    assert close.result == "LOSS"
    assert close.exit_price == 99


def test_paper_rejects_second_open_position_and_risk_violation():
    state = RiskState(starting_equity=100_000, equity=100_000)
    guard = BuyRiskGuard(RiskLimits(max_trades_per_day=1))
    broker = PaperBroker(state, guard)
    assert broker.submit_buy(time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01)
    assert broker.submit_buy(time=_time(1), trigger=102, stop=100, target=106, requested_risk_fraction=0.01) is None
    broker.close_session(time=_time(2), price=102)
    assert broker.submit_buy(time=_time(3), trigger=102, stop=100, target=106, requested_risk_fraction=0.01) is None
    assert broker.audit[-1]["reason"] == "max_trades_per_day"
