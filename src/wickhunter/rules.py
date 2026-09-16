"""Pure WickHunter v0.1 strategy rules.

These functions contain no broker/platform code and are therefore portable.
"""

from .models import Candle


def is_bullish_signal(candle: Candle, pdl: float, previous_swept: bool = False) -> bool:
    """Return whether a completed M1 candle qualifies as the v0.1 signal."""
    if not candle.is_bullish:
        return False
    if candle.range <= 0:
        return False
    if candle.body / candle.range < 0.20:
        return False
    if candle.close_location < 0.50:
        return False
    if candle.close <= pdl:
        return False
    if not (candle.low <= pdl or previous_swept):
        return False
    return True


def reward_risk(entry: float, stop: float, target: float) -> float:
    """Long-only reward/risk ratio."""
    risk = entry - stop
    reward = target - entry
    if risk <= 0:
        return 0.0
    return reward / risk


def valid_long_geometry(entry: float, stop: float, target: float, minimum_rr: float) -> bool:
    """Check long trade geometry without placing an order."""
    if stop >= entry:
        return False
    if target <= entry:
        return False
    return reward_risk(entry, stop, target) >= minimum_rr
