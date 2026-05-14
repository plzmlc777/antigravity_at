"""OHLCV resampling for the Pattern Scanner.

Wraps the existing `kr_strategy_pool.multi_tf_helpers.resample_df` with a
DatetimeIndex-friendly interface that PatternDetector expects.

Detectors require:
  - DatetimeIndex
  - columns: open, high, low, close, volume

Higher-TF resampling drops bars that don't have a complete (open, high, low,
close, volume) — i.e., the *last* bar may be partial; we drop it to be safe
(prevents detectors from acting on an incomplete bar).
"""
from __future__ import annotations

import pandas as pd

from app.kr_strategy_pool.multi_tf_helpers import _AGG
from .types import TF_TO_PANDAS_FREQ


def resample_ohlcv(df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample 1m OHLCV to the given timeframe.

    df_1m must have:
      - DatetimeIndex
      - columns: open, high, low, close, volume

    Returns a DataFrame with the same columns at the target timeframe, indexed
    by DatetimeIndex. Drops the final partial bar.
    """
    if not isinstance(df_1m.index, pd.DatetimeIndex):
        raise ValueError("df_1m must have a DatetimeIndex")
    if timeframe not in TF_TO_PANDAS_FREQ:
        raise ValueError(
            f"Unsupported timeframe: {timeframe}. "
            f"Supported: {list(TF_TO_PANDAS_FREQ)}"
        )

    if timeframe == "1m":
        # Pass through; ensure column subset and sort
        out = df_1m[list(_AGG.keys())].sort_index()
        return out

    freq = TF_TO_PANDAS_FREQ[timeframe]
    if freq == "1D":
        # Daily: group by calendar date
        df = df_1m.copy()
        df["_d"] = df.index.normalize()
        out = df.groupby("_d").agg(_AGG)
        out.index.name = None
    else:
        out = df_1m.resample(freq, origin="start_day").agg(_AGG)

    out = out.dropna(subset=["open"])

    # Drop the most recent bar if the input ended mid-bar.
    # Source 1m bars are timestamped at the START of their minute, so the LAST
    # 1m bar of a completed coarse bar has timestamp `next_bar_start - 1 minute`.
    # E.g., 5/12 daily bar is complete when df_1m includes a row at 5/12 23:59:00.
    # The previous implementation used `- 1 second`, which always evaluated the
    # final 1m bar (23:59:00) as "before" 23:59:59 and incorrectly dropped the
    # bar. This froze paper sessions one day behind whenever data ended on a
    # clean minute boundary (e.g., archive-based backfills).
    if len(out) >= 1:
        last_bar_start = out.index[-1]
        next_bar_start = last_bar_start + pd.Timedelta(freq) if freq != "1D" else (
            last_bar_start + pd.Timedelta(days=1)
        )
        if df_1m.index[-1] < next_bar_start - pd.Timedelta(minutes=1):
            out = out.iloc[:-1]

    return out
