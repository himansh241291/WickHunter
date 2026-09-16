# WickHunter Research Harness

The research harness runs predefined configurations against the same dataset so parameter sensitivity can be measured without changing the strategy implementation.

## Principles

- Baseline v0.1 is always retained.
- Change one assumption at a time where practical.
- Keep in-sample and out-of-sample data separated.
- Record transaction-cost assumptions with every run.
- Do not optimize solely for maximum historical profit.
- Prefer parameter stability across nearby values and unseen periods.

## Current matrix

`wickhunter.research.sensitivity_cases()` generates a small transparent matrix across:

- minimum reward/risk
- stop buffer
- entry slippage

Each case is independently backtested and summarized.

## Next research stages

1. Baseline historical run.
2. Cost sensitivity.
3. RR sensitivity.
4. Stop-buffer sensitivity.
5. Sweep-depth segmentation.
6. Session/time segmentation.
7. Walk-forward train/test split.
8. Fully unseen out-of-sample validation.
9. Paper-trading observation before any live execution work.

No research stage introduces SELL entries.
