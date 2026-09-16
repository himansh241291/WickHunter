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

Export strategy-generated BUY intents for tick-level execution:

```bash
wickhunter generate-intents \
  --data data/M1.csv \
  --timezone Asia/Kolkata \
  --output data/buy-intents.json
```

The intent exporter uses the same WickHunter state machine and previous-day levels as the strategy backtester. It emits only approved BUY intents; it does not contain a second signal-generation implementation. Each intent is bounded to the immediate confirmation M1 candle with an `expires_at` timestamp.

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
  --timezone Asia/Kolkata \
  --ledger reports/paper-ledger.jsonl
```

The tick CSV requires `time,price`. Intent JSON is an array containing `time`, `trigger`, `stop`, and `target`, with optional `risk_fraction`, `spread`, and `expires_at`. The replay harness waits for the **first strictly later** ordered tick before expiry that reaches the trigger, and uses the observed tick price for the fill. It does not generate signals.

Paper replay risk controls:

```text
--max-risk-fraction
--max-trades-per-day
--max-daily-loss-fraction
--max-consecutive-losses
--max-spread
--max-slippage
```

The replay `--timezone` must match the session timezone used for strategy intent generation. Daily counters and session boundaries are calculated in that IANA timezone, not from the raw UTC calendar date.

Backtest execution-cost controls:

```text
--entry-slippage / --slippage
--exit-slippage
--commission-per-unit
```

The CLI writes JSON and CSV reports containing metrics, trades, rejections, audit events, and walk-forward train/test results where requested.

## Durable paper-trading safety

Paper execution supports an append-only JSONL ledger with flush+fsync durability, restart inspection, durable risk-state reconstruction, and a persistent kill switch. Before resuming after a process restart, recover the ledger snapshot and risk state and reconcile any open position before accepting a new BUY. An engaged kill switch blocks new BUY entries.

Daily loss limits are measured against equity at the start of the current trading day. A profitable prior day therefore does not distort the next day's percentage loss limit.

## Research discipline

Historical performance is not treated as proof of future profitability. The research harness keeps parameter cases explicit, supports cost sensitivity and rolling train/test evaluation, and does not silently optimize against the test period. Ordered ticks are preferred when intrabar ordering matters.

## Status

The repository currently contains the deterministic strategy engine, session-aware M1 data pipeline, OHLC backtester, execution-cost model, audit ledger, dataset validation, fixed sensitivity research, rolling walk-forward evaluation, BUY-intent exporter, ordered-tick paper replay, risk guardrails, durable recovery state, and persistent kill switch. There is no live-trading default and no SELL-entry implementation.
