from dataclasses import dataclass
from typing import Sequence, Tuple


@dataclass
class MACDResult:
    macd: float
    signal: float
    histogram: float


def ema(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        raise ValueError("Not enough data for EMA")
    alpha = 2 / (period + 1)
    ema_values = []
    for i, price in enumerate(values):
        if i == 0:
            ema_values.append(price)
        else:
            ema_values.append((price - ema_values[-1]) * alpha + ema_values[-1])
    return ema_values


def macd(prices: Sequence[float], fast: int = 12, slow: int = 26, signal_period: int = 9) -> MACDResult:
    if len(prices) < slow + signal_period:
        raise ValueError("Not enough data for MACD")
    fast_ema = ema(prices, fast)
    slow_ema = ema(prices, slow)
    macd_line = [f - s for f, s in zip(fast_ema[-len(slow_ema) :], slow_ema)]
    signal_line = ema(macd_line, signal_period)
    histogram = [m - s for m, s in zip(macd_line[-len(signal_line) :], signal_line)]
    return MACDResult(macd=float(macd_line[-1]), signal=float(signal_line[-1]), histogram=float(histogram[-1]))


def latest_swing_high_lows(highs: Sequence[float], lows: Sequence[float]) -> Tuple[float, float]:
    if not highs or not lows:
        raise ValueError("Highs and lows required")
    return max(highs), min(lows)
