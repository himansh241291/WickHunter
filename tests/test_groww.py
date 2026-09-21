from datetime import datetime, timezone

from wickhunter.groww import GrowwExecution, _reference_id
from wickhunter.ports import BuyOrder


class FakeGroww:
    VALIDITY_DAY = "DAY"
    ORDER_TYPE_MARKET = "MARKET"
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"

    def __init__(self):
        self.orders = []
        self.details = {}

    def place_order(self, **kwargs):
        self.orders.append(kwargs)
        oid = f"O{len(self.orders)}"
        self.details[oid] = {
            "groww_order_id": oid,
            "order_reference_id": kwargs["order_reference_id"],
            "transaction_type": kwargs["transaction_type"],
            "filled_quantity": kwargs["quantity"],
            "average_fill_price": 101.25,
            "exchange_time": "2026-01-02T09:00:01+00:00",
        }
        return {"status": "SUCCESS", "payload": {"groww_order_id": oid}}

    def get_order_detail(self, *, groww_order_id, segment):
        return {"status": "SUCCESS", "payload": self.details[groww_order_id]}

    def get_order_status_by_reference_id(self, *, order_reference_id, segment):
        for item in self.details.values():
            if item["order_reference_id"] == order_reference_id:
                return {"status": "SUCCESS", "payload": item}
        return {"status": "SUCCESS", "payload": {}}

    def get_position_for_trading_symbol(self, *, trading_symbol, segment):
        return {"status": "SUCCESS", "payload": {"positions": [{
            "trading_symbol": trading_symbol,
            "quantity": 100,
            "net_price": 101.25,
            "product": "CNC",
        }]}}


def test_groww_reference_is_20_chars_and_stable():
    assert len(_reference_id("wh-buy-abc")) == 20
    assert _reference_id("wh-buy-abc") == _reference_id("wh-buy-abc")


def test_groww_buy_and_idempotent_lookup():
    api = FakeGroww()
    broker = GrowwExecution(trading_symbol="RELIANCE", api=api)
    order = BuyOrder(
        time=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        quantity=100, trigger=101, stop=99, target=106,
        client_order_id="wh-buy-test",
    )
    receipt = broker.submit_buy(order)
    assert receipt.order_id == "O1"
    assert receipt.fill_price == 101.25
    assert len(api.orders) == 1
    assert broker.find_buy_order(order.client_order_id).order_id == "O1"


def test_groww_position_is_long_only():
    broker = GrowwExecution(trading_symbol="RELIANCE", api=FakeGroww())
    position = broker.position()
    assert position["quantity"] == 100
    assert position["entry"] == 101.25
