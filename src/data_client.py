import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


class DataClient:
    """Thin wrapper around Alpaca or mock data provider."""

    def __init__(self, provider: Optional[object] = None):
        self.provider = provider

    def get_bars(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[Bar]:
        if self.provider:
            return self.provider.get_bars(symbol, timeframe, start, end)
        # fallback mock data: generate flat bars for testing
        logger.warning("Using mock data provider for %s %s", symbol, timeframe)
        bars = []
        t = start
        price = 100.0
        while t < end:
            bars.append(Bar(timestamp=t, open=price, high=price + 1, low=price - 1, close=price, volume=1000))
            t += _timeframe_to_timedelta(timeframe)
        return bars

    def latest_price(self, symbol: str) -> float:
        if self.provider:
            return self.provider.latest_price(symbol)
        return 100.0

    def option_chain(self, symbol: str, expiry: datetime):
        if self.provider:
            return self.provider.option_chain(symbol, expiry)
        # mock chain
        strikes = [90, 95, 100, 105, 110]
        deltas = [0.2, 0.35, 0.5, 0.65, 0.8]
        premiums = [1.5, 2.5, 3.5, 5.5, 7.5]
        return [
            {
                "strike": strike,
                "delta": delta,
                "bid": premium,
                "ask": premium + 0.3,
                "type": "call",
            }
            for strike, delta, premium in zip(strikes, deltas, premiums)
        ]


def _timeframe_to_timedelta(timeframe: str) -> timedelta:
    if timeframe.lower().startswith("5"):
        return timedelta(minutes=5)
    if timeframe.lower().startswith("15"):
        return timedelta(minutes=15)
    if timeframe.lower().startswith("30"):
        return timedelta(minutes=30)
    if timeframe.lower().startswith("60"):
        return timedelta(minutes=60)
    raise ValueError(f"Unsupported timeframe: {timeframe}")
