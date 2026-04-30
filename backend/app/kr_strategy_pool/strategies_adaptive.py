"""
Volatility-Adaptive Position Sizing wrappers for Robust 5-pool.

Daily return 표준편차(15d rolling)에 따라 buy_size_pct를 동적으로 결정:
  vol < 2.0%  → 0.90 (LO)
  vol 2-4%    → 0.70 (MED)
  vol 4-6%    → 0.50 (HI)
  vol >= 6%   → 0.30 (very HI)

forward-leak 방지를 위해 어제까지 vol만 사용 (shift(1)).
"""
import pandas as pd

from .strategies_optimized import (
    S2OptBBReversion,
    S5OptVwapReversion,
    S16OptStochasticReversion,
    S25OptLunchFade,
)
from .strategies.s18_zscore_reversion import S18ZScoreReversion


class AdaptiveSizeMixin:
    """
    매 candle 진입 직전 buy_size_pct를 vol regime에 따라 동적으로 조정.
    부모 on_data가 self.config["buy_size_pct"]를 사용하므로 그 값을 갱신.
    """

    # (vol_threshold, size_pct) — vol < threshold 시 해당 size 적용
    SIZE_BY_VOL = [
        (2.0, 0.90),    # LO regime
        (4.0, 0.70),    # MED regime (default)
        (6.0, 0.50),    # HI regime
        (float("inf"), 0.30),  # very HI
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
        daily_vol_lag = daily_vol.shift(1).fillna(2.0)

        self._daily_vol = dict(zip(daily_vol_lag.index, daily_vol_lag))
        self._ts_to_day = dict(zip(df["timestamp"], df["day"]))

    def _adaptive_size_pct(self, ts: str) -> float:
        day = self._ts_to_day.get(ts)
        vol = self._daily_vol.get(day, 2.0)
        if pd.isna(vol):
            vol = 2.0
        for threshold, size in self.SIZE_BY_VOL:
            if vol < threshold:
                return size
        return 0.30

    def on_data(self, candle):
        # 진입 시 사용될 size를 vol regime에 따라 갱신
        self.config["buy_size_pct"] = self._adaptive_size_pct(candle["timestamp"])
        super().on_data(candle)


# Robust 5-pool adaptive wrappers
class S2BBAdaptive(AdaptiveSizeMixin, S2OptBBReversion):
    name = "s2_opt_bb_adaptive"


class S5VwapAdaptive(AdaptiveSizeMixin, S5OptVwapReversion):
    name = "s5_opt_vwap_adaptive"


class S16StochasticAdaptive(AdaptiveSizeMixin, S16OptStochasticReversion):
    name = "s16_opt_stochastic_adaptive"


class S18ZScoreAdaptive(AdaptiveSizeMixin, S18ZScoreReversion):
    name = "s18_zscore_adaptive"


class S25LunchFadeAdaptive(AdaptiveSizeMixin, S25OptLunchFade):
    name = "s25_opt_lunch_fade_adaptive"
