"""Validation helpers for historical M1 research datasets."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from .models import Candle


@dataclass(frozen=True)
class DatasetReport:
    candles: int
    sessions: int
    duplicates: int
    gaps: int
    max_gap_minutes: float
    timezone_aware: bool
    monotonic: bool
    strict_continuity: bool = False

    @property
    def valid(self) -> bool:
        """Return structural validity; normal session gaps are not failures."""
        return (
            self.candles > 0
            and self.duplicates == 0
            and self.timezone_aware
            and self.monotonic
            and (not self.strict_continuity or self.gaps == 0)
        )


def validate_m1(
    candles: Iterable[Candle],
    *,
    strict_continuity: bool = False,
) -> DatasetReport:
    """Validate timestamps and report intraday M1 continuity gaps.

    Market data normally contains overnight/weekend/session-boundary gaps, so
    gaps are informational by default. ``strict_continuity=True`` is available
    for synthetic datasets or feeds where every consecutive row must be one
    minute apart within a calendar session.
    """
    rows = list(candles)
    if not rows:
        return DatasetReport(0, 0, 0, 0, 0.0, True, True, strict_continuity)

    timestamps = [c.time for c in rows]
    duplicates = len(timestamps) - len(set(timestamps))
    monotonic = all(a < b for a, b in zip(timestamps, timestamps[1:]))
    aware = all(ts.tzinfo is not None and ts.utcoffset() is not None for ts in timestamps)

    gaps = 0
    max_gap = timedelta(0)
    for previous, current in zip(rows, rows[1:]):
        delta = current.time - previous.time
        if previous.time.date() == current.time.date() and delta > timedelta(minutes=1):
            gaps += 1
            max_gap = max(max_gap, delta)

    sessions = len({c.time.date() for c in rows})
    return DatasetReport(
        candles=len(rows),
        sessions=sessions,
        duplicates=duplicates,
        gaps=gaps,
        max_gap_minutes=max_gap.total_seconds() / 60.0,
        timezone_aware=aware,
        monotonic=monotonic,
        strict_continuity=strict_continuity,
    )
