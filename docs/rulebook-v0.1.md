# WickHunter Rulebook v0.1

This document defines the first deterministic, backtestable baseline. It is intentionally conservative. It is a research specification, not a claim that the strategy has positive expectancy.

## 1. Direction

- Long entries only.
- No short entries anywhere in the implementation.
- A day can contain at most one completed WickHunter trade by default.

## 2. Daily reference

- `PDL` = Low of the previous completed trading day.
- The trading-day boundary is an explicit configuration parameter.
- PDL is frozen after the day starts and never recalculated intraday.
- If a valid previous-day candle cannot be established, that trading day is skipped.

## 3. Execution data

- Signal timeframe: M1.
- Decisions are made from completed M1 candles unless a rule explicitly refers to an intrabar price trigger.
- Entry confirmation is an intrabar break of the signal candle High.
- Backtests must model spread and execution costs rather than assuming fills at ideal mid prices.

## 4. Sweep definition

A downside sweep is created when a completed M1 candle has `Low < PDL`.

For v0.1, there is no arbitrary fixed pip minimum. The raw breach is recorded in price units and normalized metrics are recorded for research. This prevents an untested threshold from being silently baked into the baseline.

The sweep extreme is the lowest price reached below PDL during the active sweep event.

## 5. Sweep event lifecycle

After the first M1 candle with `Low < PDL`:

1. Create a new sweep event.
2. Record sweep start time and sweep low.
3. Continue updating sweep low while price remains in the sweep phase.
4. Look for a bullish reversal signal.
5. If price establishes sustained downside movement without a qualifying signal, invalidate the event.

For v0.1, sustained downside movement is defined as **two consecutive completed M1 candles closing below PDL after the sweep begins without a valid bullish signal**. This is a baseline definition and will be tested rather than assumed optimal.

## 6. Bullish signal candle

A bullish signal candle must satisfy all of the following:

- `Close > Open`.
- The candle occurs after the sweep begins.
- The candle's Low is at or below PDL OR the candle directly follows a candle whose Low was below PDL.
- Candle body is at least 20% of its total High-Low range.
- Close is in the upper 50% of the candle's total range.

Doji-like candles and zero-range candles are invalid signals.

## 7. PDL reclaim

The baseline requires the bullish signal candle to close back **above PDL**.

This makes the setup a sweep-and-reclaim rather than merely a green candle occurring below the level.

## 8. Confirmation

When a valid signal candle closes:

- Store `SignalHigh = signal candle High`.
- Store `SignalLow = signal candle Low`.
- Store the sweep low.
- Enter `LONG_READY`.

The immediate next M1 candle is the only confirmation candle in v0.1.

A long entry occurs when the next candle's traded price breaks `SignalHigh`.

If the next candle closes without breaking SignalHigh, the setup expires.

## 9. Entry

- Direction: BUY.
- Trigger: first executable price at or above SignalHigh after the signal candle closes, subject to spread/slippage/risk controls.
- The signal candle itself cannot trigger its own entry.
- If the market gaps above SignalHigh between ticks, the actual executable price is used and slippage is recorded.

## 10. Stop loss

Baseline stop:

`SL = SweepLow - StopBuffer`

`StopBuffer` is configurable and expressed in points/ticks for the instrument.

If calculated SL is invalid for the broker's minimum stop distance, the trade is rejected rather than silently changing the strategy.

## 11. Target

The baseline target is the previous completed day's High (`PDH`).

`TP = PDH`

A trade is allowed only when the projected reward from actual entry to PDH is positive and meets the configured minimum reward/risk threshold.

The initial research value will be `MinimumRewardRisk = 1.5`.

This means:

`(PDH - Entry) / (Entry - SL) >= 1.5`

## 12. Trade management

Until a separate tested rule is introduced:

- No trailing stop.
- No break-even move.
- No partial close.
- No discretionary exit.
- Position exits only at SL, TP, or an explicit end-of-session rule if enabled.

## 13. Session control

The baseline strategy does not trade continuously across the full 24-hour period. Session windows must be explicitly configured using the selected strategy timezone.

Until instrument-specific testing determines suitable windows, the implementation must expose session start/end as configuration rather than hard-coding a market-specific assumption.

## 14. Risk controls

The execution engine must support:

- Risk percentage per trade.
- Maximum trades per day.
- Maximum daily loss.
- Maximum consecutive losses.
- Maximum spread.
- Maximum slippage.
- Duplicate-sweep protection.

A risk control can block a trade but cannot convert it into a short trade.

## 15. Same-day repeated sweeps

Once a sweep event produces a completed trade, that PDL event is considered consumed.

The baseline allows no second trade from the same sweep event.

A later, clearly separated sweep may be recorded for research, but the default one-trade-per-day control prevents additional live entries.

## 16. End-of-day behavior

Any pending signal is invalidated at the configured trading-day boundary.

Open-position handling at the boundary is configurable; the baseline closes open positions at the configured end-of-session rather than carrying them indefinitely.

## 17. No-lookahead requirement

PDH/PDL values must come only from completed historical data available before the trading day begins.

No future candle, future high/low, future spread, or future volatility measurement may influence an earlier decision.

## 18. Research logging

Every detected setup must be logged, including rejected setups, with:

- Date/time
- Symbol
- PDL/PDH
- Sweep low
- Sweep depth
- Signal OHLC
- Signal body/range metrics
- Entry trigger
- Actual entry
- SL/TP
- Reward/risk
- Spread
- Result
- Rejection reason, if rejected

The goal is to learn which components contribute to expectancy before optimization.

## 19. Explicit non-goals

The following are not part of v0.1:

- Short selling
- Previous-day-high short setup
- RSI/MACD/EMA entry filters
- Machine learning
- News prediction
- Martingale
- Grid trading
- Averaging down
- Unlimited re-entry

## 20. Status

v0.1 is the first deterministic research baseline. Parameters must be validated through out-of-sample testing before being considered production defaults.
