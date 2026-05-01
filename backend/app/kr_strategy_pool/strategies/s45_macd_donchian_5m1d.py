"""
S45: 5m MACD bullish cross + 1d Donchian-mid filter.

Entry : 5m MACD line crosses above signal (cross_window 내) AND
        most recent closed 1d close >= Donchian mid (20-day high+low) / 2
Sell  : 5m MACD bearish cross

Hypothesis: 일봉 단기 range의 중간점 위에 있다 = 단기 약세 아님.
거기서 5m 모멘텀 전환이 발생하면 의미 있는 entry.
"""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import donchian, macd
from ..multi_tf_helpers import MultiTFBase, align_to_1m, resample_df


class S45_MACD_Donchian_5m1d(MultiTFBase):
    name = "s45_macd_donchian_5m1d"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "macd_fast_5m": 12,
        "macd_slow_5m": 26,
        "macd_signal_5m": 9,
        "donchian_period_1d": 20,
        "cross_window_5m": 4,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "donchian_period_1d": {"type": "int", "min": 10, "max": 60},
        "cross_window_5m": {"type": "int", "min": 1, "max": 5},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        df_5m = resample_df(df_1m, "5min")
        macd_line, signal_line, _ = macd(
            df_5m["close"],
            int(self.config["macd_fast_5m"]),
            int(self.config["macd_slow_5m"]),
            int(self.config["macd_signal_5m"]),
        )
        diff = (macd_line - signal_line).fillna(0)
        bull_cross = (diff > 0) & (diff.shift(1) <= 0)
        bear_cross = (diff < 0) & (diff.shift(1) >= 0)
        w = int(self.config["cross_window_5m"])
        recent_bull = bull_cross.rolling(w, min_periods=1).max().fillna(0).astype(bool)
        sig_5m = pd.DataFrame({"buy": recent_bull, "sell": bear_cross})
        aligned_5m = align_to_1m(sig_5m, df_1m.index, "5min")

        df_1d = resample_df(df_1m, "1D")
        upper, mid, lower = donchian(
            df_1d["high"], df_1d["low"], int(self.config["donchian_period_1d"]),
        )
        sig_1d = pd.DataFrame({"above_mid": df_1d["close"] >= mid})
        aligned_1d = align_to_1m(sig_1d, df_1m.index, "1D")

        buy = (aligned_5m["buy"].fillna(False).values
               & aligned_1d["above_mid"].fillna(False).values)
        sell = aligned_5m["sell"].fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
