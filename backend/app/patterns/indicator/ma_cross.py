"""Golden Cross / Death Cross — moving-average crossover signals.

Golden Cross : fast MA crosses ABOVE slow MA (bullish, classic 50/200 daily).
Death Cross  : fast MA crosses BELOW slow MA (bearish).

We emit one signal per crossover bar (not every bar where fast > slow).
Confidence rises with:
  - separation acceleration (rate of fast-slow widening at cross)
  - trend strength (price > both MAs for golden, < both for death)
  - volume bonus (cross on above-avg volume)
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import PatternDetector, PatternSignal


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


class GoldenCross(PatternDetector):
    name = "golden_cross"
    category = "indicator"
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "fast_period": 20,
            "slow_period": 50,
            "use_ema": False,
            "vol_lookback": 20,
            "vol_bonus_mult": 1.2,
            "horizon_bars": 20,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        fast_n = int(self.params["fast_period"])
        slow_n = int(self.params["slow_period"])
        if self.params["use_ema"]:
            fast = _ema(df["close"], fast_n)
            slow = _ema(df["close"], slow_n)
        else:
            fast = df["close"].rolling(fast_n, min_periods=fast_n).mean()
            slow = df["close"].rolling(slow_n, min_periods=slow_n).mean()

        diff = fast - slow
        diff_prev = diff.shift(1)
        cross_up = (diff_prev <= 0) & (diff > 0)

        avg_v = df["volume"].rolling(int(self.params["vol_lookback"]), min_periods=1).mean()
        vol_bonus = df["volume"] > avg_v * float(self.params["vol_bonus_mult"])

        accel = diff - diff_prev
        accel_norm = (accel / df["close"].abs()).clip(-0.05, 0.05)

        signals: list[PatternSignal] = []
        for ts, is_cross in cross_up.items():
            if not bool(is_cross):
                continue
            close = float(df.loc[ts, "close"])
            f = float(fast.loc[ts])
            s = float(slow.loc[ts])
            base = 0.5
            base += 0.20 * min(1.0, max(0.0, float(accel_norm.loc[ts] or 0.0) / 0.01))
            if close > f and close > s:
                base += 0.15
            if bool(vol_bonus.loc[ts]):
                base += 0.15
            base = max(0.0, min(1.0, base))
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=float(s),
                    metadata={"fast_ma": f, "slow_ma": s, "close": close},
                )
            )
        return signals


class DeathCross(PatternDetector):
    name = "death_cross"
    category = "indicator"
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "fast_period": 20,
            "slow_period": 50,
            "use_ema": False,
            "vol_lookback": 20,
            "vol_bonus_mult": 1.2,
            "horizon_bars": 20,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        fast_n = int(self.params["fast_period"])
        slow_n = int(self.params["slow_period"])
        if self.params["use_ema"]:
            fast = _ema(df["close"], fast_n)
            slow = _ema(df["close"], slow_n)
        else:
            fast = df["close"].rolling(fast_n, min_periods=fast_n).mean()
            slow = df["close"].rolling(slow_n, min_periods=slow_n).mean()

        diff = fast - slow
        diff_prev = diff.shift(1)
        cross_down = (diff_prev >= 0) & (diff < 0)

        avg_v = df["volume"].rolling(int(self.params["vol_lookback"]), min_periods=1).mean()
        vol_bonus = df["volume"] > avg_v * float(self.params["vol_bonus_mult"])

        accel = diff - diff_prev
        accel_norm = (accel / df["close"].abs()).clip(-0.05, 0.05)

        signals: list[PatternSignal] = []
        for ts, is_cross in cross_down.items():
            if not bool(is_cross):
                continue
            close = float(df.loc[ts, "close"])
            f = float(fast.loc[ts])
            s = float(slow.loc[ts])
            base = 0.5
            base += 0.20 * min(1.0, max(0.0, -float(accel_norm.loc[ts] or 0.0) / 0.01))
            if close < f and close < s:
                base += 0.15
            if bool(vol_bonus.loc[ts]):
                base += 0.15
            base = max(0.0, min(1.0, base))
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=float(s),
                    metadata={"fast_ma": f, "slow_ma": s, "close": close},
                )
            )
        return signals
