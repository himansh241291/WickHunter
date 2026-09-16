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
- Separate train/test periods to reduce research leakage.

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
   Trade ledger + audit
       |
       v
 Performance metrics
       |
       v
 Research / Walk-forward reports
```

The strategy core has no broker SDK dependency. The current OHLC backtester deliberately starts exit evaluation on the candle after the intrabar SignalHigh entry trigger because OHLC bars cannot prove whether a stop or target was touched before or after entry. The baseline also liquidates an open position at the session's final close rather than carrying it into another session. Ordered tick execution removes this intrabar ordering ambiguity where tick data is available.

Execution costs are explicit: entry slippage, exit slippage, and per-unit commission. Exit ambiguity is deterministic stop-first for the baseline OHLC model.

## CLI

Install the project and test dependencies:

```bash
python -m pip install -e ".[test]"
```

Run a backtest:

```bash
wickhunter backtest --data data/M1.csv --timezone Asia/Kolkata --output-dir reports
```

Run dataset validation:

```bash
wickhunter validate --data data/M1.csv --timezone Asia/Kolkata
```

Run a fixed research matrix:

```bash
wickhunter research --data data/M1.csv --timezone Asia/Kolkata \
  --rr-values 1.5,2.0,2.5 \
  --entry-slippages 0,0.02 --exit-slippages 0,0.02 \
  --commissions 0,0.01 --output-dir reports/research
```

Run rolling walk-forward evaluation:

```bash
wickhunter research --data data/M1.csv --timezone Asia/Kolkata \
  --train-size 60 --test-size 20 --step 20 \
  --rr-values 1.5,2.0,2.5 --output-dir reports/walkforward
```

Run ordered-tick paper replay from approved BUY intents:

```bash
wickhunter paper-replay \
  --ticks data/ticks.csv \
  --intents data/buy-intents.json \
  --ledger reports/paper-ledger.jsonl
```

The tick CSV requires `time,price`. Intent JSON is an array containing `time`, `trigger`, `stop`, and `target`, with optional `risk_fraction` and `spread`. The replay harness does not generate signals; it executes only already-approved BUY intents.

Backtest execution-cost controls:

```text
--entry-slippage / --slippage
--exit-slippage
--commission-per-unit
```

The CLI writes JSON and CSV reports containing metrics, trades, rejections, audit events, and walk-forward train/test results where requested.

## Durable paper-trading safety

Paper execution supports an append-only JSONL ledger with flush+fsync durability, restart inspection, and a persistent kill switch. Before resuming after a process restart, recover the ledger snapshot and reconcile any open position before accepting a new BUY. An engaged kill switch blocks new BUY entries.

## Data format

The dependency-free CSV adapter accepts:

```text
time,open,high,low,close,spread
2026-01-02T09:00:00+00:00,100.5,100.8,99.0,99.5,0.1
```

Timestamps must be timezone-aware. `prepare_sessions()` groups candles by an explicit IANA timezone and derives PDH/PDL from the immediately preceding available completed session without using current/future candles.

The validator reports same-date M1 gaps separately from expected overnight/session-boundary gaps. Use `--strict` when continuity gaps should cause validation failure.

## Research discipline

The research harness evaluates fixed parameter cases rather than silently optimizing against historical profit. Walk-forward evaluation keeps chronological train/test partitions disjoint and reports both independently. The framework does not select a configuration from test results.

Historical performance is not implied by the unit-test fixtures; real market-data validation is required.

## Tests

Run locally:

```bash
pytest -q
```

GitHub Actions runs the test suite on pushes to `main` and pull requests.

## Status

Deterministic v0.1 rulebook + portable strategy engine + session-aware CSV pipeline + execution-cost model + audit ledger + CLI + sensitivity research + rolling walk-forward + ordered-tick execution + paper broker + durable paper ledger/recovery + kill switch + paper replay CLI are implemented. No live-trading defaults should be inferred from the current code.
