"""Command-line interface for running reproducible WickHunter backtests."""

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from .backtest import BacktestConfig, WickHunterBacktester
from .data import load_m1_csv, prepare_sessions
from .metrics import summarize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wickhunter", description="Run a BUY-only WickHunter backtest")
    sub = parser.add_subparsers(dest="command", required=True)

    backtest = sub.add_parser("backtest", help="run a backtest from M1 CSV data")
    backtest.add_argument("--data", required=True, help="M1 CSV path")
    backtest.add_argument("--timezone", default="UTC", help="IANA session timezone")
    backtest.add_argument("--output-dir", default="reports", help="directory for generated reports")
    backtest.add_argument("--starting-equity", type=float, default=100_000.0)
    backtest.add_argument("--risk-fraction", type=float, default=0.01)
    backtest.add_argument("--minimum-rr", type=float, default=1.5)
    backtest.add_argument("--stop-buffer", type=float, default=0.0)
    backtest.add_argument("--slippage", type=float, default=0.0)
    backtest.add_argument("--max-trades-per-day", type=int, default=1)
    backtest.add_argument("--no-session-liquidation", action="store_true")
    return parser


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_backtest(args: argparse.Namespace) -> int:
    candles = load_m1_csv(args.data)
    sessions, levels = prepare_sessions(candles, timezone_name=args.timezone)
    config = BacktestConfig(
        starting_equity=args.starting_equity,
        risk_fraction=args.risk_fraction,
        minimum_reward_risk=args.minimum_rr,
        stop_buffer=args.stop_buffer,
        max_trades_per_day=args.max_trades_per_day,
        slippage=args.slippage,
        liquidate_at_session_end=not args.no_session_liquidation,
    )
    result = WickHunterBacktester(config).run(sessions, levels)
    metrics = summarize(result)

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding="utf-8")
    _write_csv(output / "trades.csv", [asdict(trade) for trade in result.trades])
    _write_csv(output / "rejected.csv", result.rejected)
    _write_csv(output / "audit.csv", result.audit)

    print(json.dumps(metrics, indent=2, allow_nan=False))
    print(f"Reports written to {output.resolve()}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "backtest":
        return run_backtest(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
