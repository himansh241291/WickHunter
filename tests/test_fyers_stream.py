from wickhunter.fyers_stream import FyersDataStream


class FakeSocket:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.subscriptions = []
        self.running = False

    def connect(self):
        self.kwargs["on_connect"]()

    def subscribe(self, *, symbols, data_type):
        self.subscriptions.append((symbols, data_type))

    def keep_running(self):
        self.running = True


def test_fyers_stream_subscribes_symbol_update(monkeypatch):
    monkeypatch.setenv("FYERS_APP_ID", "APP-100")
    monkeypatch.setenv("FYERS_ACCESS_TOKEN", "TOKEN")
    messages = []
    holder = {}

    def factory(**kwargs):
        sock = FakeSocket(**kwargs)
        holder["socket"] = sock
        return sock

    stream = FyersDataStream(
        symbol="NSE:RELIANCE-EQ",
        on_tick=messages.append,
        socket_factory=factory,
    )
    stream.connect()

    sock = holder["socket"]
    assert sock.subscriptions == [(["NSE:RELIANCE-EQ"], "SymbolUpdate")]
    assert sock.running
    assert sock.kwargs["access_token"] == "APP-100:TOKEN"

    msg = {"symbol": "NSE:RELIANCE-EQ", "ltp": 1248, "type": "sf"}
    sock.kwargs["on_message"](msg)
    assert messages == [msg]


def test_fyers_stream_records_errors(monkeypatch):
    monkeypatch.setenv("FYERS_APP_ID", "APP-100")
    monkeypatch.setenv("FYERS_ACCESS_TOKEN", "TOKEN")
    holder = {}

    def factory(**kwargs):
        holder["socket"] = FakeSocket(**kwargs)
        return holder["socket"]

    stream = FyersDataStream(symbol="NSE:RELIANCE-EQ", on_tick=lambda _: None, socket_factory=factory)
    stream.connect()
    error = {"code": 403}
    holder["socket"].kwargs["on_error"](error)
    assert stream.last_error == error
