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
    liquidate_at_session_end: bool = True

    def __post_init__(self) -> None:
        if self.starting_equity <= 0:
            raise ValueError("starting_equity must be positive")
        if not 0 < self.risk_fraction <= 1:
            raise ValueError("risk_fraction must be in (0, 1]")
        if self.minimum_reward_risk <= 0:
            raise ValueError("minimum_reward_risk must be positive")
        if self.stop_buffer < 0 or self.slippage < 0:
            raise ValueError("stop_buffer and slippage cannot be negative")
        if self.max_trades_per_day < 1:
            raise ValueError("max_trades_per_day must be >= 1")


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
    audit: list[dict] = field(default_factory=list)

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
    def session_closes(self) -> int:
        return sum(t.result == "SESSION_CLOSE" for t in self.trades)

    @property
    def win_rate(self) -> float:
        decided = self.wins + self.losses
        return self.wins / decided if decided else 0.0


class WickHunterBacktester:
    """Run one independent long-only engine per trading session.

    In OHLC mode, exits begin on the candle after entry because bar data
    cannot prove whether a stop/target was reached before or after an
    intrabar SignalHigh entry trigger.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    @staticmethod
    def _resolve_exit(candle: Candle, stop: float, target: float):
        """Resolve an exit from OHLC using deterministic stop-first ordering."""
        if candle.low <= stop:
            return stop, "LOSS"
        if candle.high >= target:
            return target, "WIN"
        return None, None

    @staticmethod
    def _audit(result: BacktestResult, session: str, candle: Candle, event: str, **details) -> None:
        row = {"session": session, "time": str(candle.time), "event": event}
        row.update(details)
        result.audit.append(row)

    def run(self, sessions: dict[str, Iterable[Candle]], levels: dict[str, DailyLevels]) -> BacktestResult:
        equity = self.config.starting_equity
        result = BacktestResult(equity, equity)

        for session in sorted(sessions):
            candles = list(sessions[session])
            if session not in levels:
                result.rejected.append({"session": session, "reason": "MISSING_PREVIOUS_DAY_LEVELS"})
                continue
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
                if pending is not None:
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
                        self._audit(result, session, candle, "EXIT", result=exit_result, price=exit_price)
                        pending = None
                    continue

                event = engine.on_candle(candle)
                if not event or event.get("action") != "BUY":
                    continue

                entry = event["entry"] + self.config.slippage
                if candle.high < entry:
                    result.rejected.append({
                        "session": session,
                        "time": str(candle.time),
                        "reason": "ENTRY_NOT_FILLED_SLIPPAGE",
                    })
                    self._audit(result, session, candle, "REJECT", reason="ENTRY_NOT_FILLED_SLIPPAGE")
                    continue

                stop = event["stop"]
                target = event["target"]
                risk_per_unit = entry - stop
                if risk_per_unit <= 0:
                    result.rejected.append({"session": session, "time": str(candle.time), "reason": "INVALID_STOP"})
                    self._audit(result, session, candle, "REJECT", reason="INVALID_STOP")
                    continue

                quantity = equity * self.config.risk_fraction / risk_per_unit
                pending = {
                    "entry_time": candle.time,
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "quantity": quantity,
                }
                self._audit(
                    result, session, candle, "BUY",
                    entry=entry, stop=stop, target=target,
                    signal_time=str(event["signal_time"]),
                    confirmation_time=str(event["confirmation_time"]),
                )
                # Do not inspect the confirmation candle for exits: OHLC
                # cannot establish whether its low/high occurred before or
                # after the intrabar SignalHigh entry trigger.

            if pending is not None:
                if self.config.liquidate_at_session_end:
                    last = candles[-1]
                    exit_price = last.close
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
                        exit_time=last.time,
                        exit_price=exit_price,
                        result="SESSION_CLOSE",
                        pnl=pnl,
                        r_multiple=pnl / risk_cash if risk_cash else 0.0,
                    ))
                    self._audit(result, session, last, "EXIT", result="SESSION_CLOSE", price=exit_price)
                else:
                    result.rejected.append({"session": session, "reason": "OPEN_AT_SESSION_END"})

        result.ending_equity = equity
        return result
