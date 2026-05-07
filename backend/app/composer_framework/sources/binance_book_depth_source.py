"""BinanceBookDepthSource — order book imbalance signal.

Hypothesis: 주문호가 imbalance + concentration는 즉시 유동성 정보 — futures
positioning과 다른 도메인. 한쪽 호가가 두꺼우면 그 방향 (price absorbing) 신호.
Top-of-book concentration이 줄면 fragility 증가 (cascade 직전 패턴).

Daily aggregated input (from backfill_book_depth.py):
  bid_depth_mean, ask_depth_mean, imbalance_mean, imbalance_std,
  near_imbalance_mean, far_imbalance_mean, top1_concentration_mean,
  imb_extreme_long_freq, imb_extreme_short_freq, snapshots

Output (prefix `bd_`):
  bd_imbalance_mean       — daily mean imbalance (-1 to +1)
  bd_imbalance_std        — intraday imbalance volatility
  bd_imbalance_5d_cum     — 5d cumulative
  bd_imbalance_20d_cum
  bd_imbalance_zscore_60d
  bd_near_imbalance       — top-of-book imbalance
  bd_far_imbalance        — deep book imbalance
  bd_imbalance_curve      — near - far (slope of imbalance vs depth)
  bd_top1_concentration   — fragility indicator
  bd_concentration_change_5d
  bd_extreme_imbalance_freq — daily fraction of intraday |imb|>0.2
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


def _build_book_depth_features(bd_daily: pd.DataFrame) -> pd.DataFrame:
    if bd_daily is None or bd_daily.empty:
        return pd.DataFrame()
    df = bd_daily.copy()

    out = pd.DataFrame(index=df.index)
    out["imbalance_mean"] = df["imbalance_mean"]
    out["imbalance_std"] = df["imbalance_std"]
    out["imbalance_5d_cum"] = df["imbalance_mean"].rolling(5, min_periods=2).sum()
    out["imbalance_20d_cum"] = df["imbalance_mean"].rolling(20, min_periods=5).sum()

    rmean = df["imbalance_mean"].rolling(60, min_periods=20).mean()
    rstd = df["imbalance_mean"].rolling(60, min_periods=20).std()
    out["imbalance_zscore_60d"] = (df["imbalance_mean"] - rmean) / rstd.replace(0, np.nan)

    out["near_imbalance"] = df["near_imbalance_mean"]
    out["far_imbalance"] = df["far_imbalance_mean"]
    out["imbalance_curve"] = df["near_imbalance_mean"] - df["far_imbalance_mean"]

    out["top1_concentration"] = df["top1_concentration_mean"]
    out["concentration_change_5d"] = df["top1_concentration_mean"].diff().rolling(5, min_periods=2).sum()

    out["extreme_long_freq"] = df["imb_extreme_long_freq"]
    out["extreme_short_freq"] = df["imb_extreme_short_freq"]
    out["extreme_net_freq"] = df["imb_extreme_long_freq"] - df["imb_extreme_short_freq"]
    return out


class BinanceBookDepthSource(SignalSource):
    name = "bookdepth"
    feature_prefix = "bd_"
    requires = ("ohlcv_eval",)

    def __init__(self, bd_daily: pd.DataFrame) -> None:
        self.bd_daily = bd_daily

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        if self.bd_daily is None or len(self.bd_daily) == 0:
            return pd.DataFrame(index=ctx.ohlcv_eval.index)

        daily = _build_book_depth_features(self.bd_daily)
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
