# WickHunter

**WickHunter** is a standalone, portable, BUY-only algorithmic trading research and execution project.

## Strategy

WickHunter is based on a liquidity-sweep / false-breakout reversion concept:

1. Mark the previous completed trading day's Low.
2. Wait for price to sweep below that level.
3. Detect a qualified bullish reversal on M1.
4. Require the reversal candle to reclaim the previous-day Low.
5. Confirm by breaking the reversal candle's High on the immediately following M1 candle.
6. Enter a LONG position.
7. Manage risk using deterministic SL/TP rules.

## Hard constraint: BUY ONLY

WickHunter does **not** contain SELL-entry logic. SELL is not an alternate mode, configuration option, or future strategy branch.

The project is intentionally independent of any other trading project or repository.

## Development philosophy

- Rule-driven and deterministic.
- Backtestable before live automation.
- Portable across execution environments where practical.
- Configuration separated from strategy logic.
- No hidden discretionary assumptions.
- Preserve a baseline strategy before optimization.
- Execution assumptions must be explicit and replaceable.

## Current architecture

```text
CSV / future market-data adapter
              |
              v
       M1 Candle stream
              |
              v
     WickHunter State Machine
              |
       +------+------+
       |             |
     Signal        Reject
       |
       v
    BUY event
       |
       v
  Risk / execution model
       |
       v
   Trade ledger
       |
       v
 Performance metrics
```

The strategy core has no broker SDK dependency. The current OHLC backtester deliberately starts exit evaluation on the candle after the intrabar SignalHigh entry trigger because OHLC bars cannot prove whether a stop or target was touched before or after entry. This avoids fabricating an intrabar sequence. A future tick-level execution model can replace this assumption without changing the signal rules.

## Data format

The dependency-free CSV adapter accepts:

```text
time,open,high,low,close,spread
2026-01-02T09:00:00+00:00,100.5,100.8,99.0,99.5,0.1
```

Timestamps must be timezone-aware. `prepare_sessions()` can group candles by an explicit IANA timezone and derive PDH/PDL from the immediately preceding available completed session without using current/future candles.

## Tests

Run locally:

```bash
python -m pip install -e ".[test]"
pytest -q
```

GitHub Actions runs the test suite on pushes to `main` and pull requests.

## Status

Deterministic v0.1 rulebook + portable strategy engine + backtest engine + session-aware CSV pipeline + unit tests are implemented. Historical validation and execution-realism work are next; no live-trading defaults should be inferred from the current code.
