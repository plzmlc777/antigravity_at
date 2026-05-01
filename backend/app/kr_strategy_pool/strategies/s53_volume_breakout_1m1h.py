"""
S53: 1m volume-confirmed breakout + 1h ADX filter.

Entry : 1m close > N-bar prior high (Donchian upper)
        AND  1m volume z-score (over window) >= volz_min   (volume confirms breakout)
        AND  1h ADX >= adx_min   (trend strength at higher TF)
Sell  : 1m close < Donchian mid

Hypothesis: dominant feature is vol_regime. This strategy is the explicit
high-vol counterpart to s52 — only triggers when (a) range expands beyond
recent base, (b) volume backs the move, (c) higher TF confirms a real trend.
False breakouts are the main failure mode; the volume z-filter screens them.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import adx, donchian
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class S53_Volume_Breakout_1m1h(MultiTFBase):
    name = "s53_volume_breakout_1m1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "donchian_period_1m": 20,
        "volz_window_1m": 60,
        "volz_min": 1.5,
        "adx_period_1h": 14,
        "adx_min": 18.0,
        "sl_pct": 0.015,
        "tp_pct": 0.035,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "donchian_period_1m": {"type": "int", "min": 10, "max": 60},
        "volz_min": {"type": "float", "min": 0.5, "max": 3.5},
        "adx_min": {"type": "float", "min": 10.0, "max": 35.0},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        upper, mid, lower = donchian(
            df_1m["high"], df_1m["low"], int(self.config["donchian_period_1m"]),
        )
        s_break = (df_1m["close"] > upper).fillna(False)
        s_sell = (df_1m["close"] < mid).fillna(False)

        v = df_1m["volume"]
        w = int(self.config["volz_window_1m"])
        v_mean = v.rolling(w, min_periods=max(5, w // 4)).mean()
        v_std = v.rolling(w, min_periods=max(5, w // 4)).std(ddof=0)
        v_z = ((v - v_mean) / v_std.replace(0, pd.NA)).fillna(0)
        vol_ok = v_z >= float(self.config["volz_min"])

        df_1h = resample_df(df_1m, "60min")
        a1h = adx(df_1h["high"], df_1h["low"], df_1h["close"],
                  int(self.config["adx_period_1h"]))
        sig_1h = pd.DataFrame({"adx_ok": a1h >= float(self.config["adx_min"])})
        aligned = align_to_1m(sig_1h, df_1m.index, "60min")
        adx_ok = aligned["adx_ok"].fillna(False).values

        buy = s_break.values & vol_ok.values & adx_ok
        sell = s_sell.values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
