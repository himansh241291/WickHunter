"""Groww broker adapter for WickHunter.

Credentials are read from environment variables and are never stored in the
repository. The adapter exposes BUY entry plus lifecycle closure of an
existing long; it does not expose a SELL-entry strategy operation.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .env import load_local_env
from .ports import BuyOrder, CloseReceipt, OrderReceipt


def _reference_id(client_order_id: str) -> str:
    """Map the full WickHunter ID to Groww's 20-character reference limit."""
    import hashlib
    return "WH" + hashlib.sha256(client_order_id.encode()).hexdigest()[:18].upper()


class GrowwExecution:
    """Broker adapter for one configured NSE/BSE cash instrument."""

    def __init__(
        self,
        *,
        trading_symbol: str,
        exchange: str = "NSE",
        segment: str = "CASH",
        product: str = "CNC",
        api: Any | None = None,
    ) -> None:
        self.trading_symbol = trading_symbol
        self.exchange = exchange
        self.segment = segment
        self.product = product
        self.api = api or self._build_api()
        self._buy_receipts: dict[str, OrderReceipt] = {}
        self._close_receipts: dict[str, CloseReceipt] = {}

    @staticmethod
    def _build_api() -> Any:
        load_local_env()
        api_key = os.environ.get("GROWW_API_KEY")
        secret = os.environ.get("GROWW_API_SECRET")
        if not api_key or not secret:
            raise RuntimeError("GROWW_API_KEY and GROWW_API_SECRET are required")
        from growwapi import GrowwAPI
        access_token = GrowwAPI.get_access_token(api_key=api_key, secret=secret)
        return GrowwAPI(access_token)

    def submit_buy(self, order: BuyOrder) -> OrderReceipt:
        reference = _reference_id(order.client_order_id)
        existing = self.find_buy_order(order.client_order_id)
        if existing is not None:
            return existing

        response = self.api.place_order(
            trading_symbol=self.trading_symbol,
            quantity=int(order.quantity),
            validity=self.api.VALIDITY_DAY,
            exchange=self.exchange,
            segment=self.segment,
            product=self.product,
            order_type=self.api.ORDER_TYPE_MARKET,
            transaction_type=self.api.TRANSACTION_TYPE_BUY,
            price=0,
            order_reference_id=reference,
        )
        payload = _payload(response)
        order_id = str(payload.get("groww_order_id", ""))
        if not order_id:
            raise RuntimeError(f"Groww BUY response has no order id: {response}")

        detail = self.api.get_order_detail(
            groww_order_id=order_id, segment=self.segment
        )
        detail_payload = _payload(detail)
        fill_price = float(
            detail_payload.get(
                "average_fill_price",
                detail_payload.get("price", order.trigger),
            )
        )
        filled_quantity = int(
            detail_payload.get("filled_quantity", payload.get("filled_quantity", order.quantity))
        )
        receipt = OrderReceipt(
            order_id=order_id,
            time=_parse_time(
                detail_payload.get("exchange_time")
                or detail_payload.get("created_at")
                or order.time.isoformat()
            ),
            fill_price=fill_price,
            quantity=filled_quantity,
            client_order_id=order.client_order_id,
        )
        self._buy_receipts[order.client_order_id] = receipt
        return receipt

    def find_buy_order(self, client_order_id: str) -> OrderReceipt | None:
        if client_order_id in self._buy_receipts:
            return self._buy_receipts[client_order_id]
        reference = _reference_id(client_order_id)
        try:
            response = self.api.get_order_status_by_reference_id(
                order_reference_id=reference, segment=self.segment
            )
        except Exception:
            return None
        payload = _payload(response)
        if not payload:
            return None
        if str(payload.get("order_reference_id", "")) != reference:
            return None
        if str(payload.get("transaction_type", "BUY")).upper() != "BUY":
            return None
        order_id = str(payload.get("groww_order_id", ""))
        if not order_id:
            return None
        detail = self.api.get_order_detail(
            groww_order_id=order_id, segment=self.segment
        )
        detail_payload = _payload(detail)
        filled = int(detail_payload.get("filled_quantity", 0))
        if filled <= 0:
            return None
        receipt = OrderReceipt(
            order_id=order_id,
            time=_parse_time(
                detail_payload.get("exchange_time")
                or detail_payload.get("created_at")
            ),
            fill_price=float(
                detail_payload.get(
                    "average_fill_price", detail_payload.get("price", 0)
                )
            ),
            quantity=filled,
            client_order_id=client_order_id,
        )
        self._buy_receipts[client_order_id] = receipt
        return receipt

    def close_long(
        self, *, time: datetime, price: float, client_order_id: str = ""
    ) -> CloseReceipt:
        if client_order_id:
            existing = self.find_close_order(client_order_id)
            if existing is not None:
                return existing

        position = self.position()
        if position is None:
            raise RuntimeError("no configured Groww long position to close")
        quantity = int(position["quantity"])
        reference = _reference_id(client_order_id or f"WHC{int(time.timestamp())}")

        response = self.api.place_order(
            trading_symbol=self.trading_symbol,
            quantity=quantity,
            validity=self.api.VALIDITY_DAY,
            exchange=self.exchange,
            segment=self.segment,
            product=self.product,
            order_type=self.api.ORDER_TYPE_MARKET,
            transaction_type=self.api.TRANSACTION_TYPE_SELL,
            price=0,
            order_reference_id=reference,
        )
        payload = _payload(response)
        order_id = str(payload.get("groww_order_id", ""))
        if not order_id:
            raise RuntimeError(f"Groww close response has no order id: {response}")

        detail = self.api.get_order_detail(
            groww_order_id=order_id, segment=self.segment
        )
        detail_payload = _payload(detail)
        filled = int(detail_payload.get("filled_quantity", quantity))
        receipt = CloseReceipt(
            order_id=order_id,
            time=_parse_time(
                detail_payload.get("exchange_time")
                or detail_payload.get("created_at")
                or time.isoformat()
            ),
            fill_price=float(
                detail_payload.get("average_fill_price", detail_payload.get("price", price))
            ),
            quantity=filled,
            client_order_id=client_order_id,
        )
        if client_order_id:
            self._close_receipts[client_order_id] = receipt
        return receipt

    def find_close_order(self, client_order_id: str) -> CloseReceipt | None:
        if client_order_id in self._close_receipts:
            return self._close_receipts[client_order_id]
        reference = _reference_id(client_order_id)
        try:
            response = self.api.get_order_status_by_reference_id(
                order_reference_id=reference, segment=self.segment
            )
        except Exception:
            return None
        payload = _payload(response)
        if not payload:
            return None
        if str(payload.get("order_reference_id", "")) != reference:
            return None
        if str(payload.get("transaction_type", "")).upper() != "SELL":
            return None
        order_id = str(payload.get("groww_order_id", ""))
        if not order_id:
            return None
        detail = self.api.get_order_detail(
            groww_order_id=order_id, segment=self.segment
        )
        detail_payload = _payload(detail)
        filled = int(detail_payload.get("filled_quantity", 0))
        if filled <= 0:
            return None
        receipt = CloseReceipt(
            order_id=order_id,
            time=_parse_time(
                detail_payload.get("exchange_time")
                or detail_payload.get("created_at")
            ),
            fill_price=float(
                detail_payload.get("average_fill_price", detail_payload.get("price", 0))
            ),
            quantity=filled,
            client_order_id=client_order_id,
        )
        self._close_receipts[client_order_id] = receipt
        return receipt

    def position(self) -> dict[str, Any] | None:
        response = self.api.get_position_for_trading_symbol(
            trading_symbol=self.trading_symbol, segment=self.segment
        )
        payload = _payload(response)
        positions = payload.get("positions", []) if isinstance(payload, dict) else []
        if not positions:
            return None
        item = positions[0]
        quantity = float(item.get("quantity", 0))
        if quantity <= 0:
            return None
        return {
            "trading_symbol": self.trading_symbol,
            "exchange": self.exchange,
            "segment": self.segment,
            "product": item.get("product", self.product),
            "quantity": quantity,
            "entry": float(item.get("net_price", item.get("credit_price", 0))),
        }


def _payload(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    payload = response.get("payload", response)
    return payload if isinstance(payload, dict) else {}


def _parse_time(value: Any) -> datetime:
    if value is None:
        raise RuntimeError("Groww response has no timestamp")
    text = str(value).replace("Z", "+00:00")
    result = datetime.fromisoformat(text)
    if result.tzinfo is None or result.utcoffset() is None:
        raise RuntimeError("Groww timestamp is not timezone-aware")
    return result
