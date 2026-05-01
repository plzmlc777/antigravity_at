"""C52: 5m mean revert in low-vol regimes (NATR percentile filter) — Crypto port of S52."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import ema, natr
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class C52_NATR_Low_Revert_5m(MultiTFBase):
    name = "c52_natr_low_revert_5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "natr_period_5m": 14,
        "natr_window_5m": 80,
        "natr_max_pct": 0.35,
        "ema_period_5m": 20,
        "sl_pct": 0.012,
        "tp_pct": 0.018,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "natr_max_pct": {"type": "float", "min": 0.1, "max": 0.6},
        "natr_window_5m": {"type": "int", "min": 30, "max": 200},
        "ema_period_5m": {"type": "int", "min": 10, "max": 50},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_5m = resample_df(df_1m, "5min")
        n = natr(df_5m["high"], df_5m["low"], df_5m["close"],
                 int(self.config["natr_period_5m"]))
        w = int(self.config["natr_window_5m"])
        rank = n.rolling(w, min_periods=max(5, w // 4)).rank(pct=True)
        low_vol = rank <= float(self.config["natr_max_pct"])

        e5 = ema(df_5m["close"], int(self.config["ema_period_5m"]))
        sig_5m = pd.DataFrame({
            "buy": low_vol & (df_5m["close"] < e5),
            "sell": df_5m["close"] >= e5,
        })
        aligned = align_to_1m(sig_5m, df_1m.index, "5min")
        buy = aligned["buy"].fillna(False).values
        sell = aligned["sell"].fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
