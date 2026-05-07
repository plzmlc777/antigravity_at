"""
Regime feature extraction — continuous scores in (roughly) [-1, 1] or [0, 1].

Each function takes an OHLCV DataFrame (DatetimeIndex, columns
open/high/low/close/volume) and returns a Series of the same index.

The classifier discretizes these into 3-way labels.

Look-ahead safe: every rolling window uses past bars only. The score at
timestamp t is fully computable from data up to and including t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ────────────────────────────────────────────────────────────── trend ─────


def compute_trend_score(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 60,
) -> pd.Series:
    """Trend strength score in approx [-1, 1].

    Method: deviation of close from slow MA, normalized by the recent return
    stddev. Smoothed by the fast MA so the score isn't whiplashed by single bars.

    > 0  : close above slow MA in stdev-units (uptrend)
    < 0  : close below slow MA in stdev-units (downtrend)
    ~ 0  : sideways

    The clip+scale to [-1, 1] makes thresholds intuitive.
    """
    if slow <= fast:
        raise ValueError("slow must be > fast")
    close = df["close"]
    ma_fast = close.rolling(fast, min_periods=fast).mean()
    ma_slow = close.rolling(slow, min_periods=slow).mean()
    # Use ma_fast (smoothed close) instead of raw close to reduce noise.
    deviation_pct = (ma_fast - ma_slow) / ma_slow
    # Normalize by the typical magnitude of return-based variation.
    rets = close.pct_change()
    stdev = rets.rolling(slow, min_periods=slow).std(ddof=0)
    # Convert deviation to stdev-units: deviation_pct ~ N stdev moves
    score = deviation_pct / stdev.clip(lower=1e-6)
    return (score.clip(-3.0, 3.0) / 3.0).rename("trend_score")


# ────────────────────────────────────────────────────────── volatility ─────


def compute_volatility_score(
    df: pd.DataFrame,
    atr_period: int = 14,
    lookback: int = 200,
) -> pd.Series:
    """Volatility percentile rank in [0, 1].

    NATR (ATR / close) percentile-ranked against the trailing `lookback`
    window. 1.0 = highest vol seen recently, 0.0 = lowest.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(atr_period, min_periods=atr_period).mean()
    natr = atr / close.clip(lower=1e-9)
    # rolling percentile rank (pct=True returns rank fraction)
    rank = natr.rolling(lookback, min_periods=atr_period * 2).rank(pct=True)
    return rank.rename("volatility_score")


# ──────────────────────────────────────────────────────────── liquidity ─────


def compute_liquidity_score(
    df: pd.DataFrame,
    short: int = 20,
    long: int = 200,
) -> pd.Series:
    """Liquidity score in approx [-1, 1].

    Z-score of the short-window mean volume vs the long-window distribution.
    Positive = abnormally heavy volume (deep liquidity), negative = thin.
    """
    vol = df["volume"].astype(float)
    short_avg = vol.rolling(short, min_periods=short).mean()
    long_avg = vol.rolling(long, min_periods=long).mean()
    long_std = vol.rolling(long, min_periods=long).std(ddof=0)
    z = (short_avg - long_avg) / long_std.clip(lower=1.0)
    return (z.clip(-3.0, 3.0) / 3.0).rename("liquidity_score")


# ─────────────────────────────────────────────────────────── momentum ─────


def compute_momentum_score(
    df: pd.DataFrame,
    short: int = 10,
    mid: int = 50,
    long: int = 200,
    norm_lookback: int = 200,
) -> pd.Series:
    """Multi-horizon momentum aggregate, normalized to approx [-1, 1].

    Weighted blend of short / mid / long pct-change. Weight bias toward
    short-horizon for responsiveness, but long horizons keep us from
    flipping on noise.
    """
    close = df["close"]
    m_s = close.pct_change(short)
    m_m = close.pct_change(mid)
    m_l = close.pct_change(long)
    blended = 0.5 * m_s + 0.3 * m_m + 0.2 * m_l
    # normalize by rolling stdev of the blend itself
    blend_std = blended.rolling(norm_lookback, min_periods=long).std(ddof=0)
    score = blended / blend_std.clip(lower=1e-6)
    return (score.clip(-3.0, 3.0) / 3.0).rename("momentum_score")
