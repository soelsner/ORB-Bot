"""Technical indicators and validation helpers for MACD-based signals.

This module provides utility functions for computing the Moving Average
Convergence Divergence (MACD) indicator and evaluating simple signal rules
used by the bot. An optional swing detection helper is also included to assist
with stop placement logic.
"""
from __future__ import annotations

from typing import Literal, Optional, Tuple

import pandas as pd

Direction = Literal["long", "short"]


def macd(df_close: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    """Compute the MACD line, signal line, and histogram.

    Args:
        df_close: Series of closing prices indexed by datetime.
        fast: Fast EMA span.
        slow: Slow EMA span.
        signal: Signal line EMA span.

    Returns:
        DataFrame with columns ``macd``, ``signal``, and ``hist`` aligned to
        the input index.
    """

    fast_ema = df_close.ewm(span=fast, adjust=False).mean()
    slow_ema = df_close.ewm(span=slow, adjust=False).mean()

    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line

    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def is_macd_ok(macd_df: pd.DataFrame, direction: Direction, confirm_bars: int) -> bool:
    """Determine whether MACD momentum confirms the trade direction.

    For longs, the MACD line must cross above the signal line on the latest bar
    and the sum of MACD deltas over ``confirm_bars`` must be positive (curling up).
    Shorts apply the opposite logic.

    Args:
        macd_df: DataFrame produced by :func:`macd` containing ``macd`` and
            ``signal`` columns.
        direction: "long" or "short".
        confirm_bars: Number of recent bars used to measure MACD curl.

    Returns:
        True when MACD conditions align with the requested direction.
    """

    if macd_df.empty:
        return False

    recent = macd_df.tail(confirm_bars).copy()
    macd_line = recent["macd"]
    signal_line = recent["signal"]

    delta_sum = macd_line.diff().sum()

    if direction == "long":
        return macd_line.iat[-1] > signal_line.iat[-1] and delta_sum > 0

    if direction == "short":
        return macd_line.iat[-1] < signal_line.iat[-1] and delta_sum < 0

    raise ValueError("direction must be 'long' or 'short'")


def last_swing(
    df_5m: pd.DataFrame, direction: Direction, lookback: int = 20
) -> Optional[Tuple[pd.Timestamp, float]]:
    """Locate the most recent swing point to refine stop placement.

    The function scans backwards over the specified lookback window to find the
    latest swing low (for longs) or swing high (for shorts) using a simple
    three-bar pivot check. It returns the timestamp and price of that swing.

    Args:
        df_5m: Five-minute OHLC data containing ``high`` and ``low`` columns.
        direction: "long" or "short".
        lookback: Number of bars to inspect from the end of the dataset.

    Returns:
        Tuple of (timestamp, price) when a swing is found, otherwise ``None``.
    """

    if df_5m.empty:
        return None

    window = df_5m.tail(lookback)

    if direction == "long":
        pivot_mask = (
            (window["low"] <= window["low"].shift(1))
            & (window["low"] <= window["low"].shift(-1))
        )
        pivot_series = window.loc[pivot_mask, "low"]
    elif direction == "short":
        pivot_mask = (
            (window["high"] >= window["high"].shift(1))
            & (window["high"] >= window["high"].shift(-1))
        )
        pivot_series = window.loc[pivot_mask, "high"]
    else:
        raise ValueError("direction must be 'long' or 'short'")

    if pivot_series.empty:
        return None

    idx = pivot_series.index[-1]
    return idx, pivot_series.iat[-1]
