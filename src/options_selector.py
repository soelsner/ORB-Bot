from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class OptionCandidate:
    strike: float
    option_type: str
    expiry: datetime
    delta: float
    mid: float


class OptionsSelector:
    def __init__(self, data_client, min_delta: float = 0.3, max_delta: float = 0.6, days_to_expiry: int = 5):
        self.data_client = data_client
        self.min_delta = min_delta
        self.max_delta = max_delta
        self.days_to_expiry = days_to_expiry

    def choose(self, symbol: str, direction: str, as_of: datetime) -> Optional[OptionCandidate]:
        expiry = as_of + timedelta(days=self.days_to_expiry)
        chain = self.data_client.option_chain(symbol, expiry)
        if not chain:
            return None
        desired_type = "call" if direction == "long" else "put"
        filtered = [c for c in chain if self.min_delta <= c["delta"] <= self.max_delta and c["type"].lower() == desired_type]
        if not filtered:
            filtered = [c for c in chain if c["type"].lower() == desired_type]
        if not filtered:
            return None
        for candidate in filtered:
            candidate["mid"] = (candidate["bid"] + candidate["ask"]) / 2
        filtered.sort(key=lambda c: abs(c["delta"] - (self.max_delta + self.min_delta) / 2))
        chosen = filtered[0]
        return OptionCandidate(
            strike=float(chosen["strike"]),
            option_type=desired_type,
            expiry=expiry,
            delta=float(chosen["delta"]),
            mid=float(chosen["mid"]),
        )
