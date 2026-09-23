from wickhunter.fyers_market import FyersMarketData


class FakeFyers:
    def get_profile(self):
        return {"s": "ok", "code": 200, "data": {"name": "test"}}

    def quotes(self, data):
        assert data == {"symbols": "NSE:RELIANCE-EQ"}
        return {"s": "ok", "d": [{"v": {"lp": 100.0}}]}

    def history(self, data):
        assert data["resolution"] == "1"
        assert data["symbol"] == "NSE:RELIANCE-EQ"
        return {"s": "ok", "candles": [[1, 100, 101, 99, 100.5, 10]]}


def test_profile_and_quote():
    client = FyersMarketData(client=FakeFyers())
    assert client.profile()["s"] == "ok"
    assert client.quote()["d"][0]["v"]["lp"] == 100.0


def test_historical_m1():
    client = FyersMarketData(client=FakeFyers())
    assert client.historical_m1(start="2026-09-01", end="2026-09-02") == [[1, 100, 101, 99, 100.5, 10]]


def test_api_error_is_not_hidden():
    class ErrorClient:
        def get_profile(self):
            return {"s": "error", "code": -16, "message": "permission denied"}

    client = FyersMarketData(client=ErrorClient())
    try:
        client.profile()
    except RuntimeError as exc:
        assert "permission denied" in str(exc)
    else:
        raise AssertionError("expected FYERS API error")
