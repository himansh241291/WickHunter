# WickHunter Execution Model v0.1

## Purpose

The strategy rules and execution model are separate. This prevents a
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

Commission can be configured as a per-unit round-trip cost. The execution
module applies it once for entry and once for exit.

## Tick-level execution

When ordered tick data is available, `wickhunter.tick` can resolve the first
observed BUY trigger and the first observed stop/target threshold. This removes
the OHLC ambiguity while keeping the strategy signal rules unchanged.

The tick resolver is deliberately a primitive rather than a second strategy:
it contains no indicators, signal generation, short entries, or optimization.

## Session boundary

An open position is liquidated at the final candle close by default. This is a
research convention for producing a finite daily result, not a claim about
live-market execution.
