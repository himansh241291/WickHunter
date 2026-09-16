from datetime import datetime, timezone

from wickhunter.execution import ExecutionConfig
from wickhunter.ledger import TradeLedger
from wickhunter.paper import PaperBroker
from wickhunter.risk import BuyRiskGuard, RiskLimits, RiskState
from wickhunter.safety import KillSwitch
from wickhunter.tick import Tick


def _time(minute=0):
    return datetime(2026, 1, 2, 9, minute, tzinfo=timezone.utc)


def test_paper_buy_and_target_close_updates_equity():
    state = RiskState(starting_equity=100_000, equity=100_000)
    broker = PaperBroker(state, execution=ExecutionConfig(commission_per_unit=0.01))
    position = broker.submit_buy(time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01)
    assert position is not None
    assert state.trades_today == 1
    close = broker.process_tick(Tick(_time(1), 105))
    assert close is not None and close.result == "WIN"
    assert close.net_pnl > 0
    assert broker.position is None and state.equity > 100_000


def test_paper_stop_is_first_ordered_tick_threshold():
    state = RiskState(starting_equity=100_000, equity=100_000)
    broker = PaperBroker(state)
    broker.submit_buy(time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01)
    close = broker.process_tick(Tick(_time(1), 98.5))
    assert close is not None and close.result == "LOSS"
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


def test_paper_ledger_and_kill_switch_survive_restart(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = TradeLedger(path)
    switch = KillSwitch(ledger)
    state = RiskState(starting_equity=100_000, equity=100_000)
    broker = PaperBroker(state, ledger=ledger, kill_switch=switch)
    assert broker.submit_buy(time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01)
    broker.process_tick(Tick(_time(1), 105))
    switch.engage(time=_time(2), reason="test")
    restarted_switch = KillSwitch(TradeLedger(path))
    assert restarted_switch.is_halted()
    restarted_state = TradeLedger(path).snapshot()
    assert restarted_state["open_position"] is None
    restarted_broker = PaperBroker(RiskState(starting_equity=100_000, equity=100_000), kill_switch=restarted_switch)
    assert restarted_broker.submit_buy(time=_time(3), trigger=101, stop=99, target=105, requested_risk_fraction=0.01) is None


def test_paper_blocks_new_buy_when_persisted_position_is_unreconciled(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = TradeLedger(path)
    state = RiskState(starting_equity=100_000, equity=100_000)
    broker = PaperBroker(state, ledger=ledger)
    assert broker.submit_buy(time=_time(), trigger=101, stop=99, target=105, requested_risk_fraction=0.01)

    restarted = PaperBroker(
        RiskState(starting_equity=100_000, equity=100_000),
        ledger=TradeLedger(path),
    )
    assert restarted.submit_buy(time=_time(1), trigger=102, stop=100, target=106, requested_risk_fraction=0.01) is None
    assert restarted.audit[-1]["reason"] == "unreconciled_open_position"
