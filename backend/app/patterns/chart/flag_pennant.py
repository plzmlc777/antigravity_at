"""Flag and Pennant — short consolidation after a strong impulse, then breakout.

Bull Flag:
  1. Strong upward impulse (M bars, return >= threshold).
  2. Short consolidation (N bars), parallel downward channel.
  3. Breakout above channel resistance → bull continuation.

Bear Flag: mirror.
Pennant: same as flag but consolidation is converging (small symmetrical triangle).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal
from ._helpers import atr_series, linreg_slope


class _FlagBase(PatternDetector):
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "impulse_bars": 8,
            "consolidation_bars": 7,
            # 5% impulse over 8 bars never happens on 1m for liquid Korean
            # large-caps (silent in Phase-2 diagnosis). Lower to 1.5% so the
            # detector actually fires on intraday TFs; chart patterns naturally
            # scale with volatility — fitness learning will weight them.
            "min_impulse_pct": 0.015,
            "max_consolidation_pct": 0.04,
            "cooldown_bars": 15,
            "horizon_bars": 8,
        }


class BullFlag(_FlagBase):
    name = "bull_flag"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        m = int(self.params["impulse_bars"])
        n = int(self.params["consolidation_bars"])
        signals: list[PatternSignal] = []
        for i in range(m + n, len(df)):
            impulse = df.iloc[i - m - n : i - n + 1]
            cons = df.iloc[i - n : i + 1]
            imp_ret = (impulse["close"].iloc[-1] - impulse["close"].iloc[0]) / impulse["close"].iloc[0]
            if imp_ret < float(self.params["min_impulse_pct"]):
                continue
            cons_high = cons["high"].max()
            cons_low = cons["low"].min()
            cons_range_pct = (cons_high - cons_low) / cons_low
            if cons_range_pct > float(self.params["max_consolidation_pct"]):
                continue
            slope_high, _ = linreg_slope(cons["high"].to_numpy())
            slope_low, _ = linreg_slope(cons["low"].to_numpy())
            if not (slope_high <= 0 and slope_low <= 0):
                continue
            curr_close = float(df["close"].iloc[i])
            if curr_close <= cons_high:
                continue
            ts = df.index[i]
            base = 0.55 + 0.25 * min(1.0, imp_ret / 0.10) + 0.20 * (1.0 - cons_range_pct / float(self.params["max_consolidation_pct"]))
            base = max(0.0, min(1.0, base))
            target = curr_close + (impulse["close"].iloc[-1] - impulse["close"].iloc[0])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(cons_low),
                    metadata={"impulse_pct": float(imp_ret), "cons_range_pct": float(cons_range_pct)},
                )
            )
        return signals


class BearFlag(_FlagBase):
    name = "bear_flag"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        m = int(self.params["impulse_bars"])
        n = int(self.params["consolidation_bars"])
        signals: list[PatternSignal] = []
        for i in range(m + n, len(df)):
            impulse = df.iloc[i - m - n : i - n + 1]
            cons = df.iloc[i - n : i + 1]
            imp_ret = (impulse["close"].iloc[0] - impulse["close"].iloc[-1]) / impulse["close"].iloc[0]
            if imp_ret < float(self.params["min_impulse_pct"]):
                continue
            cons_high = cons["high"].max()
            cons_low = cons["low"].min()
            cons_range_pct = (cons_high - cons_low) / cons_low
            if cons_range_pct > float(self.params["max_consolidation_pct"]):
                continue
            slope_high, _ = linreg_slope(cons["high"].to_numpy())
            slope_low, _ = linreg_slope(cons["low"].to_numpy())
            if not (slope_high >= 0 and slope_low >= 0):
                continue
            curr_close = float(df["close"].iloc[i])
            if curr_close >= cons_low:
                continue
            ts = df.index[i]
            base = 0.55 + 0.25 * min(1.0, imp_ret / 0.10) + 0.20 * (1.0 - cons_range_pct / float(self.params["max_consolidation_pct"]))
            base = max(0.0, min(1.0, base))
            target = curr_close - (impulse["close"].iloc[0] - impulse["close"].iloc[-1])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(cons_high),
                    metadata={"impulse_pct": float(imp_ret), "cons_range_pct": float(cons_range_pct)},
                )
            )
        return signals


class Pennant(_FlagBase):
    name = "pennant"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        m = int(self.params["impulse_bars"])
        n = int(self.params["consolidation_bars"])
        signals: list[PatternSignal] = []
        for i in range(m + n, len(df)):
            impulse = df.iloc[i - m - n : i - n + 1]
            cons = df.iloc[i - n : i + 1]
            imp_ret_up = (impulse["close"].iloc[-1] - impulse["close"].iloc[0]) / impulse["close"].iloc[0]
            imp_ret_down = -imp_ret_up
            slope_high, _ = linreg_slope(cons["high"].to_numpy())
            slope_low, _ = linreg_slope(cons["low"].to_numpy())
            # converging: slopes have opposite signs (high down, low up)
            if not (slope_high < 0 and slope_low > 0):
                continue
            cons_high = cons["high"].max()
            cons_low = cons["low"].min()
            curr_close = float(df["close"].iloc[i])
            ts = df.index[i]
            if imp_ret_up >= float(self.params["min_impulse_pct"]) and curr_close > cons_high:
                direction, target, stop = "bull", curr_close + (impulse["close"].iloc[-1] - impulse["close"].iloc[0]), float(cons_low)
                imp_ret = imp_ret_up
            elif imp_ret_down >= float(self.params["min_impulse_pct"]) and curr_close < cons_low:
                direction, target, stop = "bear", curr_close - (impulse["close"].iloc[0] - impulse["close"].iloc[-1]), float(cons_high)
                imp_ret = imp_ret_down
            else:
                continue
            base = max(0.0, min(1.0, 0.50 + 0.25 * min(1.0, imp_ret / 0.10) + 0.25))
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction=direction,
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(stop),
                    metadata={"impulse_pct": float(imp_ret), "high_slope": float(slope_high), "low_slope": float(slope_low)},
                )
            )
        return signals
