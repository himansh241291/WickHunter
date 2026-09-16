"""Dependency-free research harness for WickHunter parameter studies.

The harness intentionally evaluates fixed parameter grids rather than performing
an optimizer. Every run remains BUY-only and independently reproducible.
"""

from dataclasses import dataclass
from typing import Iterable

from .backtest import BacktestConfig, BacktestResult, DailyLevels, WickHunterBacktester
from .metrics import summarize
from .models import Candle


@dataclass(frozen=True)
class ResearchCase:
    name: str
    config: BacktestConfig


@dataclass(frozen=True)
class ResearchResult:
    name: str
    metrics: dict[str, float]


def run_cases(
    sessions: dict[str, Iterable[Candle]],
    levels: dict[str, DailyLevels],
    cases: Iterable[ResearchCase],
) -> list[ResearchResult]:
    """Run each case independently against identical market data."""
    results: list[ResearchResult] = []
    for case in cases:
        result: BacktestResult = WickHunterBacktester(case.config).run(sessions, levels)
        results.append(ResearchResult(case.name, summarize(result)))
    return results


def sensitivity_cases(
    *,
    starting_equity: float = 100_000.0,
    risk_fraction: float = 0.01,
    minimum_rr_values: Iterable[float] = (1.5, 2.0, 2.5),
    stop_buffers: Iterable[float] = (0.0,),
    slippages: Iterable[float] = (0.0,),
) -> list[ResearchCase]:
    """Build a transparent one-/few-parameter sensitivity grid.

    This is a research matrix, not an optimization objective. The caller can
    compare stability across nearby assumptions and later separate in-sample
    from out-of-sample periods.
    """
    cases: list[ResearchCase] = []
    for rr in minimum_rr_values:
        for buffer in stop_buffers:
            for slippage in slippages:
                name = f"rr={rr:g}|buffer={buffer:g}|slippage={slippage:g}"
                cases.append(
                    ResearchCase(
                        name=name,
                        config=BacktestConfig(
                            starting_equity=starting_equity,
                            risk_fraction=risk_fraction,
                            minimum_reward_risk=rr,
                            stop_buffer=buffer,
                            slippage=slippage,
                        ),
                    )
                )
    return cases
