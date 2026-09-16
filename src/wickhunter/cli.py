"""Command-line interface for reproducible WickHunter research runs."""

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from .backtest import BacktestConfig, WickHunterBacktester
from .data import load_m1_csv, prepare_sessions
from .metrics import summarize
from .research import sensitivity_cases, run_cases
from .replay import load_ticks, replay_buy_intents
from .validation import validate_m1
from .walkforward import make_rolling_windows, run_walk_forward


def _data_args(parser):
    parser.add_argument("--data", required=True, help="M1 CSV path")
    parser.add_argument("--timezone", default="UTC", help="IANA session timezone")


def build_parser():
    parser = argparse.ArgumentParser(prog="wickhunter", description="BUY-only WickHunter research engine")
    sub = parser.add_subparsers(dest="command", required=True)
    backtest = sub.add_parser("backtest", help="run a backtest")
    _data_args(backtest)
    backtest.add_argument("--output-dir", default="reports")
    backtest.add_argument("--starting-equity", type=float, default=100_000.0)
    backtest.add_argument("--risk-fraction", type=float, default=0.01)
    backtest.add_argument("--minimum-rr", type=float, default=1.5)
    backtest.add_argument("--stop-buffer", type=float, default=0.0)
    backtest.add_argument("--entry-slippage", "--slippage", dest="entry_slippage", type=float, default=0.0)
    backtest.add_argument("--exit-slippage", type=float, default=0.0)
    backtest.add_argument("--commission-per-unit", type=float, default=0.0)
    backtest.add_argument("--max-trades-per-day", type=int, default=1)
    backtest.add_argument("--no-session-liquidation", action="store_true")

    validate = sub.add_parser("validate", help="validate an M1 dataset")
    _data_args(validate)
    validate.add_argument("--strict", action="store_true", help="fail on same-date M1 gaps")

    research = sub.add_parser("research", help="run fixed sensitivity or walk-forward research")
    _data_args(research)
    research.add_argument("--output-dir", default="reports/research")
    research.add_argument("--rr-values", default="1.5,2.0,2.5")
    research.add_argument("--stop-buffers", default="0")
    research.add_argument("--entry-slippages", default="0")
    research.add_argument("--exit-slippages", default="0")
    research.add_argument("--commissions", default="0")
    research.add_argument("--starting-equity", type=float, default=100_000.0)
    research.add_argument("--risk-fraction", type=float, default=0.01)
    research.add_argument("--train-size", type=int, default=0)
    research.add_argument("--test-size", type=int, default=0)
    research.add_argument("--step", type=int, default=None)

    replay = sub.add_parser("paper-replay", help="replay approved BUY intents against ordered ticks")
    replay.add_argument("--ticks", required=True, help="tick CSV with time,price columns")
    replay.add_argument("--intents", required=True, help="JSON array of approved BUY intents")
    replay.add_argument("--ledger", default="reports/paper-ledger.jsonl")
    replay.add_argument("--starting-equity", type=float, default=100_000.0)
    replay.add_argument("--risk-fraction", type=float, default=0.01)
    return parser


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _floats(value):
    return tuple(float(x.strip()) for x in value.split(",") if x.strip())


def run_backtest(args):
    candles = load_m1_csv(args.data)
    sessions, levels = prepare_sessions(candles, timezone_name=args.timezone)
    config = BacktestConfig(starting_equity=args.starting_equity, risk_fraction=args.risk_fraction,
        minimum_reward_risk=args.minimum_rr, stop_buffer=args.stop_buffer,
        max_trades_per_day=args.max_trades_per_day, entry_slippage=args.entry_slippage,
        exit_slippage=args.exit_slippage, commission_per_unit=args.commission_per_unit,
        liquidate_at_session_end=not args.no_session_liquidation)
    result = WickHunterBacktester(config).run(sessions, levels)
    metrics = summarize(result)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding="utf-8")
    _write_csv(output / "trades.csv", [asdict(t) for t in result.trades])
    _write_csv(output / "rejected.csv", result.rejected)
    _write_csv(output / "audit.csv", result.audit)
    print(json.dumps(metrics, indent=2, allow_nan=False))
    print(f"Reports written to {output.resolve()}")
    return 0


def run_validate(args):
    report = validate_m1(load_m1_csv(args.data), strict_continuity=args.strict)
    payload = asdict(report) | {"valid": report.valid}
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0 if report.valid else 1


def run_research(args):
    candles = load_m1_csv(args.data)
    sessions, levels = prepare_sessions(candles, timezone_name=args.timezone)
    cases = sensitivity_cases(starting_equity=args.starting_equity, risk_fraction=args.risk_fraction,
        minimum_rr_values=_floats(args.rr_values), stop_buffers=_floats(args.stop_buffers),
        slippages=_floats(args.entry_slippages), exit_slippages=_floats(args.exit_slippages),
        commissions_per_unit=_floats(args.commissions))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if args.train_size and args.test_size:
        windows = make_rolling_windows(sessions.keys(), args.train_size, args.test_size, args.step)
        results = run_walk_forward(sessions, levels, cases, windows)
        payload = [{"window": r.window, "case": r.case, "train": r.train_metrics, "test": r.test_metrics} for r in results]
        (output / "walkforward.json").write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
        _write_csv(output / "walkforward.csv", [{"window": r.window, "case": r.case, "train": json.dumps(r.train_metrics), "test": json.dumps(r.test_metrics)} for r in results])
        print(f"Walk-forward evaluations: {len(results)}")
    else:
        results = run_cases(sessions, levels, cases)
        payload = [{"name": r.name, "metrics": r.metrics} for r in results]
        (output / "research.json").write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
        _write_csv(output / "research.csv", [{"name": r.name, **r.metrics} for r in results])
        print(f"Research cases: {len(results)}")
    print(f"Reports written to {output.resolve()}")
    return 0


def run_paper_replay(args):
    ticks = load_ticks(args.ticks)
    intents = json.loads(Path(args.intents).read_text(encoding="utf-8"))
    if not isinstance(intents, list):
        raise ValueError("intents JSON must be an array")
    ledger = __import__("wickhunter.ledger", fromlist=["TradeLedger"]).TradeLedger(args.ledger)
    state = replay_buy_intents(ticks, intents, starting_equity=args.starting_equity,
        risk_fraction=args.risk_fraction, ledger=ledger)
    print(json.dumps({"starting_equity": args.starting_equity, "equity": state.equity,
                      "net_pnl": state.equity - args.starting_equity,
                      "trades_today": state.trades_today,
                      "consecutive_losses": state.consecutive_losses}, indent=2, allow_nan=False))
    return 0


def main():
    args = build_parser().parse_args()
    if args.command == "backtest": return run_backtest(args)
    if args.command == "validate": return run_validate(args)
    if args.command == "research": return run_research(args)
    if args.command == "paper-replay": return run_paper_replay(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
