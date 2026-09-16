"""Portable bar-based backtesting engine for WickHunter v0.1."""

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .engine import EngineConfig, WickHunterEngine
from .models import Candle


@dataclass(frozen=True)
class DailyLevels:
    session: str
    pdh: float
    pdl: float


@dataclass(frozen=True)
class BacktestConfig:
    starting_equity: float = 100_000.0
    risk_fraction: float = 0.01
    minimum_reward_risk: float = 1.5
    stop_buffer: float = 0.0
    max_trades_per_day: int = 1
    slippage: float = 0.0


@dataclass(frozen=True)
class BacktestTrade:
    session: str
    entry_time: object
    entry: float
    stop: float
    target: float
    quantity: float
    exit_time: object
    exit_price: float
    result: str
    pnl: float
    r_multiple: float


@dataclass
class BacktestResult:
    starting_equity: float
    ending_equity: float
    trades: list[BacktestTrade] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(t.result == "WIN" for t in self.trades)

    @property
    def losses(self) -> int:
        return sum(t.result == "LOSS" for t in self.trades)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades else 0.0


class WickHunterBacktester:
    """Run one independent WickHunter engine per trading session.

    The caller supplies completed M1 candles grouped by session and the
    previous completed session's PDH/PDL. No future session level is read.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    @staticmethod
    def _resolve_exit(candle: Candle, stop: float, target: float):
        """Resolve an exit from OHLC using a deterministic conservative model."""
        if candle.low <= stop:
            return stop, "LOSS"
        if candle.high >= target:
            return target, "WIN"
        return None, None

    def run(self, sessions: dict[str, Iterable[Candle]], levels: dict[str, DailyLevels]) -> BacktestResult:
        equity = self.config.starting_equity
        result = BacktestResult(equity, equity)

        for session, candles_iter in sessions.items():
            if session not in levels:
                result.rejected.append({"session": session, "reason": "MISSING_PREVIOUS_DAY_LEVELS"})
                continue

            candles = list(candles_iter)
            if not candles:
                continue

            day = levels[session]
            engine = WickHunterEngine(
                pdl=day.pdl,
                pdh=day.pdh,
                config=EngineConfig(
                    minimum_reward_risk=self.config.minimum_reward_risk,
                    stop_buffer=self.config.stop_buffer,
                    max_trades_per_day=self.config.max_trades_per_day,
                ),
            )
            pending = None

            for candle in candles:
                if pending is None:
                    event = engine.on_candle(candle)
                    if event and event["action"] == "BUY":
                        entry = event["entry"] + self.config.slippage
                        stop = event["stop"]
                        target = event["target"]
                        risk_per_unit = entry - stop
                        if risk_per_unit <= 0:
                            result.rejected.append({"session": session, "time": str(candle.time), "reason": "INVALID_STOP"})
                            continue
                        quantity = equity * self.config.risk_fraction / risk_per_unit
                        pending = {
                            "entry_time": candle.time,
                            "entry": entry,
                            "stop": stop,
                            "target": target,
                            "quantity": quantity,
                        }
                        # Entry is triggered intrabar. Therefore this same
                        # confirmation candle may also reach SL/TP afterward.
                        exit_price, exit_result = self._resolve_exit(candle, stop, target)
                        if exit_result:
                            self._record_trade(result, session, pending, candle, exit_price, exit_result, equity)
                            equity += (exit_price - entry) * quantity
                            pending = None
                    continue

                exit_price, exit_result = self._resolve_exit(candle, pending["stop"], pending["target"])
                if exit_result:
                    pnl = (exit_price - pending["entry"]) * pending["quantity"]
                    risk_cash = (pending["entry"] - pending["stop"]) * pending["quantity"]
                    equity += pnl
                    result.trades.append(BacktestTrade(
                        session=session,
                        entry_time=pending["entry_time"],
                        entry=pending["entry"],
                        stop=pending["stop"],
                        target=pending["target"],
                        quantity=pending["quantity"],
                        exit_time=candle.time,
                        exit_price=exit_price,
                        result=exit_result,
                        pnl=pnl,
                        r_multiple=pnl / risk_cash if risk_cash else 0.0,
                    ))
                    pending = None

            if pending is not None:
                result.rejected.append({"session": session, "reason": "OPEN_AT_SESSION_END"})

        result.ending_equity = equity
        return result

    @staticmethod
    def _record_trade(result, session, pending, candle, exit_price, exit_result, equity_before):
        pnl = (exit_price - pending["entry"]) * pending["quantity"]
        risk_cash = (pending["entry"] - pending["stop"]) * pending["quantity"]
        result.trades.append(BacktestTrade(
            session=session,
            entry_time=pending["entry_time"],
            entry=pending["entry"],
            stop=pending["stop"],
            target=pending["target"],
            quantity=pending["quantity"],
            exit_time=candle.time,
            exit_price=exit_price,
            result=exit_result,
            pnl=pnl,
            r_multiple=pnl / risk_cash if risk_cash else 0.0,
        ))
