"""
S31 Adaptive Confirmation — vol regime에 따라 min_buy_confirmations 동적 조정.

vol 작을 때(안정): 적극적 진입 (mb=3)
vol 보통: default (mb=4)
vol 높을 때(불안정): 보수적 진입 (mb=5)

이전 adaptive sizing 실패 (vol bin off + single-phase env) 교훈을 반영해
이 종목의 실제 daily vol 분포(2-4%)에 calibrated된 bin 사용.
"""
from typing import Any, ClassVar, Dict

import pandas as pd

from .s31_1m_variants import S31_1m_SamePeriod


class S31AdaptiveConfirmation(S31_1m_SamePeriod):
    """1m, period × 3, vol-adaptive mb."""
    name = "s31_adaptive_confirmation"
    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S31_1m_SamePeriod.DEFAULT_PARAMS,
        # period × 3 (1m_period_x3 best)
        "bb_period": 75,
        "stoch_k_period": 27,
        "z_period": 90,
        # static defaults (adaptive_mb override)
        "min_buy_confirmations": 4,
        "min_sell_confirmations": 1,
        "sl_pct": 0.025,
        "tp_pct": 0.03,
    }

    # (vol_threshold, mb) — vol < threshold 시 해당 mb 적용
    # 이 종목의 daily 15d std는 보통 2~4% — 그에 맞춘 calibration
    MB_BY_VOL = [
        (2.5, 3),    # LO regime — 적극
        (4.0, 4),    # MED regime (default)
        (float("inf"), 5),  # HI regime — 보수
    ]

    def initialize(self) -> None:
        super().initialize()
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df["day"] = df["ts"].dt.date.astype(str)

        daily_close = df.groupby("day")["close"].last()
        daily_ret = daily_close.pct_change() * 100
        daily_vol = daily_ret.rolling(15).std()
        # forward-leak 방지: 어제까지의 vol만 사용
        daily_vol_lag = daily_vol.shift(1).fillna(3.0)  # default MED

        self._daily_vol = dict(zip(daily_vol_lag.index, daily_vol_lag))
        self._ts_to_day = dict(zip(df["timestamp"], df["day"]))

    def _adaptive_mb(self, ts: str) -> int:
        day = self._ts_to_day.get(ts)
        vol = self._daily_vol.get(day, 3.0)
        if pd.isna(vol):
            vol = 3.0
        for threshold, mb in self.MB_BY_VOL:
            if vol < threshold:
                return mb
        return 5

    def on_data(self, candle):
        # 매 candle 진입 시 mb를 vol regime에 따라 갱신
        self.config["min_buy_confirmations"] = self._adaptive_mb(candle["timestamp"])
        super().on_data(candle)


class S31AdaptiveConfirmationSlow(S31AdaptiveConfirmation):
    """더 보수적 — LO=4, MED=5, HI=6 (모두 한 단계 더 strict)."""
    name = "s31_adaptive_confirmation_slow"
    MB_BY_VOL = [
        (2.5, 4),
        (4.0, 5),
        (float("inf"), 5),  # max는 5 (시그널 5개)
    ]


class S31AdaptiveConfirmationFast(S31AdaptiveConfirmation):
    """더 적극적 — LO=2, MED=3, HI=4."""
    name = "s31_adaptive_confirmation_fast"
    MB_BY_VOL = [
        (2.5, 2),
        (4.0, 3),
        (float("inf"), 4),
    ]
