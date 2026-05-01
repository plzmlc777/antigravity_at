"""
S44: 1m EMA pullback + 10-14시 time window + 1h trend filter.

Entry : EMA50_1m < close < EMA20_1m   (close가 fast/slow EMA 사이 pullback zone)
        AND 10:00 <= time < 14:00      (장 초반/말미 noise 회피)
        AND 1h close > EMA50_1h        (대 추세 상승)
Sell  : 1m close < EMA50_1m            (pullback zone 이탈)

Hypothesis: 추세장 안에서 mid-day 시간대의 작은 pullback이 가장 안정적인
follow-through 진입. 장 시작/끝과 점심 직전은 회피.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import ema
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class S44_EMA_Time_1m1h(MultiTFBase):
    name = "s44_ema_time_1m1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "ema_fast_1m": 20,
        "ema_slow_1m": 50,
        "ema_trend_1h": 50,
        "time_start": "10:00",
        "time_end": "14:00",
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "ema_fast_1m": {"type": "int", "min": 5, "max": 50},
        "ema_slow_1m": {"type": "int", "min": 20, "max": 100},
        "ema_trend_1h": {"type": "int", "min": 20, "max": 100},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        e_fast = ema(df_1m["close"], int(self.config["ema_fast_1m"]))
        e_slow = ema(df_1m["close"], int(self.config["ema_slow_1m"]))
        in_zone = (df_1m["close"] < e_fast) & (df_1m["close"] > e_slow)
        below_slow = df_1m["close"] < e_slow

        t_str = df_1m.index.strftime("%H:%M").to_series(index=df_1m.index)
        in_window = (t_str >= str(self.config["time_start"])) & (t_str < str(self.config["time_end"]))

        df_1h = resample_df(df_1m, "60min")
        e1h = ema(df_1h["close"], int(self.config["ema_trend_1h"]))
        trend_up = df_1h["close"] > e1h
        sig_1h = pd.DataFrame({"trend_up": trend_up})
        aligned = align_to_1m(sig_1h, df_1m.index, "60min")
        trend_up_1m = aligned["trend_up"].fillna(False).values

        buy = (in_zone.values & in_window.values & trend_up_1m)
        sell = below_slow.values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
