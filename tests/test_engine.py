from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.data_client import Bar
from src.fib_orb_engine import (
    FibOrbEngine,
    anchors,
    await_pullback_to,
    compute_orb,
    detect_breakout,
    fib_grid,
    stops_targets,
)


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
    fibs = fib_grid(min(b.low for b in bars), max(b.high for b in bars))
    assert fibs[0.618] <= signal.entry <= fibs[0.5]
    assert signal.stop < signal.entry


def test_orb_and_breakout_detection():
    tz = ZoneInfo("America/New_York")
    start = datetime(2024, 1, 5, 9, 30, tzinfo=tz)
    bars = build_bars(start, 12, 100)
    # Keep post-ORB bars inside the original range until we explicitly add a breakout
    for i in range(6, len(bars)):
        base = 100 + 0.2 * 5
        ts = bars[i].timestamp
        bars[i] = Bar(timestamp=ts, open=base, high=base + 0.3, low=base - 0.3, close=base, volume=900)
    or_high, or_low, or_end = compute_orb(bars, 30)
    direction, breakout_ts = detect_breakout(bars, or_high, or_low, or_end)
    assert direction is None

    breakout_bar = Bar(
        timestamp=or_end + timedelta(minutes=5),
        open=102,
        high=103,
        low=101.5,
        close=103,
        volume=1200,
    )
    bars[7] = breakout_bar
    direction, breakout_ts = detect_breakout(bars, or_high, or_low, or_end)
    assert direction == "up"
    assert breakout_ts == breakout_bar.timestamp


def test_pullback_and_targets():
    tz = ZoneInfo("America/New_York")
    start = datetime(2024, 1, 5, 9, 30, tzinfo=tz)
    bars = build_bars(start, 12, 100)
    day_low = min(b.low for b in bars)
    day_high = max(b.high for b in bars)
    A, B = anchors("long", day_low, day_high)
    fibs = fib_grid(A, B)
    breakout_ts = bars[6].timestamp

    # Insert deeper bar to extend B before pullback
    bars[7] = Bar(
        timestamp=breakout_ts + timedelta(minutes=5),
        open=111,
        high=112,
        low=109,
        close=112,
        volume=1500,
    )
    bars[8] = Bar(
        timestamp=breakout_ts + timedelta(minutes=10),
        open=106,
        high=107,
        low=104,
        close=105,
        volume=1200,
    )

    entry_info, fibs_at_entry = await_pullback_to(
        bars,
        "long",
        fibs,
        breakout_ts,
        levels=[0.5, 0.618],
        no_pullback_timeout_min=60,
    )
    assert entry_info is not None
    level, ts, price = entry_info
    assert level == 0.5
    assert ts == bars[8].timestamp
    assert fibs_at_entry[0.5] == price

    stop, targets = stops_targets("long", fibs_at_entry, price, mode="fib")
    assert stop < price
    assert targets[0] == fibs_at_entry["B"]
