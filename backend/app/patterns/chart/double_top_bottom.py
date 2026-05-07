"""Double Top / Double Bottom — 2-peak (or 2-trough) reversal patterns.

Algorithm:
  1. Find local extrema using scipy.signal.find_peaks with prominence + distance.
  2. Among recent peaks (last `lookback` bars), look for two peaks at similar
     price levels with a meaningful trough between them (or two troughs with a peak).
  3. Confirm by neckline break: for Double Top, current close < trough between peaks.
  4. Confidence: function of price-level similarity + trough depth + recency.

Suggested target = mirror of pattern height projected from neckline (classical TA).
Suggested stop  = the higher peak (DoubleTop) or lower trough (DoubleBottom).

We emit a signal at the bar where neckline break is confirmed (no look-ahead).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from ..base import PatternDetector, PatternSignal


def _find_extrema(series: np.ndarray, prominence: float, distance: int) -> np.ndarray:
    peaks, _ = find_peaks(series, prominence=prominence, distance=distance)
    return peaks


class DoubleTop(PatternDetector):
    name = "double_top"
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 60,
            "peak_distance": 5,
            "prominence_atr_mult": 1.0,    # peak prominence >= ATR
            "level_tolerance_pct": 0.02,   # two peaks within 2% of each other
            "min_trough_pct": 0.02,        # trough between peaks at least 2% below peak avg
            "horizon_bars": 10,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        params = self.params
        lookback = int(params["lookback"])
        if len(ohlcv) < lookback + 5:
            return []

        df = ohlcv
        # ATR proxy for prominence threshold
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14, min_periods=1).mean()

        signals: list[PatternSignal] = []

        for i in range(lookback, len(df)):
            window = df.iloc[i - lookback : i + 1]
            highs = window["high"].to_numpy()
            closes = window["close"].to_numpy()
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            prom = cur_atr * float(params["prominence_atr_mult"])
            peak_idx = _find_extrema(highs, prominence=prom, distance=int(params["peak_distance"]))
            if len(peak_idx) < 2:
                continue
            # take last two peaks
            p1, p2 = peak_idx[-2], peak_idx[-1]
            if p2 == len(window) - 1:
                # peak at last bar = no trough+break confirmation yet
                continue
            ph1, ph2 = highs[p1], highs[p2]
            level_diff = abs(ph1 - ph2) / max(ph1, ph2)
            if level_diff > float(params["level_tolerance_pct"]):
                continue
            trough_slice = window["low"].iloc[p1 : p2 + 1].to_numpy()
            trough_val = float(trough_slice.min())
            peak_avg = (ph1 + ph2) / 2.0
            trough_depth_pct = (peak_avg - trough_val) / peak_avg
            if trough_depth_pct < float(params["min_trough_pct"]):
                continue
            # neckline break confirmation: current close < trough_val
            curr_close = float(closes[-1])
            if curr_close >= trough_val:
                continue
            # confidence
            similarity = 1.0 - level_diff / float(params["level_tolerance_pct"])
            depth = min(1.0, trough_depth_pct / 0.10)  # 10% trough = max depth contribution
            conf = max(0.0, min(1.0, 0.4 + 0.4 * similarity + 0.2 * depth))
            # target = neckline - height_of_pattern
            height = peak_avg - trough_val
            target = trough_val - height
            stop = max(ph1, ph2)
            ts = window.index[-1]
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=conf,
                    horizon_bars=int(params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(stop),
                    metadata={
                        "peak1": float(ph1),
                        "peak2": float(ph2),
                        "neckline": float(trough_val),
                        "height": float(height),
                        "level_diff": float(level_diff),
                        "trough_depth_pct": float(trough_depth_pct),
                    },
                )
            )
        return signals


class DoubleBottom(PatternDetector):
    name = "double_bottom"
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 60,
            "peak_distance": 5,
            "prominence_atr_mult": 1.0,
            "level_tolerance_pct": 0.02,
            "min_peak_pct": 0.02,
            "horizon_bars": 10,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        params = self.params
        lookback = int(params["lookback"])
        if len(ohlcv) < lookback + 5:
            return []

        df = ohlcv
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(14, min_periods=1).mean()

        signals: list[PatternSignal] = []

        for i in range(lookback, len(df)):
            window = df.iloc[i - lookback : i + 1]
            lows = window["low"].to_numpy()
            closes = window["close"].to_numpy()
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            prom = cur_atr * float(params["prominence_atr_mult"])
            # invert lows to find troughs as peaks
            trough_idx = _find_extrema(-lows, prominence=prom, distance=int(params["peak_distance"]))
            if len(trough_idx) < 2:
                continue
            t1, t2 = trough_idx[-2], trough_idx[-1]
            if t2 == len(window) - 1:
                continue
            tv1, tv2 = lows[t1], lows[t2]
            level_diff = abs(tv1 - tv2) / max(tv1, tv2)
            if level_diff > float(params["level_tolerance_pct"]):
                continue
            peak_slice = window["high"].iloc[t1 : t2 + 1].to_numpy()
            peak_val = float(peak_slice.max())
            trough_avg = (tv1 + tv2) / 2.0
            peak_height_pct = (peak_val - trough_avg) / trough_avg
            if peak_height_pct < float(params["min_peak_pct"]):
                continue
            curr_close = float(closes[-1])
            if curr_close <= peak_val:
                continue
            similarity = 1.0 - level_diff / float(params["level_tolerance_pct"])
            height_score = min(1.0, peak_height_pct / 0.10)
            conf = max(0.0, min(1.0, 0.4 + 0.4 * similarity + 0.2 * height_score))
            height = peak_val - trough_avg
            target = peak_val + height
            stop = min(tv1, tv2)
            ts = window.index[-1]
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=conf,
                    horizon_bars=int(params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(stop),
                    metadata={
                        "trough1": float(tv1),
                        "trough2": float(tv2),
                        "neckline": float(peak_val),
                        "height": float(height),
                        "level_diff": float(level_diff),
                        "peak_height_pct": float(peak_height_pct),
                    },
                )
            )
        return signals
