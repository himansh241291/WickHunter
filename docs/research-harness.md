# WickHunter Research Harness

The research harness runs predefined configurations against identical datasets so parameter sensitivity can be measured without changing the strategy implementation.

## Principles

- Baseline v0.1 is always retained.
- Change one assumption at a time where practical.
- Keep in-sample and out-of-sample data separated.
- Record transaction-cost assumptions with every run.
- Do not optimize solely for maximum historical profit.
- Prefer parameter stability across nearby values and unseen periods.
- Every result is reproducible from the input CSV and explicit configuration.

## Current matrix

`wickhunter.research.sensitivity_cases()` generates a transparent matrix across:

- minimum reward/risk
- stop buffer
- entry slippage
- exit slippage
- commission per unit

Each case is independently backtested and summarized.

## Walk-forward evaluation

`wickhunter.walkforward.make_rolling_windows()` creates chronological windows:

```text
TRAIN TRAIN TRAIN TRAIN | TEST TEST
                    ->
       TRAIN TRAIN TRAIN TRAIN | TEST TEST
```

A session cannot be in both train and test for the same window. `run_walk_forward()` evaluates every fixed research case independently on both partitions and returns both metric sets. The framework deliberately does not silently select a parameter set based on test performance.

CLI example:

```bash
wickhunter research --data data/m1.csv --timezone Asia/Kolkata \
  --train-size 60 --test-size 20 --step 20 \
  --rr-values 1.5,2.0,2.5 --stop-buffers 0,0.05 \
  --entry-slippages 0,0.02 --exit-slippages 0,0.02 \
  --commissions 0,0.01 --output-dir reports/walkforward
```

## Research stages

1. Baseline historical run.
2. Cost sensitivity.
3. RR sensitivity.
4. Stop-buffer sensitivity.
5. Sweep-depth segmentation.
6. Session/time segmentation.
7. Walk-forward train/test evaluation.
8. Fully unseen out-of-sample validation.
9. Paper-trading observation before any live execution work.

No research stage introduces SELL entries.
