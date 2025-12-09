from src.sizer import PositionSize, Sizer


def test_sizer_allocates_contracts_and_hard_stop():
    sizer = Sizer(account_equity=50000, portfolio_alloc_pct=0.25, option_hard_stop_pct=0.5)
    result = sizer.contracts_for_trade(ask=2.5, entry_opt_price=2.5)

    assert isinstance(result, PositionSize)
    assert result.contracts == 50
    assert result.notional == 12500
    assert result.hard_stop_price == 1.25


def test_sizer_rejects_when_not_enough_buying_power():
    sizer = Sizer(account_equity=1000, portfolio_alloc_pct=0.1, option_hard_stop_pct=0.5)
    result = sizer.contracts_for_trade(ask=5.0, entry_opt_price=5.0)

    assert result is None
