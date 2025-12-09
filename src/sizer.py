from dataclasses import dataclass
from typing import Optional


@dataclass
class PositionSize:
    contracts: int
    notional: float


class Sizer:
    def __init__(self, portfolio_value: float, risk_pct: float, stop_buffer_pct: float = 0.0):
        self.portfolio_value = portfolio_value
        # Accept either decimal (0.01) or whole percent (1 == 1%).
        if risk_pct <= 0:
            raise ValueError("risk_pct must be positive")
        if risk_pct <= 1:
            self.risk_pct = risk_pct if risk_pct <= 0.05 else risk_pct / 100.0
        else:
            self.risk_pct = risk_pct / 100.0
        self.stop_buffer_pct = stop_buffer_pct

    def contracts_for_trade(self, premium: float, stop_distance: float, entry_price: float) -> Optional[PositionSize]:
        risk_capital = self.portfolio_value * self.risk_pct
        per_contract_risk = max((entry_price - stop_distance) * 100, premium * 100)
        per_contract_risk += entry_price * self.stop_buffer_pct
        if per_contract_risk <= 0:
            return None
        contracts = int(risk_capital // per_contract_risk)
        if contracts < 1:
            return None
        notional = contracts * premium * 100
        return PositionSize(contracts=contracts, notional=notional)
