# WickHunter paper-trading layer

WickHunter keeps strategy decisions separate from execution and account risk. The paper layer is deterministic, broker-neutral, and BUY-entry only.

## Flow

1. The strategy engine emits a valid BUY trigger after the PDL sweep, bullish reclaim signal, and immediate SignalHigh confirmation.
2. `BuyRiskGuard` checks stop geometry, requested risk, trades per day, daily loss, consecutive losses, spread, and expected slippage.
3. `PaperBroker.submit_buy()` creates one simulated long position using the configured adverse entry execution cost.
4. Ordered ticks are processed while the position is open. Ticks at or before the fill are ignored; the first later stop or target threshold closes the position.
5. Session-end liquidation is available as an explicit deterministic lifecycle rule.
6. Gross P&L, round-trip commission, net P&L, equity, daily P&L, consecutive losses, and audit events are updated.

## Durable state and kill switch

`TradeLedger` stores append-only JSONL events and uses flush + `fsync` for each write. `TradeLedger.snapshot()` reconstructs whether a BUY position is still open and whether the persistent kill switch is engaged.

On process restart, inspect the snapshot before accepting a new BUY. An unresolved open position must be reconciled before new strategy orders are accepted. An engaged kill switch blocks new BUY entries until explicitly released.

## Safety properties

- There is no short-entry method.
- There is no mirrored SELL strategy path.
- Only one simulated position may be open at a time.
- A rejected risk check cannot silently resize beyond the configured maximum risk fraction.
- Daily and consecutive-loss limits block new BUY entries rather than altering an existing strategy signal.
- Execution costs are explicit and adverse to the simulated long position.
- Corrupt ledger records raise an error rather than silently producing a false recovery state.

## Broker-neutral boundary

`PaperBroker` contains no broker SDK, credentials, network calls, or live-order side effects. A future market-data/broker adapter can translate external events into WickHunter candles/ticks and translate approved BUY requests into a provider-specific API without changing the strategy rulebook.

Live execution must remain opt-in. Paper mode is the development and validation path.
