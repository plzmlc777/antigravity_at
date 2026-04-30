"""
S34: S31 1m_period_x3 + 외국인/기관 filter.

S31의 5-of-5 confirmation signal에 외국인+기관 데이터로 추가 필터:
  - 어제 외국인 순매수 양수 AND 기관 순매수 양수 → 진입 허용
  - 그 외에는 진입 차단 (청산은 그대로)

가설: 외국인+기관이 매수하는 시기 = mean reversion 시그널의 false positive 줄임

S33B 단독: OOS +8.03% / Sharpe 2.08
S31 단독: OOS +19.15% / Sharpe 5.42
S34 (결합): ?
"""
from typing import Any, ClassVar, Dict, Optional

import pandas as pd

from .s31_1m_variants import S31_1m_PeriodX3
from .s33_foreign_signal import compute_foreign_indicators, load_foreign_data


class S34_S31_PlusForeignBoth(S31_1m_PeriodX3):
    """S31 진입에 '어제 외국인+기관 둘 다 순매수 양수' filter 추가."""
    name = "s34_s31_plus_foreign_both"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31_1m_PeriodX3.DEFAULT_PARAMS,
    }

    def initialize(self) -> None:
        super().initialize()
        # foreign data 로드
        fdf = compute_foreign_indicators(load_foreign_data(self.symbol))
        # day → bool (어제 둘 다 양수)
        self._foreign_pass: Dict[str, bool] = {
            r["dt"]: bool(
                r["frgnr_yesterday_pos"] == 1 and r["orgn_yesterday_pos"] == 1
            )
            for _, r in fdf.iterrows()
        }

        # 1m feed의 ts → day 매핑
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        self._ts_to_day = dict(zip(df["timestamp"], df["ts"].dt.date.astype(str)))

    def on_data(self, candle):
        ts = candle["timestamp"]
        day = self._ts_to_day.get(ts, "")
        passes = self._foreign_pass.get(day, False)

        if self._has_position():
            # 청산은 그대로 (filter 무관)
            super().on_data(candle)
            return

        # 진입 시 filter 적용
        if not passes:
            return  # 진입 skip
        super().on_data(candle)


class S34_S31_PlusForeign5dCum(S31_1m_PeriodX3):
    """S31 진입에 '외국인 5일 누적 > N' filter 추가."""
    name = "s34_s31_plus_foreign_5d_cum"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31_1m_PeriodX3.DEFAULT_PARAMS,
        "min_frgnr_5d_cum": 0,
    }

    def initialize(self) -> None:
        super().initialize()
        fdf = compute_foreign_indicators(load_foreign_data(self.symbol))
        threshold = float(self.config["min_frgnr_5d_cum"])
        self._foreign_pass: Dict[str, bool] = {
            r["dt"]: bool(r["frgnr_5d_cum"] > threshold) for _, r in fdf.iterrows()
        }
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        self._ts_to_day = dict(zip(df["timestamp"], df["ts"].dt.date.astype(str)))

    def on_data(self, candle):
        ts = candle["timestamp"]
        day = self._ts_to_day.get(ts, "")
        passes = self._foreign_pass.get(day, False)

        if self._has_position():
            super().on_data(candle)
            return
        if not passes:
            return
        super().on_data(candle)


class S34_S31_PlusBigBuyersSum(S31_1m_PeriodX3):
    """S31 진입에 '외국인+기관 합산 어제 순매수 > N' filter."""
    name = "s34_s31_plus_big_buyers_sum"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31_1m_PeriodX3.DEFAULT_PARAMS,
        "min_sum": 1000,
    }

    def initialize(self) -> None:
        super().initialize()
        fdf = compute_foreign_indicators(load_foreign_data(self.symbol))
        threshold = float(self.config["min_sum"])
        self._foreign_pass: Dict[str, bool] = {
            r["dt"]: bool(r["frgnr_orgn_sum_yesterday"] > threshold)
            for _, r in fdf.iterrows()
        }
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        self._ts_to_day = dict(zip(df["timestamp"], df["ts"].dt.date.astype(str)))

    def on_data(self, candle):
        ts = candle["timestamp"]
        day = self._ts_to_day.get(ts, "")
        passes = self._foreign_pass.get(day, False)

        if self._has_position():
            super().on_data(candle)
            return
        if not passes:
            return
        super().on_data(candle)
