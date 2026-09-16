# Live Runtime Safety

WickHunter separates strategy decisions from broker execution. The live runtime is BUY-only and must treat the append-only ledger as the durable source of lifecycle state.

## Startup

1. Open the ledger.
2. Validate every ledger record; corruption is a hard stop.
3. Recover the open BUY position and risk state.
4. If an open BUY exists, restore it and do not submit another BUY.
5. Recover the kill-switch state.
6. Only then start consuming market data.

## Duplicate-order protection

A restart must never infer that an order is safe to recreate merely because the strategy currently produces the same signal. A persisted `BUY_FILLED` event represents an existing position until a `POSITION_CLOSED` or `SESSION_END` event is recorded.

## Runtime sequence

`completed M1 candle -> BUY trigger armed -> eligible tick -> risk check -> BUY submission -> durable BUY_FILLED -> position monitoring -> durable POSITION_CLOSED`

The confirmation candle is the only candle eligible to trigger the BUY. The runtime must not extend the trigger lifetime.

## Reconciliation

A broker adapter should reconcile its actual long position against the durable ledger before enabling new BUY submissions. Any disagreement is a fail-closed condition and requires explicit operator reconciliation.

No SELL/short strategy path is defined by this project.
