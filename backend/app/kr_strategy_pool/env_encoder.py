"""
Environment Encoder — Meta-Strategy MoE Phase 2.

Encode market state at a given timepoint into a fixed-dim feature vector that
Phase 4's meta-learner uses to pick the best multi-TF strategy.

Phase 2 default = market-internal features only (no KOSPI/USDKRW/macro).

Feature layout (13 dims, order is stable — never reorder):
    0  vol_regime          rolling 30-trading-day realized-vol pct rank (0..1)
    1  trend_1h            (EMA20_1h - EMA20_1h.shift(3)) / |EMA20.shift(3)|
    2  trend_1d            (close_1d - EMA10_1d) / close
    3  range_width_1h      (donchian20_high - donchian20_low) / close (1h)
    4  liquidity_z         5d MA volume z-score vs 30d distribution
    5  time_sin            sin(2*pi * minute_into_session / 390)
    6  time_cos            cos(2*pi * minute_into_session / 390)
    7  dow_mon
    8  dow_tue
    9  dow_wed
    10 dow_thu
    11 dow_fri
    12 momentum_5d         close_t / close_(t-5 trading days) - 1

Output is np.ndarray of shape (12,), no NaN, no Inf (replaced with 0).
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .data_utils import resample_ohlcv
from .indicators import donchian, ema

# 한국 정규장 시간(분 단위)
_SESSION_OPEN = time(9, 0)
_SESSION_CLOSE = time(15, 30)
_SESSION_MINUTES = (
    (_SESSION_CLOSE.hour * 60 + _SESSION_CLOSE.minute)
    - (_SESSION_OPEN.hour * 60 + _SESSION_OPEN.minute)
)  # 390

FEATURE_NAMES: List[str] = [
    "vol_regime",
    "trend_1h",
    "trend_1d",
    "range_width_1h",
    "liquidity_z",
    "time_sin",
    "time_cos",
    "dow_mon",
    "dow_tue",
    "dow_wed",
    "dow_thu",
    "dow_fri",
    "momentum_5d",
]
FEATURE_DIM = len(FEATURE_NAMES)  # 13


def _safe(v: float) -> float:
    if v is None or np.isnan(v) or np.isinf(v):
        return 0.0
    return float(v)


def _minute_of_session(ts: pd.Timestamp) -> int:
    minute = ts.hour * 60 + ts.minute
    open_min = _SESSION_OPEN.hour * 60 + _SESSION_OPEN.minute
    return max(0, min(_SESSION_MINUTES, minute - open_min))


def encode_environment(
    feed_1m: List[Dict[str, Any]],
    ts: str,
    macro: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """Encode environment at timestamp `ts` using 1m feed up to (and including) ts.

    Look-ahead safe: only uses bars with timestamp <= ts.

    Args:
        feed_1m: list of {timestamp, open, high, low, close, volume} dicts.
        ts: ISO timestamp string identifying the encoding point.
        macro: reserved for Phase 2.5 (KOSPI/USDKRW); ignored in v1.

    Returns:
        np.ndarray shape (FEATURE_DIM,) with no NaN/Inf.
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

    # ── 일봉 (close-by-day) for vol_regime, momentum_5d, trend_1d
    daily = resample_ohlcv(feed_1m, "1D")
    daily_df = pd.DataFrame(daily)
    if not daily_df.empty:
        daily_df["ts"] = pd.to_datetime(daily_df["timestamp"])
        daily_df = daily_df.set_index("ts").sort_index()
        # 시점 t의 day는 포함하지 말 것 (look-ahead 회피) — 단, 같은 날 이전 bar는 OK
        # 실시간이면 t의 daily bar는 아직 close 안 됨. 그러면 t 이전 일까지의 daily만 사용.
        prior_days = daily_df.loc[daily_df.index < target.normalize()]
    else:
        prior_days = pd.DataFrame()

    # 0. vol_regime — 30 trading-day realized vol pct rank
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

    # 1. trend_1h — EMA20 slope on 1h bars up to last closed 1h bar before target
    feed_until = [c for c in feed_1m if pd.Timestamp(c["timestamp"]) <= target]
    h1 = resample_ohlcv(feed_until, "60min")
    if len(h1) >= 5:
        h1_df = pd.DataFrame(h1)
        h1_df["ts"] = pd.to_datetime(h1_df["timestamp"])
        h1_df = h1_df.set_index("ts").sort_index()
        e1h = ema(h1_df["close"], 20)
        if len(e1h.dropna()) >= 4:
            cur = e1h.iloc[-1]
            prev = e1h.iloc[-4] if len(e1h) >= 4 else e1h.iloc[0]
            denom = abs(prev) if abs(prev) > 1e-9 else 1.0
            trend_1h = _safe((cur - prev) / denom)
        else:
            trend_1h = 0.0
    else:
        trend_1h = 0.0

    # 2. trend_1d — close_today vs EMA10_1d (use last closed prior day if today still open)
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

    # 3. range_width_1h — Donchian width on 1h
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

    # 4. liquidity_z — 5-trading-day volume z vs 30d (use daily)
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

    # 5,6. time-of-day sin/cos
    minute = _minute_of_session(target)
    angle = 2.0 * np.pi * (minute / max(_SESSION_MINUTES, 1))
    time_sin = float(np.sin(angle))
    time_cos = float(np.cos(angle))

    # 7-11. day-of-week one-hot (Mon=0..Fri=4)
    dow = target.weekday()
    dow_oh = [0.0] * 5
    if 0 <= dow <= 4:
        dow_oh[dow] = 1.0

    # 12. momentum_5d — close_today / close_(t-5 trading days) - 1
    if len(prior_days) >= 6:
        last5 = prior_days["close"].iloc[-1]
        prior5 = prior_days["close"].iloc[-6]
        if abs(prior5) > 1e-9:
            momentum_5d = _safe(last5 / prior5 - 1.0)
        else:
            momentum_5d = 0.0
    else:
        momentum_5d = 0.0

    vec = np.array(
        [
            vol_regime,
            trend_1h,
            trend_1d,
            range_width_1h,
            liquidity_z,
            time_sin,
            time_cos,
            *dow_oh,
            momentum_5d,
        ],
        dtype=float,
    )
    # final safety
    vec = np.where(np.isfinite(vec), vec, 0.0)
    return vec
