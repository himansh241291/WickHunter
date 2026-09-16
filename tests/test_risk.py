from wickhunter.risk import BuyRiskGuard, RiskLimits, RiskState


def test_buy_risk_sizes_from_stop_distance():
    state = RiskState(starting_equity=100_000, equity=100_000)
    decision = BuyRiskGuard(RiskLimits(max_risk_fraction=0.01)).check_buy(
        state, entry=101, stop=99, requested_risk_fraction=0.01
    )
    assert decision.allowed
    assert decision.quantity == 500


def test_buy_risk_enforces_daily_trade_limit():
    state = RiskState(starting_equity=100_000, equity=100_000, trades_today=1)
    decision = BuyRiskGuard(RiskLimits(max_trades_per_day=1)).check_buy(
        state, entry=101, stop=99, requested_risk_fraction=0.01
    )
    assert not decision.allowed
    assert decision.reason == "max_trades_per_day"


def test_buy_risk_enforces_spread_slippage_and_loss_limits():
    limits = RiskLimits(
        max_spread=0.2, max_slippage=0.1,
        max_daily_loss_fraction=0.02, max_consecutive_losses=2,
    )
    guard = BuyRiskGuard(limits)
    state = RiskState(starting_equity=100_000, equity=98_000, daily_pnl=-2_000)
    assert guard.check_buy(state, entry=101, stop=99, requested_risk_fraction=0.01).reason == "max_daily_loss"
    state.daily_pnl = 0
    state.consecutive_losses = 2
    assert guard.check_buy(state, entry=101, stop=99, requested_risk_fraction=0.01).reason == "max_consecutive_losses"
    state.consecutive_losses = 0
    assert guard.check_buy(state, entry=101, stop=99, requested_risk_fraction=0.01, spread=0.3).reason == "max_spread"
    assert guard.check_buy(state, entry=101, stop=99, requested_risk_fraction=0.01, expected_slippage=0.2).reason == "max_slippage"
