"""Rising Wedge (bear) and Falling Wedge (bull) — converging trendlines, both
sloping in the same direction.

Rising Wedge: both highs and lows trending up, but lows rising faster (converging).
              Often a bearish reversal/continuation.
Falling Wedge: both trending down, highs falling faster. Often bullish reversal.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import PatternDetector, PatternSignal
from ._helpers import atr_series, find_peaks_arr, find_troughs_arr, linreg_slope


class _WedgeBase(PatternDetector):
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 40

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 40,
            "peak_distance": 4,
            "prominence_atr_mult": 0.6,
            "min_slope_atr_mult": 0.05,    # both lines must slope at >=0.05 ATR/bar
            "min_slope_diff_atr_mult": 0.05,  # stricter convergence requirement
            "min_peaks": 3,                 # need ≥3 peaks/troughs for credible trend line
            "min_troughs": 3,
            "cooldown_bars": 10,
            "horizon_bars": 10,
        }


class RisingWedge(_WedgeBase):
    name = "rising_wedge"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        cooldown_until = -1
        for i in range(lb, len(df)):
            if i < cooldown_until:
                continue
            window = df.iloc[i - lb : i + 1]
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            highs = window["high"].to_numpy()
            lows = window["low"].to_numpy()
            prom = cur_atr * float(self.params["prominence_atr_mult"])
            peaks = find_peaks_arr(highs, prom, int(self.params["peak_distance"]))
            troughs = find_troughs_arr(lows, prom, int(self.params["peak_distance"]))
            if len(peaks) < int(self.params["min_peaks"]) or len(troughs) < int(self.params["min_troughs"]):
                continue
            sh, _ = linreg_slope(highs[peaks])
            sl, _ = linreg_slope(lows[troughs])
            min_slope = cur_atr * float(self.params["min_slope_atr_mult"])
            min_diff = cur_atr * float(self.params["min_slope_diff_atr_mult"])
            # both clearly positive, lows rising faster than highs (convergence)
            if not (sh > min_slope and sl > sh + min_diff):
                continue
            curr_close = float(window["close"].iloc[-1])
            support_now = float(window["low"].iloc[troughs[-1]])
            if curr_close >= support_now:
                continue
            cooldown_until = i + int(self.params["cooldown_bars"])
            ts = window.index[-1]
            base = max(0.0, min(1.0, 0.45 + 0.30 * min(1.0, (sl - sh) / cur_atr) + 0.25))
            height = float(window["high"].iloc[peaks[-1]] - lows[troughs[0]])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=curr_close - height,
                    suggested_stop=float(window["high"].iloc[peaks[-1]]),
                    metadata={"high_slope": float(sh), "low_slope": float(sl), "support": support_now},
                )
            )
        return signals


class FallingWedge(_WedgeBase):
    name = "falling_wedge"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        cooldown_until = -1
        for i in range(lb, len(df)):
            if i < cooldown_until:
                continue
            window = df.iloc[i - lb : i + 1]
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            highs = window["high"].to_numpy()
            lows = window["low"].to_numpy()
            prom = cur_atr * float(self.params["prominence_atr_mult"])
            peaks = find_peaks_arr(highs, prom, int(self.params["peak_distance"]))
            troughs = find_troughs_arr(lows, prom, int(self.params["peak_distance"]))
            if len(peaks) < int(self.params["min_peaks"]) or len(troughs) < int(self.params["min_troughs"]):
                continue
            sh, _ = linreg_slope(highs[peaks])
            sl, _ = linreg_slope(lows[troughs])
            min_slope = cur_atr * float(self.params["min_slope_atr_mult"])
            min_diff = cur_atr * float(self.params["min_slope_diff_atr_mult"])
            if not (sl < -min_slope and sh < sl - min_diff):
                continue
            curr_close = float(window["close"].iloc[-1])
            resistance_now = float(window["high"].iloc[peaks[-1]])
            if curr_close <= resistance_now:
                continue
            cooldown_until = i + int(self.params["cooldown_bars"])
            ts = window.index[-1]
            base = max(0.0, min(1.0, 0.45 + 0.30 * min(1.0, (sl - sh) / cur_atr) + 0.25))
            height = float(highs[peaks[0]] - window["low"].iloc[troughs[-1]])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=curr_close + height,
                    suggested_stop=float(window["low"].iloc[troughs[-1]]),
                    metadata={"high_slope": float(sh), "low_slope": float(sl), "resistance": resistance_now},
                )
            )
        return signals
