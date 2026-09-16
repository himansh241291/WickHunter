"""Performance metrics for WickHunter backtest results."""

from .backtest import BacktestResult


def summarize(result: BacktestResult) -> dict:
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

    durations = []
    for trade in result.trades:
        entry_time = getattr(trade, "entry_time", None)
        exit_time = getattr(trade, "exit_time", None)
        if entry_time is not None and exit_time is not None:
            durations.append((exit_time - entry_time).total_seconds() / 60)

    r_values = [getattr(trade, "r_multiple", 0.0) for trade in result.trades]
    profit_factor = gross_profit / gross_loss if gross_loss else None

    return {
        "starting_equity": result.starting_equity,
        "ending_equity": result.ending_equity,
        "net_pnl": result.ending_equity - result.starting_equity,
        "total_trades": result.total_trades,
        "wins": result.wins,
        "losses": result.losses,
        "session_closes": getattr(result, "session_closes", 0),
        "win_rate": result.win_rate,
        "profit_factor": profit_factor,
        "expectancy_per_trade": sum(pnls) / len(pnls) if pnls else 0.0,
        "average_win": sum(wins) / len(wins) if wins else 0.0,
        "average_loss": sum(losses) / len(losses) if losses else 0.0,
        "max_drawdown": max_drawdown,
        "max_consecutive_losses": max_consecutive_losses,
        "average_hold_minutes": sum(durations) / len(durations) if durations else 0.0,
        "total_r": sum(r_values),
        "average_r": sum(r_values) / len(r_values) if r_values else 0.0,
        "rejections": len(getattr(result, "rejected", [])),
        "audit_events": len(getattr(result, "audit", [])),
    }
