"""Leakage-safe walk-forward evaluation for WickHunter research."""

from dataclasses import dataclass
from typing import Iterable

from .backtest import DailyLevels, WickHunterBacktester
from .metrics import summarize
from .models import Candle
from .research import ResearchCase


@dataclass(frozen=True)
class WalkForwardWindow:
    """A chronological train/test split identified by session names."""

    name: str
    train_sessions: tuple[str, ...]
    test_sessions: tuple[str, ...]


@dataclass(frozen=True)
class WalkForwardResult:
    window: str
    case: str
    train_metrics: dict
    test_metrics: dict


def make_rolling_windows(
    session_names: Iterable[str],
    train_size: int,
    test_size: int,
    step: int | None = None,
) -> list[WalkForwardWindow]:
    """Create chronological, non-leaking rolling train/test windows.

    ``train_size`` and ``test_size`` are counts of completed trading sessions.
    The default step advances by one test block. No session appears in both
    train and test within a window.
    """
    names = tuple(sorted(session_names))
    if train_size < 1 or test_size < 1:
        raise ValueError("train_size and test_size must be >= 1")
    if step is None:
        step = test_size
    if step < 1:
        raise ValueError("step must be >= 1")

    windows: list[WalkForwardWindow] = []
    start = 0
    index = 1
    while start + train_size + test_size <= len(names):
        train = names[start : start + train_size]
        test = names[start + train_size : start + train_size + test_size]
        windows.append(WalkForwardWindow(f"WF{index:03d}", train, test))
        start += step
        index += 1
    return windows


def _subset(
    sessions: dict[str, Iterable[Candle]],
    levels: dict[str, DailyLevels],
    names: tuple[str, ...],
):
    selected_sessions = {name: sessions[name] for name in names if name in sessions}
    selected_levels = {name: levels[name] for name in names if name in levels}
    return selected_sessions, selected_levels


def run_walk_forward(
    sessions: dict[str, Iterable[Candle]],
    levels: dict[str, DailyLevels],
    cases: Iterable[ResearchCase],
    windows: Iterable[WalkForwardWindow],
) -> list[WalkForwardResult]:
    """Run every fixed research case independently on every train/test split."""
    cases = tuple(cases)
    results: list[WalkForwardResult] = []
    for window in windows:
        train_sessions, train_levels = _subset(sessions, levels, window.train_sessions)
        test_sessions, test_levels = _subset(sessions, levels, window.test_sessions)
        for case in cases:
            train_result = WickHunterBacktester(case.config).run(train_sessions, train_levels)
            test_result = WickHunterBacktester(case.config).run(test_sessions, test_levels)
            results.append(
                WalkForwardResult(
                    window=window.name,
                    case=case.name,
                    train_metrics=summarize(train_result),
                    test_metrics=summarize(test_result),
                )
            )
    return results
