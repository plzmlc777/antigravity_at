"""
S43: 1m Donchian breakout + 1h ATR rank filter.

Entry : 1m close > 20-bar prior high (Donchian upper)  AND
        1h ATR percentile rank over last `atr_rank_window` 1h bars >= atr_rank_min
Sell  : 1m close < Donchian mid

Hypothesis: 돌파 전략은 변동성이 충분할 때만 follow-through가 발생.
1h 시간대 ATR 분위가 낮으면 dead market — breakout 무력.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import atr, donchian
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class S43_Donchian_ATR_1m1h(MultiTFBase):
    name = "s43_donchian_atr_1m1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "donchian_period_1m": 20,
        "atr_period_1h": 14,
        "atr_rank_window_1h": 50,
        "atr_rank_min": 0.5,
        "sl_pct": 0.015,
        "tp_pct": 0.03,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "donchian_period_1m": {"type": "int", "min": 10, "max": 60},
        "atr_rank_window_1h": {"type": "int", "min": 20, "max": 200},
        "atr_rank_min": {"type": "float", "min": 0.2, "max": 0.9},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        upper, mid, lower = donchian(
            df_1m["high"], df_1m["low"], int(self.config["donchian_period_1m"]),
        )
        s_buy = (df_1m["close"] > upper).fillna(False)
        s_sell = (df_1m["close"] < mid).fillna(False)

        df_1h = resample_df(df_1m, "60min")
        a1h = atr(df_1h["high"], df_1h["low"], df_1h["close"],
                  int(self.config["atr_period_1h"]))
        win = int(self.config["atr_rank_window_1h"])
        rank = a1h.rolling(win, min_periods=max(5, win // 4)).rank(pct=True)
        atr_ok = (rank >= float(self.config["atr_rank_min"]))
        sig_1h = pd.DataFrame({"atr_ok": atr_ok})
        aligned = align_to_1m(sig_1h, df_1m.index, "60min")
        atr_ok_1m = aligned["atr_ok"].fillna(False).values

        buy = s_buy.values & atr_ok_1m
        sell = s_sell.values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
