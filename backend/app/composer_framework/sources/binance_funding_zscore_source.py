"""BinanceFundingZScoreSource — single z-score feature on raw 8h funding rate.

Hypothesis (Research Track paradigm `funding_carry`, R-3 PASS): when perpetual
futures funding rate enters an extreme regime, the crowded side typically
reverses — both because the funding flow drains the crowd's edge and because
extreme positioning precedes squeezes.

This source emits ONE feature: rolling z-score of `funding_rate` over the
last `lookback` 8h funding periods, mapped onto the eval index by funding-time.

Output (single column, prefix `bnfz_`):
  bnfz_zscore  — funding_rate z-score (rolling lookback periods)

Combine with `NegationPassthroughComposer` + `FundingReversalPolicy` to mirror
the rule-based reversal strategy validated in scripts/poc_funding_carry.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceFundingZScoreSource(SignalSource):
    name = "bnfz"
    feature_prefix = "bnfz_"
    requires = ("ohlcv_eval",)

    def __init__(self, funding_df: pd.DataFrame | None = None,
                 lookback: int = 30) -> None:
        self.funding_df = funding_df
        self.lookback = int(lookback)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        eval_idx = pd.to_datetime(ctx.ohlcv_eval.index)
        out = pd.DataFrame(index=eval_idx)

        if self.funding_df is None or len(self.funding_df) == 0:
            out["bnfz_zscore"] = np.nan
            return out

        f = self.funding_df.copy()
        f["funding_time"] = pd.to_datetime(f["funding_time"])
        f["funding_rate"] = pd.to_numeric(f["funding_rate"], errors="coerce")
        f = f.dropna(subset=["funding_time", "funding_rate"]).sort_values("funding_time")
        if f.empty:
            out["bnfz_zscore"] = np.nan
            return out

        # z-score on the 8h funding-rate series itself (NOT daily aggregated)
        rolling_mean = f["funding_rate"].rolling(self.lookback, min_periods=10).mean()
        rolling_std = f["funding_rate"].rolling(self.lookback, min_periods=10).std()
        z = (f["funding_rate"] - rolling_mean) / rolling_std.replace(0, np.nan)

        zseries = pd.Series(z.values, index=f["funding_time"].values)
        zseries = zseries[~zseries.index.duplicated(keep="last")].sort_index()

        # forward-fill onto eval index — at eval time t, the most recent
        # funding-period z-score (at funding_time <= t) is what's actionable.
        union_idx = pd.DatetimeIndex(sorted(set(zseries.index) | set(eval_idx)))
        ffilled = zseries.reindex(union_idx).ffill().reindex(eval_idx)
        out["bnfz_zscore"] = ffilled.values

        return out
