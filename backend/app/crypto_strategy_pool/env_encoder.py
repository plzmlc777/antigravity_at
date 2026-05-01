"""
Crypto Environment Encoder — Meta-Strategy MoE Phase 2 (24/7 version).

KR encoder의 mirror — time_sin/cos, dow_mon..fri (7 dim) 제거.
24/7 시장에 의미 있는 dimension 4개 추가:
  - momentum_1d (24h return, 빠른 모멘텀)
  - realized_vol_1d (직전 1d intraday std)
  - range_width_1d (1d Donchian 폭)
  - is_weekend (UTC Sat/Sun bool)

Feature layout (10 dims):
    0  vol_regime          rolling 30-day realized-vol pct rank (0..1)
    1  trend_1h            (EMA20_1h - EMA20.shift(3)) / |EMA20.shift(3)|
    2  trend_1d            (close_1d - EMA10_1d) / close
    3  range_width_1h      (donchian20_high - donchian20_low) / close (1h)
    4  range_width_1d      (donchian20_high - donchian20_low) / close (1d)
    5  liquidity_z         5d MA volume z-score vs 30d distribution
    6  momentum_5d         close_t / close_(t-5d) - 1
    7  momentum_1d         close_t / close_(t-1d) - 1   (24h return)
    8  realized_vol_1d     std of 1m returns over last 1440 bars
    9  is_weekend          1 if UTC weekday in (5,6) else 0
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .data_utils import resample_ohlcv
from .indicators import donchian, ema

FEATURE_NAMES: List[str] = [
    "vol_regime",
    "trend_1h",
    "trend_1d",
    "range_width_1h",
    "range_width_1d",
    "liquidity_z",
    "momentum_5d",
    "momentum_1d",
    "realized_vol_1d",
    "is_weekend",
]
FEATURE_DIM = len(FEATURE_NAMES)  # 10


def _safe(v: float) -> float:
    if v is None or np.isnan(v) or np.isinf(v):
        return 0.0
    return float(v)


def encode_environment(
    feed_1m: List[Dict[str, Any]],
    ts: str,
    macro: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """Encode crypto environment at timestamp `ts` (UTC) using feed_1m up to ts.

    Look-ahead safe.
    """
    if not feed_1m:
        return np.zeros(FEATURE_DIM, dtype=float)

    df = pd.DataFrame(feed_1m)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("ts").sort_index()

    target = pd.Timestamp(ts)
    df = df.loc[df.index <= target]
    if df.empty:
        return np.zeros(FEATURE_DIM, dtype=float)

    # daily resample (UTC calendar day)
    daily = resample_ohlcv(feed_1m, "1D")
    daily_df = pd.DataFrame(daily)
    if not daily_df.empty:
        daily_df["ts"] = pd.to_datetime(daily_df["timestamp"])
        daily_df = daily_df.set_index("ts").sort_index()
        prior_days = daily_df.loc[daily_df.index < target.normalize()]
    else:
        prior_days = pd.DataFrame()

    # 0. vol_regime
    if len(prior_days) >= 5:
        d_returns = prior_days["close"].pct_change().dropna()
        vol_30 = d_returns.rolling(30, min_periods=5).std()
        if len(vol_30.dropna()) >= 1:
            rank = vol_30.rank(pct=True)
            vol_regime = _safe(rank.iloc[-1])
        else:
            vol_regime = 0.5
    else:
        vol_regime = 0.5

    # 1. trend_1h
    feed_until = [c for c in feed_1m if pd.Timestamp(c["timestamp"]) <= target]
    h1 = resample_ohlcv(feed_until, "60min")
    if len(h1) >= 5:
        h1_df = pd.DataFrame(h1)
        h1_df["ts"] = pd.to_datetime(h1_df["timestamp"])
        h1_df = h1_df.set_index("ts").sort_index()
        e1h = ema(h1_df["close"], 20)
        if len(e1h.dropna()) >= 4:
            cur = e1h.iloc[-1]
            prev = e1h.iloc[-4]
            denom = abs(prev) if abs(prev) > 1e-9 else 1.0
            trend_1h = _safe((cur - prev) / denom)
        else:
            trend_1h = 0.0
    else:
        trend_1h = 0.0

    # 2. trend_1d
    if len(prior_days) >= 3:
        e1d = ema(prior_days["close"], 10)
        if len(e1d.dropna()) >= 1:
            last_close = prior_days["close"].iloc[-1]
            last_ema = e1d.iloc[-1]
            denom = abs(last_close) if abs(last_close) > 1e-9 else 1.0
            trend_1d = _safe((last_close - last_ema) / denom)
        else:
            trend_1d = 0.0
    else:
        trend_1d = 0.0

    # 3. range_width_1h
    if len(h1) >= 21:
        h1_df = pd.DataFrame(h1)
        h1_df["ts"] = pd.to_datetime(h1_df["timestamp"])
        h1_df = h1_df.set_index("ts").sort_index()
        upper, mid, lower = donchian(h1_df["high"], h1_df["low"], 20)
        cur_close = h1_df["close"].iloc[-1]
        if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]) and abs(cur_close) > 1e-9:
            range_width_1h = _safe((upper.iloc[-1] - lower.iloc[-1]) / cur_close)
        else:
            range_width_1h = 0.0
    else:
        range_width_1h = 0.0

    # 4. range_width_1d
    if len(prior_days) >= 21:
        upper, mid, lower = donchian(prior_days["high"], prior_days["low"], 20)
        cur_close = prior_days["close"].iloc[-1]
        if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]) and abs(cur_close) > 1e-9:
            range_width_1d = _safe((upper.iloc[-1] - lower.iloc[-1]) / cur_close)
        else:
            range_width_1d = 0.0
    else:
        range_width_1d = 0.0

    # 5. liquidity_z
    if len(prior_days) >= 5:
        v = prior_days["volume"]
        v_5 = v.rolling(5, min_periods=2).mean()
        v_30_mean = v.rolling(30, min_periods=5).mean()
        v_30_std = v.rolling(30, min_periods=5).std(ddof=0)
        last_v5 = v_5.iloc[-1]
        last_mean = v_30_mean.iloc[-1]
        last_std = v_30_std.iloc[-1]
        if pd.notna(last_v5) and pd.notna(last_mean) and pd.notna(last_std) and last_std > 0:
            liquidity_z = _safe((last_v5 - last_mean) / last_std)
        else:
            liquidity_z = 0.0
    else:
        liquidity_z = 0.0

    # 6. momentum_5d
    if len(prior_days) >= 6:
        last5 = prior_days["close"].iloc[-1]
        prior5 = prior_days["close"].iloc[-6]
        if abs(prior5) > 1e-9:
            momentum_5d = _safe(last5 / prior5 - 1.0)
        else:
            momentum_5d = 0.0
    else:
        momentum_5d = 0.0

    # 7. momentum_1d
    if len(prior_days) >= 2:
        c0 = prior_days["close"].iloc[-1]
        c1 = prior_days["close"].iloc[-2]
        if abs(c1) > 1e-9:
            momentum_1d = _safe(c0 / c1 - 1.0)
        else:
            momentum_1d = 0.0
    else:
        momentum_1d = 0.0

    # 8. realized_vol_1d (1m returns std over last 1440 bars)
    last1d = df.tail(1440)
    if len(last1d) >= 100:
        rets = last1d["close"].pct_change().dropna()
        if len(rets) >= 50:
            realized_vol_1d = _safe(float(rets.std(ddof=0)))
        else:
            realized_vol_1d = 0.0
    else:
        realized_vol_1d = 0.0

    # 9. is_weekend (UTC)
    is_weekend = 1.0 if target.weekday() in (5, 6) else 0.0

    vec = np.array(
        [
            vol_regime,
            trend_1h,
            trend_1d,
            range_width_1h,
            range_width_1d,
            liquidity_z,
            momentum_5d,
            momentum_1d,
            realized_vol_1d,
            is_weekend,
        ],
        dtype=float,
    )
    vec = np.where(np.isfinite(vec), vec, 0.0)
    return vec
