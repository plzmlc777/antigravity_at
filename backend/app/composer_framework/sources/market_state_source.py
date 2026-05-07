"""MarketStateSource — recent returns, realized vol, volume z-score, day-of-week.

Same math as legacy `pattern_ml.features.build_feature_matrix` market block.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.composer_framework.signal_source import SignalSource, SourceContext


class MarketStateSource(SignalSource):
    name = "mkt"
    feature_prefix = "mkt_"
    requires = ("ohlcv_eval",)

    def build_features(self, ctx: SourceContext) -> pd.DataFrame:
        self._require(ctx, "ohlcv_eval")
        df = ctx.ohlcv_eval
        out = pd.DataFrame(index=df.index)
        close = df["close"].astype(float)
        out["ret_1"] = np.log(close / close.shift(1))
        out["ret_5"] = np.log(close / close.shift(5))
        out["ret_20"] = np.log(close / close.shift(20))
        out["vol_realized_5"] = out["ret_1"].rolling(5).std(ddof=0)
        out["vol_realized_20"] = out["ret_1"].rolling(20).std(ddof=0)
        if "volume" in df.columns:
            v = df["volume"].astype(float)
            out["vol_z"] = (v - v.rolling(20).mean()) / v.rolling(20).std(ddof=0).replace(0, np.nan)
        else:
            out["vol_z"] = 0.0
        out["dow"] = df.index.dayofweek
        return self._prefixed(out)
