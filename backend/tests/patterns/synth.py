"""Synthetic OHLCV generators for pattern unit tests.

Each helper returns a DataFrame with columns [open, high, low, close, volume]
indexed by DatetimeIndex (1m frequency by default). All prices are float, volume int.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _make_index(n: int, start: str = "2025-01-01 09:00", freq: str = "1min") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq=freq)


def flat_noise(n: int = 100, base: float = 100.0, vol: float = 0.5, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = _make_index(n)
    closes = base + rng.normal(0, vol, n).cumsum() * 0.0
    opens = closes + rng.normal(0, vol * 0.3, n)
    highs = np.maximum(opens, closes) + rng.uniform(0, vol, n)
    lows = np.minimum(opens, closes) - rng.uniform(0, vol, n)
    volumes = rng.integers(900, 1100, n)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def bullish_engulfing_at(n: int = 50, idx_pos: int = 30) -> pd.DataFrame:
    """Bullish engulfing at idx_pos.

    Detector now requires:
      - prev bar bearish, curr bar bullish, body engulf
      - curr body >= 1.5 × prev body
      - curr body >= avg body (last 20)
      - prev close < MA(10).shift(1) — i.e. preceding downtrend
    So the synthetic must include a downtrend leading into idx_pos.
    """
    df = flat_noise(n, base=100, vol=0.1, seed=1).copy()
    # Force a downtrend over the 15 bars before idx_pos
    for k in range(idx_pos - 15, idx_pos):
        v = 102.0 - 0.15 * (k - (idx_pos - 15))
        df.iloc[k, df.columns.get_loc("open")] = v + 0.05
        df.iloc[k, df.columns.get_loc("close")] = v
        df.iloc[k, df.columns.get_loc("high")] = v + 0.15
        df.iloc[k, df.columns.get_loc("low")] = v - 0.10
    # prev bar (idx_pos-1): bearish, modest body
    p = idx_pos - 1
    df.iloc[p, df.columns.get_loc("open")] = 100.0
    df.iloc[p, df.columns.get_loc("close")] = 99.5
    df.iloc[p, df.columns.get_loc("high")] = 100.1
    df.iloc[p, df.columns.get_loc("low")] = 99.4
    # curr bar: bullish, body engulfs prev with comfortable margin
    df.iloc[idx_pos, df.columns.get_loc("open")] = 99.4
    df.iloc[idx_pos, df.columns.get_loc("close")] = 100.7
    df.iloc[idx_pos, df.columns.get_loc("high")] = 100.9
    df.iloc[idx_pos, df.columns.get_loc("low")] = 99.3
    df.iloc[idx_pos, df.columns.get_loc("volume")] = 4000
    return df


def bearish_engulfing_at(n: int = 50, idx_pos: int = 30) -> pd.DataFrame:
    """Bearish engulfing at idx_pos with preceding uptrend (mirror of bullish)."""
    df = flat_noise(n, base=100, vol=0.1, seed=2).copy()
    for k in range(idx_pos - 15, idx_pos):
        v = 98.0 + 0.15 * (k - (idx_pos - 15))
        df.iloc[k, df.columns.get_loc("open")] = v - 0.05
        df.iloc[k, df.columns.get_loc("close")] = v
        df.iloc[k, df.columns.get_loc("high")] = v + 0.10
        df.iloc[k, df.columns.get_loc("low")] = v - 0.15
    p = idx_pos - 1
    df.iloc[p, df.columns.get_loc("open")] = 100.0
    df.iloc[p, df.columns.get_loc("close")] = 100.5
    df.iloc[p, df.columns.get_loc("high")] = 100.6
    df.iloc[p, df.columns.get_loc("low")] = 99.9
    df.iloc[idx_pos, df.columns.get_loc("open")] = 100.6
    df.iloc[idx_pos, df.columns.get_loc("close")] = 99.3
    df.iloc[idx_pos, df.columns.get_loc("high")] = 100.7
    df.iloc[idx_pos, df.columns.get_loc("low")] = 99.1
    df.iloc[idx_pos, df.columns.get_loc("volume")] = 4000
    return df


def doji_at(n: int = 50, idx_pos: int = 30) -> pd.DataFrame:
    df = flat_noise(n, base=100, vol=0.3, seed=3).copy()
    df.iloc[idx_pos, df.columns.get_loc("open")] = 100.0
    df.iloc[idx_pos, df.columns.get_loc("close")] = 100.005
    df.iloc[idx_pos, df.columns.get_loc("high")] = 100.6
    df.iloc[idx_pos, df.columns.get_loc("low")] = 99.4
    return df


def double_top(n: int = 100) -> pd.DataFrame:
    """Two near-equal peaks with trough between, then breakdown.

    Geometry: rise→peak1→shallow dip→peak2→breakdown below trough, all within
    the detector's default 60-bar lookback so both peaks remain visible.
    """
    rng_local = np.random.default_rng(42)
    idx = _make_index(n)
    closes = np.full(n, 100.0)
    for i in range(0, 15):  # rise to ~110
        closes[i] = 100 + (i / 14) * 10
    for i in range(15, 22):  # peak1 plateau ~110
        closes[i] = 110 + rng_local.uniform(-0.2, 0.2)
    for i in range(22, 35):  # shallow trough to ~106
        closes[i] = 110 - (i - 22) * 0.32
    for i in range(35, 48):  # rise back to ~110
        closes[i] = 105.84 + (i - 35) * 0.32
    for i in range(48, 55):  # peak2 plateau ~110
        closes[i] = 110 + rng_local.uniform(-0.2, 0.2)
    for i in range(55, n):  # breakdown clearly below trough (~106)
        closes[i] = 110 - (i - 55) * 0.6
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) + 0.15
    lows = np.minimum(opens, closes) - 0.15
    volumes = np.full(n, 1000, dtype=int)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def double_bottom(n: int = 100) -> pd.DataFrame:
    df = double_top(n).copy()
    # Mirror around 100
    for c in ("open", "high", "low", "close"):
        df[c] = 200 - df[c]
    # high/low must remain consistent
    new_high = df[["open", "close"]].max(axis=1) + 0.2
    new_low = df[["open", "close"]].min(axis=1) - 0.2
    df["high"] = new_high
    df["low"] = new_low
    return df


def golden_cross_setup(n: int = 120) -> pd.DataFrame:
    """Trend that creates a 20/50-MA bullish cross around bar ~70."""
    idx = _make_index(n)
    closes = np.empty(n)
    for i in range(n):
        if i < 40:
            closes[i] = 100 - i * 0.2  # downtrend
        elif i < 70:
            closes[i] = 92 + (i - 40) * 0.05  # flatten
        else:
            closes[i] = 93.5 + (i - 70) * 0.4  # uptrend
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) + 0.3
    lows = np.minimum(opens, closes) - 0.3
    volumes = np.full(n, 1000, dtype=int)
    volumes[70:90] = 1500
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def volume_climax_at(n: int = 60, idx_pos: int = 40, kind: str = "bull") -> pd.DataFrame:
    df = flat_noise(n, base=100, vol=0.4, seed=5).copy()
    # Set baseline volumes low
    df["volume"] = 1000
    if kind == "bull":
        # Big down bar with massive volume, close near low
        df.iloc[idx_pos, df.columns.get_loc("open")] = 100.0
        df.iloc[idx_pos, df.columns.get_loc("close")] = 97.2
        df.iloc[idx_pos, df.columns.get_loc("high")] = 100.1
        df.iloc[idx_pos, df.columns.get_loc("low")] = 97.0
    else:
        df.iloc[idx_pos, df.columns.get_loc("open")] = 100.0
        df.iloc[idx_pos, df.columns.get_loc("close")] = 102.8
        df.iloc[idx_pos, df.columns.get_loc("high")] = 103.0
        df.iloc[idx_pos, df.columns.get_loc("low")] = 99.9
    df.iloc[idx_pos, df.columns.get_loc("volume")] = 10000
    return df
