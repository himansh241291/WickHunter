#!/usr/bin/env python3
"""Run WickHunter against FYERS market data with paper execution only."""
from __future__ import annotations

import argparse
import signal
import threading
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from wickhunter.fyers_paper import FyersPaperPipeline
from wickhunter.ledger import TradeLedger
from wickhunter.paper import PaperBroker
from wickhunter.risk import BuyRiskGuard, RiskLimits
from wickhunter.safety import KillSwitch, recover_risk_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WickHunter FYERS paper trader (no live orders)")
    parser.add_argument("--symbol", required=True, help="FYERS symbol, e.g. NSE:RELIANCE-EQ")
    parser.add_argument("--pdl", type=float, required=True, help="previous completed session low")
    parser.add_argument("--pdh", type=float, required=True, help="previous completed session high")
    parser.add_argument("--ledger", default="reports/fyers-paper-ledger.jsonl")
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--starting-equity", type=float, default=100_000.0)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--max-risk-fraction", type=float, default=0.01)
    parser.add_argument("--max-trades-per-day", type=int, default=1)
    parser.add_argument("--max-daily-loss-fraction", type=float, default=None)
    parser.add_argument("--max-consecutive-losses", type=int, default=None)
    parser.add_argument("--max-spread", type=float, default=None)
    parser.add_argument("--max-slippage", type=float, default=None)
    parser.add_argument("--stale-seconds", type=float, default=5.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    zone = ZoneInfo(args.timezone)
    ledger = TradeLedger(Path(args.ledger))
    now = datetime.now(zone)
    state = recover_risk_state(
        ledger, starting_equity=args.starting_equity, as_of=now,
        timezone_name=args.timezone,
    )
    limits = RiskLimits(
        max_risk_fraction=args.max_risk_fraction,
        max_trades_per_day=args.max_trades_per_day,
        max_daily_loss_fraction=args.max_daily_loss_fraction,
        max_consecutive_losses=args.max_consecutive_losses,
        max_spread=args.max_spread,
        max_slippage=args.max_slippage,
    )
    kill_switch = KillSwitch(ledger)
    broker = PaperBroker(
        state, risk_guard=BuyRiskGuard(limits), ledger=ledger, kill_switch=kill_switch,
    )
    pipeline = FyersPaperPipeline(
        symbol=args.symbol, initial_pdl=args.pdl, initial_pdh=args.pdh,
        broker=broker, ledger=ledger, risk_fraction=args.risk_fraction,
        timezone_name=args.timezone,
        feed_health=None,
        kill_switch=kill_switch,
    )
    pipeline.feed_health.max_age = timedelta(seconds=args.stale_seconds)
    pipeline.recover()

    stop = threading.Event()
    failure: list[BaseException] = []

    def connect_stream() -> None:
        try:
            pipeline.connect()
        except BaseException as exc:  # surface connection failures to the main thread
            failure.append(exc)
            stop.set()

    def request_stop(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    thread = threading.Thread(target=connect_stream, name="fyers-market-data", daemon=True)
    thread.start()
    print("WickHunter FYERS pipeline started in PAPER-ONLY mode.")
    print(f"Symbol: {args.symbol} | Timezone: {args.timezone} | Ledger: {Path(args.ledger).resolve()}")
    print("No broker order API is invoked by this script. Ctrl+C stops the stream.")
    try:
        while not stop.wait(1.0):
            pipeline.heartbeat(datetime.now(zone))
            if failure:
                raise RuntimeError("FYERS market-data stream failed") from failure[0]
    except KeyboardInterrupt:
        stop.set()
    finally:
        pipeline.close()
        thread.join(timeout=3.0)
    if failure:
        raise RuntimeError("FYERS market-data stream failed") from failure[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
