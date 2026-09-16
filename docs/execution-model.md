# WickHunter Execution Model v0.1

## Purpose

The strategy rules and the execution model are separate. This prevents a
backtest from silently changing the setup when transaction-cost assumptions
change.

## BUY entry

The strategy emits a SignalHigh trigger. In the current OHLC backtester, the
confirmation candle must reach that trigger. Entry slippage is then applied as
an adverse price adjustment to the BUY execution.

Because OHLC data cannot establish the intrabar ordering of the confirmation
candle, stop/target evaluation starts on the next candle.

## Long exit

For a long position:

- Stop is evaluated at the configured stop price.
- Target is evaluated at the configured target price.
- If both are touched in the same OHLC candle, the baseline model resolves the
  stop first. This is deliberately conservative and must not be interpreted as
  the true tick sequence.
- Exit slippage reduces the executable long-exit price.

## Costs

Commission can be configured as a per-unit round trip cost. The execution
module applies it to both entry and exit.

## Session boundary

An open position is liquidated at the final candle close by default. This is a
research convention for producing a finite daily result, not a claim about
live-market execution.

## Tick-level upgrade path

When tick data is available, the execution layer should replace OHLC ambiguity
with the observed sequence of prices. The signal rules must remain unchanged.
