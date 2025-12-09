"""ORB + Fibonacci retracement engine.

This module provides a small toolkit for building an Opening Range Breakout
approach that waits for a Fibonacci pullback before entering.  The public
functions are intentionally composable so that a caller can mix-and-match the
pieces in higher level workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .data_client import Bar
from .indicators import MACDResult, macd


@dataclass
class ORBBox:
    high: float
    low: float
    start: datetime
    end: datetime


@dataclass
class TradeSignal:
    direction: str  # "long" or "short"
    entry: float
    stop: float
    targets: List[float]
    reason: str
    orb: ORBBox
    entry_time: datetime


def compute_orb(bars_1m: Iterable[Bar], minutes: int) -> Tuple[float, float, datetime]:
    """Compute the opening range box.

    Args:
        bars_1m: Sequence of 1-minute bars for the session.
        minutes: Duration of the opening range window.

    Returns:
        Tuple of (or_high, or_low, or_end_ts).
    """

    bars = list(bars_1m)
    if not bars:
        raise ValueError("At least one bar is required to compute the ORB")

    start_ts = bars[0].timestamp
    orb_end_ts = start_ts + timedelta(minutes=minutes)
    orb_bars = [b for b in bars if b.timestamp < orb_end_ts]
    if not orb_bars:
        raise ValueError("No bars inside ORB window")

    or_high = max(b.high for b in orb_bars)
    or_low = min(b.low for b in orb_bars)
    return or_high, or_low, orb_end_ts


def detect_breakout(
    bars_5m: Iterable[Bar],
    or_high: float,
    or_low: float,
    or_end_ts: datetime,
    require_close: bool = True,
) -> Tuple[Optional[str], Optional[datetime]]:
    """Detect the first 5-minute bar that breaks the OR.

    Args:
        bars_5m: 5-minute bars for the session.
        or_high: Opening range high.
        or_low: Opening range low.
        or_end_ts: Opening range end timestamp.
        require_close: Whether the bar must *close* beyond the OR (default) or
            whether a wick is sufficient.

    Returns:
        A tuple of (direction, breakout_bar_ts) where direction is "up",
        "down" or ``None``.
    """

    for bar in bars_5m:
        if bar.timestamp <= or_end_ts:
            continue

        closes_beyond = bar.close > or_high or bar.close < or_low
        wicks_beyond = bar.high > or_high or bar.low < or_low

        triggered = closes_beyond if require_close else wicks_beyond
        if not triggered:
            continue

        direction = "up" if (bar.close if require_close else bar.high) > or_high else "down"
        return direction, bar.timestamp

    return None, None


def anchors(direction: str, day_low: float, day_high: float) -> Tuple[float, float]:
    """Return anchor points A and B for the chosen direction."""

    if direction == "long":
        return day_low, day_high
    return day_high, day_low


def fib_grid(A: float, B: float) -> Dict[float, float]:
    """Build a Fibonacci grid from anchors A and B.

    Keys are floats (e.g. ``0.5``, ``0.618``, ``1.272``) to make downstream
    arithmetic straightforward.
    """

    diff = B - A
    grid = {
        0.236: B - diff * 0.236,
        0.382: B - diff * 0.382,
        0.5: B - diff * 0.5,
        0.618: B - diff * 0.618,
        0.786: B - diff * 0.786,
        1.272: B + diff * 0.272,
        1.618: B + diff * 0.618,
        "A": A,
        "B": B,
    }
    return grid


def await_pullback_to(
    bars_5m: Iterable[Bar],
    direction: str,
    fibs: Dict[float, float],
    breakout_ts: datetime,
    *,
    levels: Optional[List[float]] = None,
    no_pullback_timeout_min: Optional[int] = None,
) -> Tuple[Optional[Tuple[float, datetime, float]], Dict[float, float]]:
    """Walk bars after the breakout until a retracement tag occurs.

    Args:
        bars_5m: 5-minute bars for the session.
        direction: "long" or "short".
        fibs: Initial fib grid (will be updated if B extends before entry).
        breakout_ts: Timestamp of the breakout bar.
        levels: Which fib retracements to accept as entries.
        no_pullback_timeout_min: Abort if no pullback occurs before this many
            minutes elapse after the breakout.

    Returns:
        ``(entry_info, fibs_at_entry)``. ``entry_info`` is a tuple of
        ``(level_key, bar_ts, entry_price)`` or ``None`` if invalidated/timeout.
        The fib dictionary reflects the final anchor state (B may have changed
        if new extremes printed before entry).
    """

    levels = levels or [0.5, 0.618]
    A = fibs["A"]
    B = fibs["B"]
    current_fibs = dict(fibs)
    expiry_ts = breakout_ts + timedelta(minutes=no_pullback_timeout_min) if no_pullback_timeout_min else None

    for bar in bars_5m:
        if bar.timestamp <= breakout_ts:
            continue
        if expiry_ts and bar.timestamp > expiry_ts:
            break

        # Update anchor B until an entry tag occurs, then freeze.
        if direction == "long" and bar.high > B:
            B = bar.high
            current_fibs = fib_grid(A, B)
        elif direction == "short" and bar.low < B:
            B = bar.low
            current_fibs = fib_grid(A, B)

        # Invalidation: close beyond 0.786 against the direction.
        if direction == "long" and bar.close < current_fibs[0.786]:
            return None, current_fibs
        if direction == "short" and bar.close > current_fibs[0.786]:
            return None, current_fibs

        for level in levels:
            level_price = current_fibs[level]
            if bar.low <= level_price <= bar.high:
                return (level, bar.timestamp, level_price), current_fibs

    return None, current_fibs


def stops_targets(direction: str, fibs: Dict[float, float], entry_price: float, mode: str = "fib") -> Tuple[float, List[float]]:
    """Compute stop and targets.

    Args:
        direction: "long" or "short".
        fibs: Fibonacci grid at entry time.
        entry_price: Execution price (generally the tagged fib level).
        mode: ``"fib"`` for 1.272/1.618 extensions or ``"rr```` for a risk
            multiple target.
    """

    swing_stop = fibs["A"]
    buffer_stop = fibs[0.786]
    if direction == "long":
        stop = min(buffer_stop, swing_stop)
        hod_retest = fibs["B"]
        if mode == "rr":
            rr_target = entry_price + 2 * (entry_price - stop)
            targets = [hod_retest, rr_target]
        else:
            targets = [hod_retest, fibs[1.272], fibs[1.618]]
    else:
        stop = max(buffer_stop, swing_stop)
        lod_retest = fibs["B"]
        if mode == "rr":
            rr_target = entry_price - 2 * (stop - entry_price)
            targets = [lod_retest, rr_target]
        else:
            targets = [lod_retest, fibs[1.272], fibs[1.618]]

    return stop, targets


class FibOrbEngine:
    """High-level convenience wrapper that stitches the building blocks."""

    def __init__(
        self,
        orb_minutes: int = 30,
        breakout_close_minutes: int = 5,
        no_pullback_timeout_min: int = 60,
        pullback_levels: Optional[List[float]] = None,
    ):
        self.orb_minutes = orb_minutes
        self.breakout_close_minutes = breakout_close_minutes
        self.no_pullback_timeout_min = no_pullback_timeout_min
        self.pullback_levels = pullback_levels or [0.5, 0.618]

    def evaluate(self, bars: List[Bar]) -> Optional[TradeSignal]:
        if len(bars) < 6:
            return None

        or_high, or_low, or_end = compute_orb(bars, self.orb_minutes)
        direction, breakout_ts = detect_breakout(bars, or_high, or_low, or_end)
        if not breakout_ts:
            return None

        direction_label = "long" if direction == "up" else "short"
        day_high = max(b.high for b in bars)
        day_low = min(b.low for b in bars)
        A, B = anchors(direction_label, day_low, day_high)
        fibs = fib_grid(A, B)

        entry_info, fibs_at_entry = await_pullback_to(
            bars,
            direction_label,
            fibs,
            breakout_ts,
            levels=self.pullback_levels,
            no_pullback_timeout_min=self.no_pullback_timeout_min,
        )
        if entry_info is None:
            return None
        level_used, entry_ts, entry_price = entry_info

        # Optional MACD confluence on closes; skip filter if insufficient data
        try:
            macd_result: MACDResult = macd([b.close for b in bars if b.timestamp <= entry_ts])
        except ValueError:
            macd_result = None
        if macd_result and not self._macd_confirms(direction_label, macd_result):
            return None

        stop, targets = stops_targets(direction_label, fibs_at_entry, entry_price, mode="fib")
        reason = f"ORB breakout {direction_label} with fib pullback at {level_used}"
        orb_box = ORBBox(high=or_high, low=or_low, start=bars[0].timestamp, end=or_end)
        return TradeSignal(direction=direction_label, entry=entry_price, stop=stop, targets=targets, reason=reason, orb=orb_box, entry_time=entry_ts)

    @staticmethod
    def _macd_confirms(direction: str, macd_result: MACDResult) -> bool:
        if direction == "long":
            return macd_result.macd >= macd_result.signal and macd_result.histogram >= 0
        return macd_result.macd <= macd_result.signal and macd_result.histogram <= 0

