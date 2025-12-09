from src.sizer import PositionSize, Sizer


def test_sizer_uses_percent_and_respects_min_contracts():
    sizer = Sizer(portfolio_value=50000, risk_pct=1.0, stop_buffer_pct=0.001)
    result = sizer.contracts_for_trade(premium=2.5, stop_distance=9.5, entry_price=10.5)
    assert isinstance(result, PositionSize)
    assert result.contracts > 0


def test_sizer_rejects_when_risk_too_high():
    sizer = Sizer(portfolio_value=1000, risk_pct=0.5, stop_buffer_pct=0.0)
    result = sizer.contracts_for_trade(premium=5.0, stop_distance=9.9, entry_price=10.0)
    assert result is None
