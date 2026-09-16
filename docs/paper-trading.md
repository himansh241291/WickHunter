# WickHunter paper-trading layer

WickHunter keeps strategy decisions separate from execution and account risk. The paper layer is deterministic, broker-neutral, and BUY-entry only.

## Flow

1. The strategy engine emits a valid BUY trigger after the PDL sweep, bullish reclaim signal, and immediate SignalHigh confirmation.
2. `BuyRiskGuard` checks stop geometry, requested risk, trades per day, daily loss, consecutive losses, spread, and expected slippage.
3. `PaperBroker.submit_buy()` creates one simulated long position using the configured adverse entry execution cost.
4. Ordered ticks are processed while the position is open. The first observed stop or target threshold closes the position.
5. Session-end liquidation is available as an explicit deterministic lifecycle rule.
6. Gross P&L, round-trip commission, net P&L, equity, daily P&L, consecutive losses, and audit events are updated.

## Safety properties

- There is no short-entry method.
- There is no mirrored SELL strategy path.
- Only one simulated position may be open at a time.
- A rejected risk check cannot silently resize beyond the configured maximum risk fraction.
- Daily and consecutive-loss limits block new BUY entries rather than altering an existing strategy signal.
- Execution costs are explicit and adverse to the simulated long position.

## Broker-neutral boundary

`PaperBroker` intentionally contains no broker SDK, credentials, network calls, or live-order side effects. A future market-data/broker adapter can translate external events into WickHunter candles/ticks and translate approved BUY requests into a provider-specific API without changing the strategy rulebook.

Live execution must remain opt-in. Paper mode is the default development and validation path.
