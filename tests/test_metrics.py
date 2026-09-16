from types import SimpleNamespace

from wickhunter.metrics import summarize


def test_metrics_basic():
    trades = [
        SimpleNamespace(pnl=100.0, result="WIN"),
        SimpleNamespace(pnl=-50.0, result="LOSS"),
        SimpleNamespace(pnl=25.0, result="WIN"),
    ]
    result = SimpleNamespace(
        starting_equity=1000.0,
        ending_equity=1075.0,
        trades=trades,
        total_trades=3,
        wins=2,
        losses=1,
        win_rate=2 / 3,
    )
    metrics = summarize(result)
    assert metrics["net_pnl"] == 75.0
    assert metrics["profit_factor"] == 2.5
    assert metrics["max_drawdown"] == 50.0
    assert metrics["expectancy_per_trade"] == 25.0
