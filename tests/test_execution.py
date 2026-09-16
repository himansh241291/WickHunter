import pytest

from wickhunter.execution import ExecutionConfig, LongExecutionModel


def test_long_execution_applies_adverse_slippage_and_commission():
    model = LongExecutionModel(
        ExecutionConfig(entry_slippage=0.10, exit_slippage=0.20, commission_per_unit=0.05)
    )
    # Trigger 100 -> executed entry 100.10; exit 105 -> 104.80.
    # Quantity 10; commission = 10 * 0.05 * 2 = 1.0.
    assert model.entry_price(100.0) == pytest.approx(100.10)
    assert model.exit_price(105.0) == pytest.approx(104.80)
    assert model.commission(10.0) == pytest.approx(1.0)
    assert model.net_pnl(100.0, 105.0, 10.0) == pytest.approx(46.0)


def test_execution_costs_reject_negative_values():
    with pytest.raises(ValueError):
        ExecutionConfig(entry_slippage=-0.01)
    with pytest.raises(ValueError):
        ExecutionConfig(exit_slippage=-0.01)
    with pytest.raises(ValueError):
        ExecutionConfig(commission_per_unit=-1.0)


def test_negative_quantity_is_rejected():
    model = LongExecutionModel()
    with pytest.raises(ValueError):
        model.commission(-1)
    with pytest.raises(ValueError):
        model.net_pnl(100, 101, -1)
