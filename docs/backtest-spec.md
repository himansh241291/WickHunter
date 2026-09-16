# WickHunter Backtest Specification v0.1

## Objective

Determine whether the deterministic WickHunter long-only setup has measurable historical expectancy before adding complexity or optimization.

## Required data

- M1 OHLC data.
- Previous-day OHLC derived from the same source/session definition.
- Spread data where available.
- Tick data is preferred for execution-sensitive validation.

## Test phases

### Phase A — Baseline

Run exactly the v0.1 rulebook without optimization.

### Phase B — Sensitivity

Vary one parameter at a time, especially:

- Sweep depth normalization
- Signal body threshold
- Reclaim requirement
- Confirmation window
- Stop buffer
- Minimum reward/risk
- Session windows

### Phase C — Out-of-sample

Reserve unseen historical periods before optimization. Do not tune against the final evaluation period.

### Phase D — Forward test

Run the frozen candidate in paper/demo mode with real-time spreads and execution behavior.

## Metrics

Record at minimum:

- Total trades
- Win rate
- Gross profit/loss
- Net profit/loss after costs
- Profit factor
- Expectancy per trade
- Average win
- Average loss
- Maximum drawdown
- Maximum consecutive losses
- Average holding time
- Return on risk
- Trades by session
- Trades by sweep depth bucket
- Trades by reward/risk bucket

## Required robustness checks

- Spread sensitivity
- Slippage sensitivity
- Different symbols
- Different market regimes
- Different date ranges
- Parameter perturbation
- Out-of-sample validation

## Execution realism

A backtest must not enter at SignalHigh merely because historical OHLC shows that the High was crossed. It must model the available bar/tick sequence and transaction costs as closely as the available data permits.

### Current OHLC execution model

The signal candle is the completed reversal candle. The immediately following candle is the only confirmation candle. If its High reaches SignalHigh, the backtester records a long entry at SignalHigh plus configured positive slippage, subject to the candle High being sufficient to fill that price.

Exit evaluation starts on the candle after the entry candle. This is intentional: with OHLC-only data, the order of an entry trigger and a stop/target touch inside the same minute cannot be established. The model therefore does not invent an intrabar sequence. On later candles, if both SL and TP are touched, SL is resolved first as the deterministic conservative policy.

A tick-level execution model will be added as a separate adapter so the strategy rules remain unchanged.

## Data integrity

- Timestamps must be timezone-aware.
- Candles are processed chronologically.
- Duplicate timestamps are rejected.
- Session boundaries are derived from an explicit IANA timezone.
- PDH/PDL for a session come only from the immediately preceding available completed session.
- The current session's candles are never used to construct its own PDH/PDL.

## Research principle

Do not optimize for maximum historical net profit. Prefer stable behavior across nearby parameter values and unseen periods.
