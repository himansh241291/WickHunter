from wickhunter.groww_market import GrowwMarketData


class FakeMarketAPI:
    CANDLE_INTERVAL_MIN_1 = "1m"

    def get_instrument_by_exchange_and_trading_symbol(self, **kwargs):
        return {"payload": {"exchange_token": 2885, "trading_symbol": kwargs["trading_symbol"]}}

    def get_ltp(self, **kwargs):
        return {"NSE_RELIANCE": 2500.5}

    def get_quote(self, **kwargs):
        return {"payload": {"last_price": 2500.5, "bid_price": 2500.0}}

    def get_historical_candles(self, **kwargs):
        assert kwargs["candle_interval"] == "1m"
        return {"payload": {"candles": [
            ["2026-09-22T09:15:00", 2500, 2505, 2498, 2503, 1000, None],
        ]}}


def test_groww_market_read_only():
    market = GrowwMarketData(trading_symbol="RELIANCE", api=FakeMarketAPI())

    assert market.instrument()["exchange_token"] == 2885
    assert market.ltp() == 2500.5
    assert market.quote()["last_price"] == 2500.5
    assert market.historical_m1(
        start_time="2026-09-22 09:15:00",
        end_time="2026-09-22 09:16:00",
    )[0][4] == 2503
