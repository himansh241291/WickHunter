from datetime import datetime, timedelta, timezone

from wickhunter.engine import State
from wickhunter.live import BuyCoordinator
from wickhunter.models import Candle
from wickhunter.ports import BuyOrder, OrderReceipt
from wickhunter.risk import RiskState


class FakeExecution:
    def __init__(self):
        self.orders = []

    def submit_buy(self, order: BuyOrder) -> OrderReceipt:
        self.orders.append(order)
        return OrderReceipt("paper-1", order.time, order.trigger, order.quantity)

    def close_long(self, *, time, price):
        raise AssertionError("live coordinator must not create a SELL entry")

    def position(self):
        return None


def setup():
    start = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    candles = [
        Candle(start, 100.5, 100.8, 99.0, 99.5),
        Candle(start + timedelta(minutes=1), 99.5, 101.5, 99.2, 101.2),
    ]
    return start, candles


def test_signal_arms_buy_for_immediate_confirmation_candle():
    start, candles = setup()
    broker = FakeExecution()
    coordinator = BuyCoordinator(
        pdl=100, pdh=106, execution=broker,
        risk_state=RiskState(100000, 100000),
    )
    assert coordinator.on_completed_candle(candles[0]) is None
    armed = coordinator.on_completed_candle(candles[1])
    assert armed is not None
    assert armed.order.trigger == 101.5
    assert armed.order.time == start + timedelta(minutes=2)
    assert armed.expires_at == start + timedelta(minutes=3)
    assert coordinator.engine.state == State.LONG_READY


def test_tick_at_trigger_after_confirmation_start_fills_buy():
    start, candles = setup()
    broker = FakeExecution()
    coordinator = BuyCoordinator(
        pdl=100, pdh=106, execution=broker,
        risk_state=RiskState(100000, 100000),
    )
    coordinator.on_completed_candle(candles[0])
    coordinator.on_completed_candle(candles[1])
    receipt = coordinator.on_tick(start + timedelta(minutes=2, seconds=1), 101.5)
    assert receipt is not None
    assert len(broker.orders) == 1
    assert broker.orders[0].quantity > 0
    assert coordinator.engine.state == State.POSITION_OPEN


def test_trigger_not_seen_before_expiry():
    start, candles = setup()
    broker = FakeExecution()
    coordinator = BuyCoordinator(
        pdl=100, pdh=106, execution=broker,
        risk_state=RiskState(100000, 100000),
    )
    coordinator.on_completed_candle(candles[0])
    coordinator.on_completed_candle(candles[1])
    assert coordinator.on_tick(start + timedelta(minutes=3), 101.5) is None
    assert broker.orders == []
    assert coordinator.engine.state == State.DONE
