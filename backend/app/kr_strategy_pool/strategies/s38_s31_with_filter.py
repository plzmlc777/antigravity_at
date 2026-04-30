"""
S38 — S31 1m_period_x3 + AST mutation에서 발견된 best filter 결합.

S31의 5-of-5 confirmation은 강력하지만 기간 내 false positive 존재.
Filter 추가로 false positive 줄임:
  - f14_high_atr: 변동성 충분한 환경
  - f02_vol_above_20avg: 거래량 충분한 환경
  - f11_morning: 오전 시간대 (KR 시장 핵심)
"""
from typing import Any, ClassVar, Dict

import pandas as pd

from .s31_1m_variants import S31_1m_PeriodX3


class S38_S31_HighAtr(S31_1m_PeriodX3):
    """S31 + f14_high_atr (high-low 거래폭이 20봉 평균 위)."""
    name = "s38_s31_high_atr"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31_1m_PeriodX3.DEFAULT_PARAMS,
        "atr_lookback": 20,
    }

    def initialize(self) -> None:
        super().initialize()
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        high_low = df["high"] - df["low"]
        atr_avg = high_low.rolling(int(self.config["atr_lookback"])).mean()
        filter_pass = (high_low > atr_avg).fillna(False)
        self._filter_pass = dict(zip(df["timestamp"], filter_pass.values))

    def on_data(self, candle):
        # 청산은 그대로
        if self._has_position():
            super().on_data(candle)
            return
        # 진입 시 filter check
        ts = candle["timestamp"]
        if not self._filter_pass.get(ts, False):
            return
        super().on_data(candle)


class S38_S31_VolAbove20(S31_1m_PeriodX3):
    """S31 + f02_vol_above_20avg."""
    name = "s38_s31_vol_above_20"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31_1m_PeriodX3.DEFAULT_PARAMS,
        "vol_lookback": 20,
    }

    def initialize(self) -> None:
        super().initialize()
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        avg_vol = df["volume"].rolling(int(self.config["vol_lookback"])).mean()
        filter_pass = (df["volume"] > avg_vol).fillna(False)
        self._filter_pass = dict(zip(df["timestamp"], filter_pass.values))

    def on_data(self, candle):
        if self._has_position():
            super().on_data(candle)
            return
        ts = candle["timestamp"]
        if not self._filter_pass.get(ts, False):
            return
        super().on_data(candle)


class S38_S31_Morning(S31_1m_PeriodX3):
    """S31 + f11_morning (09:00-11:30)."""
    name = "s38_s31_morning"

    def initialize(self) -> None:
        super().initialize()
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["t_str"] = df["ts"].dt.strftime("%H:%M")
        filter_pass = (df["t_str"] >= "09:00") & (df["t_str"] < "11:30")
        self._filter_pass = dict(zip(df["timestamp"], filter_pass.values))

    def on_data(self, candle):
        if self._has_position():
            super().on_data(candle)
            return
        ts = candle["timestamp"]
        if not self._filter_pass.get(ts, False):
            return
        super().on_data(candle)


class S38_S31_AtrAndVol(S31_1m_PeriodX3):
    """S31 + (f14_high_atr AND f02_vol_above_20avg) — 두 filter 동시."""
    name = "s38_s31_atr_and_vol"

    def initialize(self) -> None:
        super().initialize()
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        high_low = df["high"] - df["low"]
        atr_avg = high_low.rolling(20).mean()
        atr_pass = (high_low > atr_avg).fillna(False)
        vol_avg = df["volume"].rolling(20).mean()
        vol_pass = (df["volume"] > vol_avg).fillna(False)
        filter_pass = atr_pass & vol_pass
        self._filter_pass = dict(zip(df["timestamp"], filter_pass.values))

    def on_data(self, candle):
        if self._has_position():
            super().on_data(candle)
            return
        ts = candle["timestamp"]
        if not self._filter_pass.get(ts, False):
            return
        super().on_data(candle)
