from dataclasses import dataclass
from typing import List, Optional

from .data_client import Bar
from .indicators import MACDResult, macd, latest_swing_high_lows


@dataclass
class ORBBox:
    high: float
    low: float
    start: str
    end: str


@dataclass
class TradeSignal:
    direction: str  # "long" or "short"
    entry: float
    stop: float
    targets: List[float]
    reason: str
    orb: ORBBox


class FibOrbEngine:
    def __init__(self, orb_minutes: int = 30, breakout_close_minutes: int = 5):
        self.orb_minutes = orb_minutes
        self.breakout_close_minutes = breakout_close_minutes

    def evaluate(self, bars: List[Bar]) -> Optional[TradeSignal]:
        if len(bars) < 5:
            return None
        orb_box = self._build_orb(bars)
        breakout_bar = self._detect_breakout(bars, orb_box)
        if not breakout_bar:
            return None
        direction = "long" if breakout_bar.close > orb_box.high else "short"
        fibs = self._fib_levels(bars, direction)
        pullback_entry = self._find_retest(bars, breakout_bar.timestamp, direction, fibs)
        if pullback_entry is None:
            return None
        macd_result = self._macd_confluence([b.close for b in bars])
        if not self._macd_confirms(direction, macd_result):
            return None
        stop = fibs["0.786"]
        targets = self._targets(bars, direction, fibs)
        reason = f"ORB breakout with {direction} fib retest and MACD confluence"
        return TradeSignal(direction=direction, entry=pullback_entry, stop=stop, targets=targets, reason=reason, orb=orb_box)

    def _build_orb(self, bars: List[Bar]) -> ORBBox:
        start_ts = bars[0].timestamp
        orb_cutoff = start_ts + self._minutes(self.orb_minutes)
        orb_bars = [b for b in bars if b.timestamp < orb_cutoff]
        high = max(b.high for b in orb_bars)
        low = min(b.low for b in orb_bars)
        return ORBBox(high=high, low=low, start=str(start_ts), end=str(orb_cutoff))

    def _detect_breakout(self, bars: List[Bar], orb: ORBBox) -> Optional[Bar]:
        orb_end = bars[0].timestamp + self._minutes(self.orb_minutes)
        for bar in bars:
            if bar.timestamp <= orb_end:
                continue
            if bar.close > orb.high or bar.close < orb.low:
                return bar
        return None

    def _fib_levels(self, bars: List[Bar], direction: str) -> dict:
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        session_high, session_low = latest_swing_high_lows(highs, lows)
        if direction == "long":
            anchor_high, anchor_low = session_high, session_low
        else:
            anchor_high, anchor_low = session_low, session_high
        diff = anchor_high - anchor_low
        levels = {
            "0.5": anchor_high - 0.5 * diff,
            "0.618": anchor_high - 0.618 * diff,
            "0.786": anchor_high - 0.786 * diff,
            "1.272": anchor_high + 0.272 * diff,
            "1.618": anchor_high + 0.618 * diff,
        }
        return levels

    def _find_retest(self, bars: List[Bar], breakout_time, direction: str, fibs: dict) -> Optional[float]:
        for bar in bars:
            if bar.timestamp <= breakout_time:
                continue
            target_range = (fibs["0.618"], fibs["0.5"]) if direction == "long" else (fibs["0.5"], fibs["0.618"])
            low, high = min(target_range), max(target_range)
            if low <= bar.low <= high or low <= bar.high <= high or (bar.low <= low and bar.high >= high):
                return fibs["0.618"] if direction == "long" else fibs["0.5"]
        return None

    def _macd_confluence(self, closes: List[float]) -> MACDResult:
        return macd(closes)

    def _macd_confirms(self, direction: str, macd_result: MACDResult) -> bool:
        if direction == "long":
            return macd_result.macd >= macd_result.signal and macd_result.histogram >= 0
        return macd_result.macd <= macd_result.signal and macd_result.histogram <= 0

    def _targets(self, bars: List[Bar], direction: str, fibs: dict) -> List[float]:
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        hod = max(highs)
        lod = min(lows)
        first = hod if direction == "long" else lod
        extensions = [fibs["1.272"], fibs["1.618"]]
        return [first] + extensions

    @staticmethod
    def _minutes(mins: int):
        from datetime import timedelta

        return timedelta(minutes=mins)
