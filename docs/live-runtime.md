# Live Runtime Safety

WickHunter separates strategy decisions from broker execution. The live runtime is BUY-only and must treat the append-only ledger as the durable source of lifecycle state.

## Startup

The LiveRuntime startup sequence is deliberately fail-closed:

1. Open the ledger.
2. Validate every ledger record; corruption is a hard stop.
3. Recover risk state from the durable event history.
4. Recover the kill-switch state.
5. Reconcile the ledger's long position with the broker.
6. Recover a pending BUY by its stable client order ID; never create a replacement ID.
7. If an existing long is present, reconcile the position monitor.
8. Recover a pending long-close by its stable client order ID.
9. Require a healthy market-data heartbeat before enabling new BUY activity.
10. Only then process M1 candles and eligible ticks.

A stale market-data heartbeat halts **new BUY submissions**. Existing long protection remains broker-side through the submitted stop/target; the heartbeat does not invent a discretionary exit.

## Duplicate-order protection

A restart must never infer that an order is safe to recreate merely because the strategy currently produces the same signal. A persisted `BUY_FILLED` event represents an existing position until a `POSITION_CLOSED` or `SESSION_END` event is recorded.

## Runtime sequence

`completed M1 candle -> BUY trigger armed -> eligible tick -> risk check -> BUY submission -> durable BUY_FILLED -> position monitoring -> durable POSITION_CLOSED`

The confirmation candle is the only candle eligible to trigger the BUY. The runtime must not extend the trigger lifetime.

## Reconciliation

A broker adapter should reconcile its actual long position against the durable ledger before enabling new BUY submissions. Any disagreement is a fail-closed condition and requires explicit operator reconciliation.

No SELL/short strategy path is defined by this project.


## Market-data heartbeat

FeedHealth tracks strictly increasing timezone-aware ticks. A runtime heartbeat must call heartbeat(now) periodically. If no fresh tick is available within the configured maximum age, the runtime enters a fail-closed state and persists the kill switch. A later fresh feed does not silently release that persistent kill switch; explicit operator release is required.

## Existing-position lifecycle

Once a BUY is confirmed, the runtime does not generate another strategy entry. The position monitor reconciles the broker position against the ledger and then evaluates only the defined long exits:

- stop: price at or below SL
- target: price at or above PDH
- session end: explicit session close when neither level fired

When an exit is requested, the broker returns a close receipt and the runtime records POSITION_CLOSED durably. Stop is evaluated before target when a single observed price satisfies both conditions.

A broker adapter must therefore expose an idempotent BUY submission path and a long-position close path. No short-entry path exists.
