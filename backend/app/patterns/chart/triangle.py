"""Triangle patterns: Ascending, Descending, Symmetrical.

Ascending Triangle: flat resistance + rising support → bull breakout (typical).
Descending Triangle: flat support + falling resistance → bear breakdown.
Symmetrical Triangle: both sides converging → directional breakout (sign of slope sum).

We fit linear regressions to local highs (resistance) and lows (support) over a
window, classify by slope signs, and emit a signal at breakout (close beyond
the converging apex line).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal
from ._helpers import atr_series, find_peaks_arr, find_troughs_arr, linreg_slope


def _classify_triangle(slope_high: float, slope_low: float, atr_unit: float) -> str | None:
    # Stricter thresholds — prior version misclassified random noise as
    # symmetrical/ascending too easily.
    flat_threshold = atr_unit * 0.02       # tighter "flat"
    sloping_threshold = atr_unit * 0.10    # must clearly slope to count
    high_flat = abs(slope_high) < flat_threshold
    low_flat = abs(slope_low) < flat_threshold
    if high_flat and slope_low > sloping_threshold:
        return "ascending"
    if low_flat and slope_high < -sloping_threshold:
        return "descending"
    if slope_high < -sloping_threshold and slope_low > sloping_threshold:
        return "symmetrical"
    return None


class _TriangleBase(PatternDetector):
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 40

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 40,
            "min_peaks": 2,
            "min_troughs": 2,
            "peak_distance": 4,
            "prominence_atr_mult": 0.6,
            "horizon_bars": 10,
        }

    def _common_fit(self, window: pd.DataFrame, cur_atr: float) -> tuple[float, float, np.ndarray, np.ndarray] | None:
        highs = window["high"].to_numpy()
        lows = window["low"].to_numpy()
        prom = cur_atr * float(self.params["prominence_atr_mult"])
        peaks = find_peaks_arr(highs, prom, int(self.params["peak_distance"]))
        troughs = find_troughs_arr(lows, prom, int(self.params["peak_distance"]))
        if len(peaks) < int(self.params["min_peaks"]) or len(troughs) < int(self.params["min_troughs"]):
            return None
        sh, _ = linreg_slope(highs[peaks])
        sl, _ = linreg_slope(lows[troughs])
        return sh, sl, peaks, troughs


class AscendingTriangle(_TriangleBase):
    name = "ascending_triangle"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        for i in range(lb, len(df)):
            window = df.iloc[i - lb : i + 1]
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            fit = self._common_fit(window, cur_atr)
            if fit is None:
                continue
            sh, sl, peaks, _ = fit
            kind = _classify_triangle(sh, sl, cur_atr)
            if kind != "ascending":
                continue
            resistance = float(window["high"].iloc[peaks].mean())
            curr_close = float(window["close"].iloc[-1])
            if curr_close <= resistance:
                continue
            ts = window.index[-1]
            base = 0.55 + 0.25 * min(1.0, sl / cur_atr) + 0.20
            base = max(0.0, min(1.0, base))
            height = resistance - float(window["low"].iloc[-30:].min())
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=resistance + height,
                    suggested_stop=resistance - height * 0.3,
                    metadata={"resistance": resistance, "support_slope": float(sl), "high_slope": float(sh)},
                )
            )
        return signals


class DescendingTriangle(_TriangleBase):
    name = "descending_triangle"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        for i in range(lb, len(df)):
            window = df.iloc[i - lb : i + 1]
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            fit = self._common_fit(window, cur_atr)
            if fit is None:
                continue
            sh, sl, _, troughs = fit
            kind = _classify_triangle(sh, sl, cur_atr)
            if kind != "descending":
                continue
            support = float(window["low"].iloc[troughs].mean())
            curr_close = float(window["close"].iloc[-1])
            if curr_close >= support:
                continue
            ts = window.index[-1]
            base = 0.55 + 0.25 * min(1.0, abs(sh) / cur_atr) + 0.20
            base = max(0.0, min(1.0, base))
            height = float(window["high"].iloc[-30:].max()) - support
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=support - height,
                    suggested_stop=support + height * 0.3,
                    metadata={"support": support, "resistance_slope": float(sh), "support_slope": float(sl)},
                )
            )
        return signals


class SymmetricalTriangle(_TriangleBase):
    name = "symmetrical_triangle"

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        for i in range(lb, len(df)):
            window = df.iloc[i - lb : i + 1]
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            fit = self._common_fit(window, cur_atr)
            if fit is None:
                continue
            sh, sl, peaks, troughs = fit
            kind = _classify_triangle(sh, sl, cur_atr)
            if kind != "symmetrical":
                continue
            resistance_now = float(window["high"].iloc[peaks].max())
            support_now = float(window["low"].iloc[troughs].min())
            curr_close = float(window["close"].iloc[-1])
            ts = window.index[-1]
            if curr_close > resistance_now * 0.999:
                direction = "bull"
                target = curr_close + (resistance_now - support_now)
                stop = (resistance_now + support_now) / 2.0
            elif curr_close < support_now * 1.001:
                direction = "bear"
                target = curr_close - (resistance_now - support_now)
                stop = (resistance_now + support_now) / 2.0
            else:
                continue
            base = max(0.0, min(1.0, 0.45 + 0.30 * min(1.0, (abs(sh) + abs(sl)) / cur_atr) + 0.25))
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction=direction,
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(stop),
                    metadata={"resistance": resistance_now, "support": support_now, "high_slope": float(sh), "low_slope": float(sl)},
                )
            )
        return signals
