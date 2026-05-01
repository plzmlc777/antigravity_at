"""C41: 5m BB lower revert + 1h EMA20 slope-up filter — Crypto port of S41."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import bollinger, ema
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class C41_BB_Trend_5m1h(MultiTFBase):
    name = "c41_bb_trend_5m1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "bb_period_5m": 25,
        "bb_std": 2.0,
        "ema_period_1h": 20,
        "ema_slope_lookback_1h": 3,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "bb_period_5m": {"type": "int", "min": 10, "max": 60},
        "bb_std": {"type": "float", "min": 1.5, "max": 3.0},
        "ema_period_1h": {"type": "int", "min": 10, "max": 50},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_5m = resample_df(df_1m, "5min")
        upper, mid, lower = bollinger(
            df_5m["close"], int(self.config["bb_period_5m"]), float(self.config["bb_std"]),
        )
        sig_5m = pd.DataFrame({
            "buy": df_5m["close"] < lower,
            "sell": df_5m["close"] > mid,
        })
        aligned_5m = align_to_1m(sig_5m, df_1m.index, "5min")

        df_1h = resample_df(df_1m, "60min")
        e1h = ema(df_1h["close"], int(self.config["ema_period_1h"]))
        slope_n = int(self.config["ema_slope_lookback_1h"])
        slope_up = e1h > e1h.shift(slope_n)
        sig_1h = pd.DataFrame({"trend_up": slope_up})
        aligned_1h = align_to_1m(sig_1h, df_1m.index, "60min")

        buy = (aligned_5m["buy"].fillna(False).values
               & aligned_1h["trend_up"].fillna(False).values)
        sell = aligned_5m["sell"].fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
