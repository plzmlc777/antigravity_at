"""BinanceAutocorrRegimeSource — autocorrelation regime + direction signal.

Hypothesis (Research Track paradigm `autocorr_regime`, R-3 PASS perm_p=0.000):
when rolling lag-1 autocorrelation of 5m returns enters extreme negative
territory (< -0.20), the market is in a mean-reverting regime. Recent N-bar
direction is then likely to fade. This source emits a discrete trade signal
suitable for a long/short threshold policy.

Output (single signal column, prefix `bnar_`):
  bnar_signal — discrete signal in {-1.0, 0.0, +1.0}:
    +1 → enter LONG (recent down move expected to revert up)
    -1 → enter SHORT (recent up move expected to revert down)
     0 → no signal (autocorr regime not extreme, OR trend regime if rev-only)
  bnar_acorr   — raw autocorr value (debug / ML fallback)
  bnar_dir_ret — recent N-bar return (debug)

Combine with `PassthroughComposer` (no negation) + `LongShortThresholdPolicy`
or `FundingReversalPolicy` (with exit_threshold=0 to disable mean-exit).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class BinanceAutocorrRegimeSource(SignalSource):
    name = "bn_autocorr_regime"
    feature_prefix = "bnar_"
    requires = ("ohlcv_eval",)

    def __init__(self, autocorr_window: int = 288, lag: int = 1,
                 rev_thresh: float = 0.20, trend_thresh: float = 0.20,
                 dir_lookback: int = 12, regime_filter: str = "rev_only") -> None:
        self.autocorr_window = int(autocorr_window)
        self.lag = int(lag)
        self.rev_thresh = float(rev_thresh)
        self.trend_thresh = float(trend_thresh)
        self.dir_lookback = int(dir_lookback)
        if regime_filter not in ("rev_only", "trend_only", "both"):
            raise ValueError(f"invalid regime_filter: {regime_filter}")
        self.regime_filter = regime_filter

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        ohlcv = ctx.ohlcv_eval
        close = ohlcv["close"].astype(float)

        ret = np.log(close / close.shift(1))
        acorr = ret.rolling(self.autocorr_window).corr(ret.shift(self.lag))
        dir_ret = close.pct_change(self.dir_lookback).shift(1)

        signal = pd.Series(0.0, index=ohlcv.index)
        if self.regime_filter in ("rev_only", "both"):
            mask_rev = (acorr < -self.rev_thresh) & dir_ret.notna() & (dir_ret != 0)
            # rev fade: dir up → SHORT (-1), dir down → LONG (+1)
            signal.loc[mask_rev] = -np.sign(dir_ret.loc[mask_rev])
        if self.regime_filter in ("trend_only", "both"):
            mask_trend = (acorr > self.trend_thresh) & dir_ret.notna() & (dir_ret != 0)
            # trend follow: dir up → LONG (+1), dir down → SHORT (-1)
            signal.loc[mask_trend] = np.sign(dir_ret.loc[mask_trend])

        out = pd.DataFrame(index=ohlcv.index)
        out["bnar_signal"] = signal.astype(float)
        out["bnar_acorr"] = acorr.astype(float)
        out["bnar_dir_ret"] = dir_ret.astype(float)
        return out
