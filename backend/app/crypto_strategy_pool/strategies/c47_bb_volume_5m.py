"""C47: 5m BB lower revert + 5m volume z-score filter — Crypto port of S47."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import bollinger
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class C47_BB_Volume_5m(MultiTFBase):
    name = "c47_bb_volume_5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "bb_period_5m": 25,
        "bb_std": 2.0,
        "volz_window_5m": 60,
        "volz_min": 1.0,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "bb_period_5m": {"type": "int", "min": 10, "max": 60},
        "volz_window_5m": {"type": "int", "min": 20, "max": 200},
        "volz_min": {"type": "float", "min": 0.5, "max": 3.0},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_5m = resample_df(df_1m, "5min")
        upper, mid, lower = bollinger(
            df_5m["close"], int(self.config["bb_period_5m"]), float(self.config["bb_std"]),
        )
        w = int(self.config["volz_window_5m"])
        v = df_5m["volume"]
        v_mean = v.rolling(w, min_periods=max(5, w // 4)).mean()
        v_std = v.rolling(w, min_periods=max(5, w // 4)).std(ddof=0)
        v_z = (v - v_mean) / v_std.replace(0, pd.NA)
        vol_ok = v_z.fillna(0) >= float(self.config["volz_min"])

        sig_5m = pd.DataFrame({
            "buy": (df_5m["close"] < lower) & vol_ok,
            "sell": df_5m["close"] > mid,
        })
        aligned = align_to_1m(sig_5m, df_1m.index, "5min")
        buy = aligned["buy"].fillna(False).values
        sell = aligned["sell"].fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
