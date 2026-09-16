# WickHunter Strategy Specification

## 1. Strategy identity

- Name: WickHunter
- Direction: LONG ONLY
- Primary execution timeframe: M1
- Core market concept: downside liquidity sweep followed by bullish reversal and confirmation.

## 2. Reference level

At the start of each trading day, calculate and freeze the **Previous Completed Day Low (PDL)**.

PDL remains fixed for the trading day. The exact trading-day/session timezone must be explicitly configured and must not be inferred from the broker's chart display.

## 3. Long setup concept

A potential long setup begins only after price trades below PDL.

The initial break is treated as a potential liquidity sweep, not an immediate entry.

The system then waits for a qualified bullish reversal candle on M1.

After the signal candle is identified, the entry trigger is its High. A long position is eligible only when price breaks that High within the configured confirmation window.

## 4. Initial state flow

DAY_START -> LEVELS_READY -> WAIT_FOR_LOW_SWEEP -> WAIT_FOR_BULLISH_SIGNAL -> LONG_READY -> LONG_ENTRY -> POSITION_OPEN -> EXIT

There is intentionally no SELL state.

## 5. Design principle

WickHunter must distinguish a temporary downside sweep from sustained acceptance below PDL. The exact quantitative definitions for sweep depth, bullish signal quality, reclaim behavior, confirmation, stop placement, target placement, and session filters will be finalized before production execution code is written.

## 6. Baseline before optimization

The first implementation must remain a transparent baseline. Parameters may be optimized only after a reproducible baseline backtest exists.

## 7. Risk

Position sizing will be risk-based rather than fixed-lot by default. Daily loss limits, maximum trades, spread controls, and duplicate-sweep protection are part of the automated risk layer.
