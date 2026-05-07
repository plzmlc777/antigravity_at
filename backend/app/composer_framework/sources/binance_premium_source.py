"""BinancePremiumSource — Spot/Futures basis (premium index) cumulative signal.

Hypothesis: premium index = (mark_price - index_price) / index_price ≒ instant basis.
positive = futures premium (bullish hedger demand or speculative long pressure)
negative = futures discount (bearish or short-skewed)

KR Flow analogue: persistent basis drift = directional positioning by big players.
intraday premium spikes = liquidation/cascade events.

Difference from funding rate:
  - funding is 8h cumulative basis settlement (smooth)
  - premium is instant, with intraday OHLC granularity (volatile spikes captured)

Output (prefix `pr_`):
  pr_close              — daily close premium
  pr_high_low_range     — intraday premium range (spike indicator)
  pr_5d_cum             — 5d cumulative close
  pr_20d_cum            — 20d cumulative close
  pr_zscore_60d         — close zscore vs 60d
  pr_change_1d
  pr_change_5d_cum
  pr_pos_streak         — consecutive days of premium (capped ±10)
  pr_extreme_spike_freq — daily fraction with |open-close| > 2*60d_std (proxy)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_premium_features(prem_df: pd.DataFrame) -> pd.DataFrame:
    if prem_df is None or prem_df.empty:
        return pd.DataFrame()
    df = prem_df.copy()
    if "close" not in df.columns:
        return pd.DataFrame()
    for c in ("open", "high", "low", "close"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=df.index)
    out["close"] = df["close"]
    out["high_low_range"] = df["high"] - df["low"] if "high" in df.columns and "low" in df.columns else np.nan
    out["5d_cum"] = df["close"].rolling(5, min_periods=2).sum()
    out["20d_cum"] = df["close"].rolling(20, min_periods=5).sum()
    rmean = df["close"].rolling(60, min_periods=20).mean()
    rstd = df["close"].rolling(60, min_periods=20).std()
    out["zscore_60d"] = (df["close"] - rmean) / rstd.replace(0, np.nan)
    out["change_1d"] = df["close"].diff()
    out["change_5d_cum"] = out["change_1d"].rolling(5, min_periods=2).sum()

    pos_day = (df["close"] > 0).astype(int)
    streak = pos_day.copy()
    for i in range(1, len(streak)):
        if pos_day.iloc[i] == 1 and pos_day.iloc[i - 1] == 1:
            streak.iloc[i] = streak.iloc[i - 1] + 1
        elif pos_day.iloc[i] == 0 and pos_day.iloc[i - 1] == 0:
            streak.iloc[i] = streak.iloc[i - 1] - 1
    out["pos_streak"] = streak.clip(-10, 10)

    if "open" in df.columns:
        intraday_dev = (df["close"] - df["open"]).abs()
        thresh = rstd * 2.0
        out["extreme_spike_freq"] = (intraday_dev > thresh).rolling(5, min_periods=2).mean()

    return out


class BinancePremiumSource(SignalSource):
    name = "premium"
    feature_prefix = "pr_"
    requires = ("ohlcv_eval",)

    def __init__(self, premium_df: pd.DataFrame) -> None:
        self.premium_df = premium_df

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.premium_df is None or len(self.premium_df) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        daily = _build_premium_features(self.premium_df)
        if daily.empty:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        eval_norm = eval_idx.normalize()
        daily.index = pd.to_datetime(daily.index).normalize()
        daily = daily[~daily.index.duplicated(keep="last")]
        mapped = daily.reindex(
            pd.DatetimeIndex(sorted(set(daily.index) | set(eval_norm)))
        ).ffill().reindex(eval_norm)
        mapped.index = eval_idx
        return self._prefixed(mapped)
