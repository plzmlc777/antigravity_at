"""Stochastic %K/%D crossover signals.

Bull cross : %K crosses above %D in oversold zone (<20).
Bear cross : %K crosses below %D in overbought zone (>80).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


def _stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    low_min = df["low"].rolling(k_period, min_periods=k_period).min()
    high_max = df["high"].rolling(k_period, min_periods=k_period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(d_period, min_periods=1).mean()
    return k, d


class StochasticBullCross(PatternDetector):
    name = "stochastic_bull_cross"
    category = "indicator"
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "k_period": 14,
            "d_period": 3,
            "oversold": 20.0,
            "min_oversold_bars": 3,   # K must have been < oversold for >=N bars
            "cooldown_bars": 5,        # don't re-fire within N bars of last signal
            "horizon_bars": 7,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        k, d = _stochastic(df, int(self.params["k_period"]), int(self.params["d_period"]))
        diff = k - d
        cross_up = (diff.shift(1) <= 0) & (diff > 0)
        # Require BOTH k AND d to have been in oversold (stricter than OR), and
        # K below threshold for >= min_oversold_bars before cross.
        os = float(self.params["oversold"])
        n = int(self.params["min_oversold_bars"])
        was_deeply_oversold = (
            (k.shift(1) < os)
            & (d.shift(1) < os)
            & ((k < os).rolling(n, min_periods=n).sum() >= n).shift(1)
        )

        mask = (cross_up & was_deeply_oversold).fillna(False)
        # apply cooldown
        cooldown = int(self.params["cooldown_bars"])
        last_idx = -10**9
        for i, ts in enumerate(df.index):
            if bool(mask.loc[ts]) and i - last_idx < cooldown:
                mask.loc[ts] = False
            elif bool(mask.loc[ts]):
                last_idx = i
        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            kv = float(k.loc[ts])
            base = 0.45 + 0.35 * (1.0 - kv / 100.0) + 0.20  # deeper oversold = higher conf
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            low = float(df.loc[ts, "low"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=low,
                    metadata={"k": kv, "d": float(d.loc[ts])},
                )
            )
        return signals


class StochasticBearCross(PatternDetector):
    name = "stochastic_bear_cross"
    category = "indicator"
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "k_period": 14,
            "d_period": 3,
            "overbought": 80.0,
            "min_overbought_bars": 3,
            "cooldown_bars": 5,
            "horizon_bars": 7,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        k, d = _stochastic(df, int(self.params["k_period"]), int(self.params["d_period"]))
        diff = k - d
        cross_down = (diff.shift(1) >= 0) & (diff < 0)
        ob = float(self.params["overbought"])
        n = int(self.params["min_overbought_bars"])
        was_deeply_overbought = (
            (k.shift(1) > ob)
            & (d.shift(1) > ob)
            & ((k > ob).rolling(n, min_periods=n).sum() >= n).shift(1)
        )

        mask = (cross_down & was_deeply_overbought).fillna(False)
        cooldown = int(self.params["cooldown_bars"])
        last_idx = -10**9
        for i, ts in enumerate(df.index):
            if bool(mask.loc[ts]) and i - last_idx < cooldown:
                mask.loc[ts] = False
            elif bool(mask.loc[ts]):
                last_idx = i
        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            kv = float(k.loc[ts])
            base = 0.45 + 0.35 * (kv / 100.0) + 0.20
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            high = float(df.loc[ts, "high"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=high,
                    metadata={"k": kv, "d": float(d.loc[ts])},
                )
            )
        return signals
