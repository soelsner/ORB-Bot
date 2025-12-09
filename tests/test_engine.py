from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.data_client import Bar
from src.fib_orb_engine import FibOrbEngine


def build_bars(start: datetime, count: int, base: float) -> list[Bar]:
    bars = []
    for i in range(count):
        ts = start + timedelta(minutes=5 * i)
        price = base + i * 0.2
        bars.append(Bar(timestamp=ts, open=price, high=price + 0.5, low=price - 0.5, close=price, volume=1000))
    return bars


def test_engine_generates_long_signal_with_retest_and_macd():
    tz = ZoneInfo("America/New_York")
    start = datetime(2024, 1, 5, 9, 30, tzinfo=tz)
    bars = build_bars(start, 40, 100)
    # Force an ORB breakout by lifting the 7th bar far above
    breakout_index = 7
    bars[breakout_index] = Bar(
        timestamp=bars[breakout_index].timestamp,
        open=110,
        high=111,
        low=109,
        close=111,
        volume=2000,
    )
    # Retest around fib levels after breakout
    bars[breakout_index + 1] = Bar(
        timestamp=bars[breakout_index + 1].timestamp,
        open=105,
        high=106,
        low=104,
        close=105,
        volume=1500,
    )

    engine = FibOrbEngine(orb_minutes=30, breakout_close_minutes=5)
    signal = engine.evaluate(bars)
    assert signal is not None
    assert signal.direction == "long"
    fibs = engine._fib_levels(bars, signal.direction)
    assert fibs["0.618"] <= signal.entry <= fibs["0.5"]
    assert signal.stop < signal.entry
