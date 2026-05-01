"""
C40: 1m VWAP revert + 5m ATR filter — Crypto port of S40.

Entry : 1m close < VWAP*(1 - lband_pct)  AND  5m ATR/close >= atr_min_pct
Sell  : 1m close >= VWAP                 (or SL/TP/max_hold)

Hypothesis: VWAP-revert가 가짜 신호를 줄 수 있는 정체장에서는, 5m 변동성이
일정 수준 이상일 때만 진입하면 의미 있는 swing이 따라온다.
24/7 — VWAP은 UTC calendar day마다 reset.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import vwap_intraday, atr
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class C40_VWAP_ATR_1m5m(MultiTFBase):
    name = "c40_vwap_atr_1m5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "vwap_lower_band_pct": 0.005,
        "atr_period_5m": 14,
        "atr_min_pct": 0.003,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "vwap_lower_band_pct": {"type": "float", "min": 0.001, "max": 0.02},
        "atr_period_5m": {"type": "int", "min": 5, "max": 30},
        "atr_min_pct": {"type": "float", "min": 0.0005, "max": 0.01},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        vwap = vwap_intraday(
            df_1m["high"], df_1m["low"], df_1m["close"], df_1m["volume"], df_1m["day_id"],
        )
        lband = vwap * (1 - float(self.config["vwap_lower_band_pct"]))
        s_buy = (df_1m["close"] < lband).fillna(False)
        s_sell = (df_1m["close"] >= vwap).fillna(False)

        df_5m = resample_df(df_1m, "5min")
        a5 = atr(df_5m["high"], df_5m["low"], df_5m["close"],
                 int(self.config["atr_period_5m"]))
        atr_pct = a5 / df_5m["close"]
        sig_5m = pd.DataFrame({"atr_ok": atr_pct >= float(self.config["atr_min_pct"])})
        aligned = align_to_1m(sig_5m, df_1m.index, "5min")
        atr_ok = aligned["atr_ok"].fillna(False).values

        buy_final = s_buy.values & atr_ok
        sell_final = s_sell.values
        self._buy = dict(zip(feed_ts, buy_final))
        self._sell = dict(zip(feed_ts, sell_final))
