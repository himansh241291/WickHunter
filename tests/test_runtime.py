from datetime import datetime, timezone

from wickhunter.ledger import TradeLedger
from wickhunter.ports import BuyOrder, CloseReceipt, OrderReceipt
from wickhunter.runtime import LiveRuntime


class RuntimeExecution:
    def __init__(self, position=None):
        self._position = position
        self.orders = []

    def submit_buy(self, order: BuyOrder) -> OrderReceipt:
        self.orders.append(order)
        return OrderReceipt("o1", order.time, order.trigger, order.quantity, order.client_order_id)

    def find_buy_order(self, client_order_id):
        return None

    def close_long(self, *, time, price, client_order_id=""):
        return CloseReceipt("c1", time, price, 1, client_order_id)

    def find_close_order(self, client_order_id):
        return None

    def position(self):
        return self._position


def test_runtime_recovers_risk_and_starts_without_open_position(tmp_path):
    ledger = TradeLedger(tmp_path / "ledger.jsonl")
    now = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    ledger.append(
        "BUY_FILLED", time=now, order_id="buy-1", client_order_id="c",
        entry=101, stop=99, target=106, quantity=100
    )
    ledger.append(
        "POSITION_CLOSED", time=now, order_id="close-1",
        client_order_id="cc", result="WIN", exit=106,
        quantity=100, net_pnl=500
    )
    runtime = LiveRuntime(
        pdl=100, pdh=106, execution=RuntimeExecution(),
        ledger=ledger, starting_equity=100_000,
    )
    started = runtime.start()
    assert started.position_monitor is None
    assert started.risk_state.equity == 100_500
    assert not runtime.coordinator.halted
