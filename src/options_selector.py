from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


@dataclass
class OptionContract:
    option_symbol: str
    strike: float
    option_type: str
    expiry: datetime
    delta: float
    ask: float


class OptionsSelector:
    def __init__(self, data_client):
        self.data_client = data_client

    def pick_expiry(self, now: datetime, policy: str) -> datetime:
        policy = policy.lower()
        base_date = now.date()

        if policy == "next_weekly":
            expiry_date = self._next_friday(base_date)
        elif policy == "same_day":
            expiry_date = base_date
        else:
            raise ValueError(f"Unsupported expiry policy: {policy}")

        return datetime.combine(expiry_date, datetime.min.time())

    def pick_strike(
        self,
        underlying_px: float,
        chain: list,
        direction: str,
        target_delta: float,
        fallback: str,
    ) -> Optional[dict]:
        if not chain:
            return None

        desired_type = "call" if direction == "long" else "put"
        filtered = [
            contract
            for contract in chain
            if self._contract_type(contract) == desired_type
        ]

        target = target_delta if direction == "long" else -target_delta
        delta_candidates = [
            contract
            for contract in filtered
            if contract.get("delta") is not None
        ]

        if delta_candidates:
            return min(delta_candidates, key=lambda c: abs(float(c["delta"]) - target))

        if fallback.upper() == "ATM":
            return self._atm_contract(underlying_px, filtered or chain)

        return None

    def contracts_for_entry(
        self,
        symbol: str,
        direction: str,
        as_of: datetime,
        expiry_policy: str,
        target_delta: float,
        fallback: str,
    ) -> Optional[OptionContract]:
        expiry = self.pick_expiry(as_of, expiry_policy)
        chain = self.data_client.option_chain(symbol, expiry)

        if expiry_policy.lower() == "same_day" and not chain:
            expiry = self.pick_expiry(as_of + timedelta(days=1), "next_weekly")
            chain = self.data_client.option_chain(symbol, expiry)

        if not chain:
            return None

        underlying_px = self.data_client.latest_price(symbol)
        selected = self.pick_strike(underlying_px, chain, direction, target_delta, fallback)
        if not selected:
            return None

        strike_raw = selected.get("strike") or selected.get("strike_price")
        if strike_raw is None:
            return None

        ask_price = (
            selected.get("ask")
            or selected.get("ask_price")
            or selected.get("mid")
            or selected.get("mark")
        )
        if ask_price is None:
            return None

        strike = float(strike_raw)
        option_type = self._contract_type(selected)
        delta = float(selected.get("delta", 0.0))
        expiry_dt = self._contract_expiry(selected) or expiry
        option_symbol = selected.get("option_symbol") or self._build_symbol(symbol, strike, option_type, expiry_dt)
        ask = float(ask_price)

        return OptionContract(
            option_symbol=option_symbol,
            strike=strike,
            option_type=option_type,
            expiry=expiry_dt,
            delta=delta,
            ask=ask,
        )

    @staticmethod
    def _contract_type(contract: dict) -> str:
        return str(contract.get("type") or contract.get("option_type", "")).lower()

    @staticmethod
    def _contract_expiry(contract: dict) -> Optional[datetime]:
        expiry_val = contract.get("expiry") or contract.get("expiration_date")
        if not expiry_val:
            return None
        if isinstance(expiry_val, datetime):
            return expiry_val
        return datetime.fromisoformat(str(expiry_val))

    @staticmethod
    def _next_friday(current_date: date) -> date:
        days_ahead = (4 - current_date.weekday()) % 7
        return current_date + timedelta(days=days_ahead)

    @staticmethod
    def _atm_contract(underlying_px: float, chain: list) -> Optional[dict]:
        priced = [c for c in chain if c.get("strike") is not None or c.get("strike_price") is not None]
        if not priced:
            return None
        return min(priced, key=lambda c: abs(float(c.get("strike") or c.get("strike_price")) - underlying_px))

    @staticmethod
    def _build_symbol(symbol: str, strike: float, option_type: str, expiry: datetime) -> str:
        type_code = "C" if option_type == "call" else "P"
        strike_int = int(strike) if strike.is_integer() else strike
        return f"{symbol}_{expiry.strftime('%Y%m%d')}_{type_code}{strike_int}"
