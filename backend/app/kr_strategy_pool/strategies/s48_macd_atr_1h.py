"""
S48: 1h MACD bullish cross + 1h ATR rank filter (slow trend follower, single-TF).

Entry : 1h MACD bullish cross within `cross_window_1h` bars AND 1h ATR rank >= atr_rank_min
Sell  : 1h MACD bearish cross

Hypothesis: 1시간대 MACD turn-around는 swing trade level의 의미 있는
모멘텀 변화. 변동성 보장된 환경(ATR rank ≥ 50%)일 때만 follow-through.
거래 빈도는 낮지만 winner 비중이 큼.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import atr, macd
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class S48_MACD_ATR_1h(MultiTFBase):
    name = "s48_macd_atr_1h"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "macd_fast_1h": 12,
        "macd_slow_1h": 26,
        "macd_signal_1h": 9,
        "atr_period_1h": 14,
        "atr_rank_window_1h": 50,
        "atr_rank_min": 0.5,
        "cross_window_1h": 4,
        "sl_pct": 0.025,
        "tp_pct": 0.04,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "atr_rank_min": {"type": "float", "min": 0.2, "max": 0.9},
        "cross_window_1h": {"type": "int", "min": 1, "max": 5},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_1h = resample_df(df_1m, "60min")
        macd_line, signal_line, _ = macd(
            df_1h["close"],
            int(self.config["macd_fast_1h"]),
            int(self.config["macd_slow_1h"]),
            int(self.config["macd_signal_1h"]),
        )
        diff = (macd_line - signal_line).fillna(0)
        bull_cross = (diff > 0) & (diff.shift(1) <= 0)
        bear_cross = (diff < 0) & (diff.shift(1) >= 0)
        w = int(self.config["cross_window_1h"])
        recent_bull = bull_cross.rolling(w, min_periods=1).max().fillna(0).astype(bool)

        a1h = atr(df_1h["high"], df_1h["low"], df_1h["close"],
                  int(self.config["atr_period_1h"]))
        rw = int(self.config["atr_rank_window_1h"])
        rank = a1h.rolling(rw, min_periods=max(5, rw // 4)).rank(pct=True)
        atr_ok = rank >= float(self.config["atr_rank_min"])

        sig_1h = pd.DataFrame({"buy": recent_bull & atr_ok, "sell": bear_cross})
        aligned = align_to_1m(sig_1h, df_1m.index, "60min")
        buy = aligned["buy"].fillna(False).values
        sell = aligned["sell"].fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
