from datetime import datetime, timedelta, timezone

from wickhunter.engine import State
from wickhunter.ledger import TradeLedger
from wickhunter.live import BuyCoordinator, buy_client_order_id
from wickhunter.models import Candle
from wickhunter.ports import BuyOrder, CloseReceipt, OrderReceipt
from wickhunter.risk import RiskState
from wickhunter.safety import KillSwitch


class FakeExecution:
    def __init__(self, position=None):
        self.orders = []
        self._position = position

    def submit_buy(self, order: BuyOrder) -> OrderReceipt:
        self.orders.append(order)
        return OrderReceipt(
            "paper-1", order.time, order.trigger, order.quantity, order.client_order_id
        )

    def find_buy_order(self, client_order_id):
        return None

    def close_long(self, *, time, price):
        raise AssertionError("live coordinator must not create a SELL entry")

    def position(self):
        return self._position


def setup():
    start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    candles = [
        Candle(start, 100.5, 100.8, 99.0, 99.5),
        Candle(start + timedelta(minutes=1), 99.5, 101.5, 99.2, 101.2),
    ]
    return start, candles


def make_coordinator(broker=None, ledger=None):
    return BuyCoordinator(
        pdl=100, pdh=106, execution=broker or FakeExecution(),
        risk_state=RiskState(100000, 100000), ledger=ledger,
    )


def test_signal_arms_buy_for_immediate_confirmation_candle():
    start, candles = setup()
    coordinator = make_coordinator()
    assert coordinator.on_completed_candle(candles[0]) is None
    armed = coordinator.on_completed_candle(candles[1])
    assert armed is not None
    assert armed.order.trigger == 101.5
    assert armed.order.time == start + timedelta(minutes=2)
    assert armed.expires_at == start + timedelta(minutes=3)


def test_buy_intent_is_persisted_before_submission(tmp_path):
    start, candles = setup()
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    coordinator = make_coordinator(ledger=ledger)
    coordinator.on_completed_candle(candles[0])
    armed = coordinator.on_completed_candle(candles[1])

    pending = ledger.snapshot()["pending_buy"]
    assert pending is not None
    assert pending["client_order_id"] == armed.order.client_order_id


def test_restart_recovers_same_buy_id(tmp_path):
    start, candles = setup()
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    first = make_coordinator(ledger=ledger)
    first.on_completed_candle(candles[0])
    armed = first.on_completed_candle(candles[1])

    restarted = make_coordinator(ledger=ledger)
    restored = restarted.recover_pending_buy()

    assert restored is not None
    assert restored.order.client_order_id == armed.order.client_order_id
    assert restored.order.client_order_id == buy_client_order_id(
        signal_time=armed.signal_time,
        trigger=armed.order.trigger,
        stop=armed.order.stop,
        target=armed.order.target,
    )


def test_restart_does_not_duplicate_persisted_position(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    ledger.append(
        "BUY_FILLED", time=now, order_id="x", client_order_id="c",
        entry=101, stop=99, target=106, quantity=100
    )
    broker = FakeExecution({
        "entry": 101, "stop": 99, "target": 106, "quantity": 100
    })
    coordinator = make_coordinator(broker=broker, ledger=ledger)
    result = coordinator.reconcile_startup()
    assert result.safe_to_buy


def test_position_mismatch_fails_closed(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    ledger.append(
        "BUY_FILLED", time=now, order_id="x", client_order_id="c",
        entry=101, stop=99, target=106, quantity=100
    )
    broker = FakeExecution({
        "entry": 102, "stop": 99, "target": 106, "quantity": 100
    })
    coordinator = make_coordinator(broker=broker, ledger=ledger)
    result = coordinator.reconcile_startup()
    assert not result.safe_to_buy
    assert coordinator.engine.state == State.DONE


def test_tick_at_trigger_after_confirmation_start_fills_buy():
    start, candles = setup()
    broker = FakeExecution()
    coordinator = make_coordinator(broker=broker)
    coordinator.on_completed_candle(candles[0])
    coordinator.on_completed_candle(candles[1])
    receipt = coordinator.on_tick(start + timedelta(minutes=2, seconds=1), 101.5)
    assert receipt is not None
    assert len(broker.orders) == 1
    assert broker.orders[0].quantity > 0
    assert broker.orders[0].client_order_id
    assert coordinator.engine.state == State.POSITION_OPEN


def test_trigger_not_seen_before_expiry():
    start, candles = setup()
    broker = FakeExecution()
    coordinator = make_coordinator(broker=broker)
    coordinator.on_completed_candle(candles[0])
    coordinator.on_completed_candle(candles[1])
    assert coordinator.on_tick(start + timedelta(minutes=3), 101.5) is None
    assert broker.orders == []
    assert coordinator.engine.state == State.DONE

def test_restart_accepts_broker_accepted_pending_buy_without_resubmission(tmp_path):
    start, candles = setup()
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    first = make_coordinator(ledger=ledger)
    first.on_completed_candle(candles[0])
    armed = first.on_completed_candle(candles[1])

    class AcceptedExecution(FakeExecution):
        def find_buy_order(self, client_order_id):
            return OrderReceipt(client_order_id, start + timedelta(minutes=2, seconds=2), 101.6, 900)

    broker = AcceptedExecution()
    restarted = make_coordinator(broker=broker, ledger=ledger)
    restored = restarted.recover_pending_buy()

    assert restored is None
    assert restarted.receipt is not None
    assert broker.orders == []
    assert ledger.snapshot()["pending_buy"] is None


def test_position_monitor_closes_existing_long_at_stop(tmp_path):
    from wickhunter.position import LongPositionMonitor

    class PositionExecution(FakeExecution):
        def __init__(self):
            super().__init__({"entry": 101, "stop": 99, "target": 106, "quantity": 100})

        def close_long(self, *, time, price):
            return CloseReceipt("close-1", time, price, 100)

    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    ledger.append(
        "BUY_FILLED", time=now, order_id="buy-1", client_order_id="c",
        entry=101, stop=99, target=106, quantity=100
    )
    monitor = LongPositionMonitor(execution=PositionExecution(), ledger=ledger)
    assert monitor.reconcile().safe_to_buy is True
    receipt = monitor.on_price(time=now, price=98.5, stop=99, target=106)
    assert receipt is not None
    assert receipt.fill_price == 99
    assert ledger.snapshot()["open_position"] is None


def test_position_monitor_closes_at_session_end(tmp_path):
    from wickhunter.position import LongPositionMonitor

    class PositionExecution(FakeExecution):
        def __init__(self):
            super().__init__({"entry": 101, "stop": 99, "target": 106, "quantity": 100})

        def close_long(self, *, time, price):
            return CloseReceipt("close-2", time, price, 100)

    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    now = datetime(2026, 1, 2, 15, 29, tzinfo=timezone.utc)
    ledger.append(
        "BUY_FILLED", time=now, order_id="buy-1", client_order_id="c",
        entry=101, stop=99, target=106, quantity=100
    )
    monitor = LongPositionMonitor(execution=PositionExecution(), ledger=ledger)
    receipt = monitor.on_price(
        time=now, price=104, stop=99, target=106, session_end=True
    )
    assert receipt is not None
    assert receipt.fill_price == 104
    assert ledger.snapshot()["open_position"] is None


def test_restart_restores_persisted_kill_switch(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    KillSwitch(ledger).engage(time=now, reason="stale_feed")
    coordinator = make_coordinator(ledger=ledger)
    coordinator.reconcile_startup()
    assert coordinator.halted
    assert coordinator.recover_pending_buy() is None
