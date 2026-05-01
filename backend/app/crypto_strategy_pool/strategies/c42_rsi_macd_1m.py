"""C42: 1m RSI oversold + MACD bullish cross — Crypto port of S42."""
from typing import Any, ClassVar, Dict, List

import pandas as pd

from ..indicators import macd, rsi
from ..multi_tf_helpers import MultiTFBase


class C42_RSI_MACD_1m(MultiTFBase):
    name = "c42_rsi_macd_1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **MultiTFBase.DEFAULT_PARAMS,
        "rsi_period": 14,
        "rsi_oversold": 35.0,
        "rsi_overbought": 65.0,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "cross_window": 5,
    }
    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "rsi_period": {"type": "int", "min": 5, "max": 30},
        "rsi_oversold": {"type": "float", "min": 15, "max": 40},
        "rsi_overbought": {"type": "float", "min": 60, "max": 85},
        "cross_window": {"type": "int", "min": 1, "max": 10},
    }

    def _build_signals(self, df_1m: pd.DataFrame, feed_ts: List[str]) -> None:
        r = rsi(df_1m["close"], int(self.config["rsi_period"]))
        macd_line, signal_line, _ = macd(
            df_1m["close"],
            int(self.config["macd_fast"]),
            int(self.config["macd_slow"]),
            int(self.config["macd_signal"]),
        )
        diff = (macd_line - signal_line).fillna(0)
        bullish_cross = (diff > 0) & (diff.shift(1) <= 0)
        bearish_cross = (diff < 0) & (diff.shift(1) >= 0)

        w = int(self.config["cross_window"])
        recent_bull = bullish_cross.rolling(w, min_periods=1).max().fillna(0).astype(bool)
        recent_bear = bearish_cross.rolling(w, min_periods=1).max().fillna(0).astype(bool)

        buy = ((r < float(self.config["rsi_oversold"])) & recent_bull).fillna(False).values
        sell = ((r > float(self.config["rsi_overbought"])) | recent_bear).fillna(False).values
        self._buy = dict(zip(feed_ts, buy))
        self._sell = dict(zip(feed_ts, sell))
