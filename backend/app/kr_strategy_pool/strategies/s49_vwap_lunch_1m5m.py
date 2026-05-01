"""
S49: 1m VWAP lunch-fade + 5m EMA20-below filter.

Entry : lunch_window 안에서 1m close < VWAP*(1-lband_pct) AND 5m close < 5m EMA20
Sell  : 1m close >= VWAP

Hypothesis: 점심대 (12:30-13:30) 거래량 감소로 인한 mean-revert가 한국장의 잘 알려진
inefficiency. 5m EMA20 below이면 회복 전 단기 약세 → revert magnitude 큼.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import ema, vwap_intraday
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class S49_VWAP_Lunch_1m5m(MultiTFBase):
    name = "s49_vwap_lunch_1m5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "vwap_lower_band_pct": 0.004,
        "lunch_start": "12:30",
        "lunch_end": "13:30",
        "ema_period_5m": 20,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "vwap_lower_band_pct": {"type": "float", "min": 0.001, "max": 0.015},
        "ema_period_5m": {"type": "int", "min": 10, "max": 50},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        vwap = vwap_intraday(
            df_1m["high"], df_1m["low"], df_1m["close"], df_1m["volume"], df_1m["day_id"],
        )
        lband = vwap * (1 - float(self.config["vwap_lower_band_pct"]))
        s_buy_raw = df_1m["close"] < lband
        s_sell = df_1m["close"] >= vwap

        t_str = df_1m.index.strftime("%H:%M").to_series(index=df_1m.index)
        in_lunch = (t_str >= str(self.config["lunch_start"])) & (t_str < str(self.config["lunch_end"]))

        df_5m = resample_df(df_1m, "5min")
        e5 = ema(df_5m["close"], int(self.config["ema_period_5m"]))
        sig_5m = pd.DataFrame({"below_ema": df_5m["close"] < e5})
        aligned = align_to_1m(sig_5m, df_1m.index, "5min")
        below_ema_5m = aligned["below_ema"].fillna(False).values

        buy = s_buy_raw.values & in_lunch.values & below_ema_5m
        sell = s_sell.values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
