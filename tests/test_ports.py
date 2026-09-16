from datetime import datetime, timezone

from wickhunter.ports import BuyOrder, OrderReceipt


def test_buy_order_is_explicit_and_long_only():
    order = BuyOrder(
        time=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
        quantity=10,
        trigger=101,
        stop=99,
        target=105,
    )
    assert order.quantity == 10
    assert order.trigger == 101
    assert order.stop < order.trigger < order.target


def test_order_receipt_carries_observed_fill():
    receipt = OrderReceipt("abc", datetime(2026, 1, 2, 9, tzinfo=timezone.utc), 101.25, 10)
    assert receipt.order_id == "abc"
    assert receipt.fill_price == 101.25
