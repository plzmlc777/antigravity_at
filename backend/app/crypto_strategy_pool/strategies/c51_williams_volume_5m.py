"""C51: 5m Williams %R oversold revert + 5m volume z filter — Crypto port of S51."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import ema, williams_r
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class C51_Williams_Volume_5m(MultiTFBase):
    name = "c51_williams_volume_5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "wr_period_5m": 14,
        "oversold_thr": -80.0,
        "overbought_thr": -20.0,
        "volz_window_5m": 60,
        "volz_min": 0.5,
        "ema_break_5m": 20,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "wr_period_5m": {"type": "int", "min": 7, "max": 30},
        "oversold_thr": {"type": "float", "min": -95.0, "max": -65.0},
        "overbought_thr": {"type": "float", "min": -35.0, "max": -5.0},
        "volz_min": {"type": "float", "min": 0.0, "max": 2.5},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_5m = resample_df(df_1m, "5min")
        wr = williams_r(df_5m["high"], df_5m["low"], df_5m["close"],
                        int(self.config["wr_period_5m"]))
        v = df_5m["volume"]
        w = int(self.config["volz_window_5m"])
        v_mean = v.rolling(w, min_periods=max(5, w // 4)).mean()
        v_std = v.rolling(w, min_periods=max(5, w // 4)).std(ddof=0)
        v_z = ((v - v_mean) / v_std.replace(0, pd.NA)).fillna(0)
        vol_ok = v_z >= float(self.config["volz_min"])

        e5 = ema(df_5m["close"], int(self.config["ema_break_5m"]))
        sig_5m = pd.DataFrame({
            "buy": (wr < float(self.config["oversold_thr"])) & vol_ok,
            "sell": (wr > float(self.config["overbought_thr"]))
                    | (df_5m["close"] < e5),
        })
        aligned = align_to_1m(sig_5m, df_1m.index, "5min")
        buy = aligned["buy"].fillna(False).values
        sell = aligned["sell"].fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
