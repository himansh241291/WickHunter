"""Performance metrics for WickHunter backtest results."""

from .backtest import BacktestResult


def summarize(result: BacktestResult) -> dict[str, float]:
    pnls = [trade.pnl for trade in result.trades]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    equity = result.starting_equity
    peak = equity
    max_drawdown = 0.0
    max_consecutive_losses = 0
    consecutive_losses = 0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        if pnl < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0

    average_hold_minutes = 0.0
    if result.trades:
        durations = [
            (trade.exit_time - trade.entry_time).total_seconds() / 60
            for trade in result.trades
            if hasattr(trade.exit_time, "__sub__")
        ]
        if durations:
            average_hold_minutes = sum(durations) / len(durations)

    return {
        "starting_equity": result.starting_equity,
        "ending_equity": result.ending_equity,
        "net_pnl": result.ending_equity - result.starting_equity,
        "total_trades": result.total_trades,
        "wins": result.wins,
        "losses": result.losses,
        "session_closes": result.session_closes,
        "win_rate": result.win_rate,
        "profit_factor": gross_profit / gross_loss if gross_loss else float("inf") if gross_profit else 0.0,
        "expectancy_per_trade": sum(pnls) / len(pnls) if pnls else 0.0,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "max_drawdown": max_drawdown,
        "max_consecutive_losses": max_consecutive_losses,
        "average_hold_minutes": average_hold_minutes,
        "rejections": len(result.rejected),
        "audit_events": len(result.audit),
    }
