from dataclasses import dataclass
from typing import Optional


@dataclass
class PositionSize:
    contracts: int
    notional: float
    hard_stop_price: float


class Sizer:
    def __init__(self, account_equity: float, portfolio_alloc_pct: float, option_hard_stop_pct: float):
        if account_equity <= 0:
            raise ValueError("account_equity must be positive")
        if portfolio_alloc_pct <= 0:
            raise ValueError("portfolio_alloc_pct must be positive")
        if option_hard_stop_pct <= 0:
            raise ValueError("option_hard_stop_pct must be positive")

        self.account_equity = account_equity
        self.portfolio_alloc_pct = (
            portfolio_alloc_pct if portfolio_alloc_pct <= 1 else portfolio_alloc_pct / 100.0
        )
        self.option_hard_stop_pct = (
            option_hard_stop_pct if option_hard_stop_pct <= 1 else option_hard_stop_pct / 100.0
        )

    def contracts_for_trade(self, ask: float, entry_opt_price: float) -> Optional[PositionSize]:
        if ask <= 0 or entry_opt_price <= 0:
            return None

        alloc_dollars = self.account_equity * self.portfolio_alloc_pct
        cost_per_contract = ask * 100
        contracts = int(alloc_dollars // cost_per_contract)
        if contracts < 1:
            return None

        notional = contracts * cost_per_contract
        hard_stop_price = entry_opt_price * (1 - self.option_hard_stop_pct)
        return PositionSize(contracts=contracts, notional=notional, hard_stop_price=hard_stop_price)
