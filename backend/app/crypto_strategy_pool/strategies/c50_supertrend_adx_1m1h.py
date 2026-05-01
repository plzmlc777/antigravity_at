"""C50: 1m Supertrend trend-follower + 1h ADX filter — Crypto port of S50."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import adx, supertrend
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class C50_Supertrend_ADX_1m1h(MultiTFBase):
    name = "c50_supertrend_adx_1m1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "st_period_1m": 10,
        "st_multiplier_1m": 3.0,
        "adx_period_1h": 14,
        "adx_min": 20.0,
        "sl_pct": 0.018,
        "tp_pct": 0.035,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "st_period_1m": {"type": "int", "min": 5, "max": 20},
        "st_multiplier_1m": {"type": "float", "min": 1.5, "max": 5.0},
        "adx_min": {"type": "float", "min": 10.0, "max": 40.0},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        st_val, st_dir = supertrend(
            df_1m["high"], df_1m["low"], df_1m["close"],
            int(self.config["st_period_1m"]), float(self.config["st_multiplier_1m"]),
        )
        prev_dir = st_dir.shift(1).fillna(-1)
        bull_flip = (st_dir == 1) & (prev_dir == -1)
        bear_flip = (st_dir == -1) & (prev_dir == 1)

        df_1h = resample_df(df_1m, "60min")
        a1h = adx(df_1h["high"], df_1h["low"], df_1h["close"],
                  int(self.config["adx_period_1h"]))
        sig_1h = pd.DataFrame({"adx_ok": a1h >= float(self.config["adx_min"])})
        aligned = align_to_1m(sig_1h, df_1m.index, "60min")
        adx_ok = aligned["adx_ok"].fillna(False).values

        buy = bull_flip.values & adx_ok
        sell = bear_flip.values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
