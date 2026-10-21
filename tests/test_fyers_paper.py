from datetime import datetime
from zoneinfo import ZoneInfo

from wickhunter.candles import M1Candle, MarketTick
from wickhunter.engine import State
from wickhunter.fyers_paper import FyersPaperPipeline
from wickhunter.ledger import TradeLedger
from wickhunter.paper import PaperBroker
from wickhunter.risk import RiskState
from wickhunter.safety import KillSwitch

IST = ZoneInfo("Asia/Kolkata")


def at(h, m, s=0):
    return datetime(2026, 9, 24, h, m, s, tzinfo=IST)


def make_pipeline(tmp_path):
    ledger = TradeLedger(tmp_path / "paper.jsonl")
    state = RiskState(starting_equity=100_000, equity=100_000)
    switch = KillSwitch(ledger)
    broker = PaperBroker(state, ledger=ledger, kill_switch=switch)
    pipeline = FyersPaperPipeline(
        symbol="NSE:RELIANCE-EQ", initial_pdl=100, initial_pdh=110,
        broker=broker, ledger=ledger, kill_switch=switch,
    )
    return pipeline, ledger, broker


def arm_pipeline(pipeline):
    pipeline.on_candle(M1Candle(at(9, 15), 100.5, 100.8, 99, 99.5, 0))
    pipeline.on_candle(M1Candle(at(9, 16), 99.5, 101, 99, 100.5, 0))
    assert pipeline.armed is not None
    assert pipeline.armed.trigger == 101
    assert pipeline.armed.order_time == at(9, 17)


class FakeStream:
    def __init__(self, *, symbol, on_tick):
        self.symbol = symbol
        self.on_tick = on_tick

    def connect(self):
        pass

    def close(self):
        pass


def fyers_message(timestamp, price, volume):
    return {
        "type": "sf", "symbol": "NSE:RELIANCE-EQ", "ltp": price,
        "exch_feed_time": timestamp.timestamp(), "vol_traded_today": volume,
    }


def test_fyers_stream_to_strategy_to_paper_fill_end_to_end(tmp_path):
    pipeline, ledger, broker = make_pipeline(tmp_path)
    pipeline.stream.stream_factory = FakeStream
    pipeline.connect()
    emit = pipeline.stream.stream.on_tick
    emit(fyers_message(at(9, 15, 1), 99.0, 1000))
    emit(fyers_message(at(9, 15, 30), 99.5, 1005))
    emit(fyers_message(at(9, 16, 1), 100.5, 1010))
    emit(fyers_message(at(9, 16, 10), 99.8, 1012))
    emit(fyers_message(at(9, 16, 30), 101.2, 1018))
    emit(fyers_message(at(9, 16, 55), 100.8, 1020))
    # This tick completes the signal candle first, arming the trigger before
    # the same rollover tick is forwarded to the execution callback.
    emit(fyers_message(at(9, 17), 100.5, 1025))
    assert pipeline.armed is not None
    emit(fyers_message(at(9, 17, 1), 101.2, 1027))
    assert broker.position is not None
    assert broker.position.entry == 101.2
    assert pipeline.engine.state == State.POSITION_OPEN
    assert ledger.snapshot()["open_position"] is not None


def test_fyers_pipeline_arms_and_paper_fills_only_on_confirmation_tick(tmp_path):
    pipeline, ledger, broker = make_pipeline(tmp_path)
    arm_pipeline(pipeline)

    assert pipeline.on_tick(MarketTick(at(9, 17), 100.5, 1000)) is None
    assert broker.position is None
    position = pipeline.on_tick(MarketTick(at(9, 17, 1), 101, 1001))
    assert position is not None
    assert broker.position is not None
    assert pipeline.engine.state == State.POSITION_OPEN
    events = [event.event for event in ledger.events()]
    assert events.count("BUY_INTENT") == 1
    assert events.count("BUY_FILLED") == 1
    assert events.count("PAPER_BUY_ACK") == 1


def test_first_confirmation_minute_tick_can_trigger_buy(tmp_path):
    pipeline, ledger, broker = make_pipeline(tmp_path)
    arm_pipeline(pipeline)

    position = pipeline.on_tick(MarketTick(at(9, 17), 101, 1000))
    assert position is not None
    assert broker.position is not None
    assert pipeline.engine.state == State.POSITION_OPEN


def test_fyers_pipeline_processes_tick_stop_and_closes_ledger_position(tmp_path):
    pipeline, ledger, broker = make_pipeline(tmp_path)
    arm_pipeline(pipeline)
    pipeline.on_tick(MarketTick(at(9, 17, 1), 101, 1001))

    close = pipeline.on_tick(MarketTick(at(9, 17, 2), 98, 1002))
    assert close is not None
    assert close.result == "LOSS"
    assert broker.position is None
    assert ledger.snapshot()["open_position"] is None
    assert pipeline.engine.state == State.DONE


def test_fyers_pipeline_expires_untriggered_buy_after_confirmation_minute(tmp_path):
    pipeline, ledger, broker = make_pipeline(tmp_path)
    arm_pipeline(pipeline)
    pipeline.on_tick(MarketTick(at(9, 17, 1), 100.5, 1001))
    pipeline.on_candle(M1Candle(at(9, 17), 100.5, 100.8, 100.2, 100.6, 0))
    assert pipeline.armed is None
    assert pipeline.engine.state == State.DONE
    assert broker.position is None
    assert ledger.snapshot()["pending_buy"] is None
    assert ledger.latest("BUY_CANCELLED") is not None


def test_fyers_pipeline_recovers_pending_buy_from_durable_ledger(tmp_path):
    first, ledger, _ = make_pipeline(tmp_path)
    arm_pipeline(first)

    state = RiskState(starting_equity=100_000, equity=100_000)
    restarted_broker = PaperBroker(state, ledger=ledger, kill_switch=KillSwitch(ledger))
    restarted = FyersPaperPipeline(
        symbol="NSE:RELIANCE-EQ", initial_pdl=100, initial_pdh=110,
        broker=restarted_broker, ledger=ledger, kill_switch=KillSwitch(ledger),
    )
    restarted.recover()
    assert restarted.armed is not None
    assert restarted.armed.client_order_id == first.armed.client_order_id
    assert restarted.armed.trigger == first.armed.trigger
