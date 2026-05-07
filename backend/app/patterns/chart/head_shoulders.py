"""Head and Shoulders / Inverse H&S — 3-peak (3-trough) reversal patterns.

H&S:
  three peaks: shoulder1, head, shoulder2
  shoulder heights similar (within tolerance), head higher than both
  neckline = line through the two troughs between peaks
  signal at bar where close < neckline (breakdown confirmation)

Inverse H&S: mirror.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal
from ._helpers import atr_series, find_peaks_arr, find_troughs_arr


class HeadShoulders(PatternDetector):
    name = "head_shoulders"
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 50

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 80,
            "peak_distance": 5,
            "prominence_atr_mult": 1.0,
            "shoulder_tolerance_pct": 0.04,  # shoulders within 4% of each other
            "head_min_higher_pct": 0.02,     # head at least 2% above shoulders
            "horizon_bars": 15,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        for i in range(lb, len(df)):
            window = df.iloc[i - lb : i + 1]
            highs = window["high"].to_numpy()
            lows = window["low"].to_numpy()
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            prom = cur_atr * float(self.params["prominence_atr_mult"])
            peaks = find_peaks_arr(highs, prom, int(self.params["peak_distance"]))
            if len(peaks) < 3:
                continue
            ls, hd, rs = peaks[-3], peaks[-2], peaks[-1]
            if rs == len(window) - 1:
                continue
            ph_ls, ph_hd, ph_rs = highs[ls], highs[hd], highs[rs]
            if ph_hd <= max(ph_ls, ph_rs):
                continue
            if abs(ph_ls - ph_rs) / max(ph_ls, ph_rs) > float(self.params["shoulder_tolerance_pct"]):
                continue
            if (ph_hd - max(ph_ls, ph_rs)) / ph_hd < float(self.params["head_min_higher_pct"]):
                continue
            # neckline troughs (lows) between ls-hd and hd-rs
            t1 = ls + np.argmin(lows[ls:hd + 1])
            t2 = hd + np.argmin(lows[hd:rs + 1])
            tv1, tv2 = lows[t1], lows[t2]
            if t2 == t1:
                continue
            slope = (tv2 - tv1) / (t2 - t1)
            # neckline value at current bar (window index = len(window)-1)
            neck_now = tv2 + slope * (len(window) - 1 - t2)
            curr_close = float(window["close"].iloc[-1])
            if curr_close >= neck_now:
                continue
            ts = window.index[-1]
            shoulder_sim = 1.0 - abs(ph_ls - ph_rs) / max(ph_ls, ph_rs) / float(self.params["shoulder_tolerance_pct"])
            head_prom = (ph_hd - max(ph_ls, ph_rs)) / ph_hd
            conf = max(0.0, min(1.0, 0.4 + 0.3 * shoulder_sim + 0.3 * min(1.0, head_prom / 0.10)))
            height = ph_hd - min(tv1, tv2)
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=conf,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(neck_now - height),
                    suggested_stop=float(ph_hd),
                    metadata={
                        "left_shoulder": float(ph_ls),
                        "head": float(ph_hd),
                        "right_shoulder": float(ph_rs),
                        "neckline_now": float(neck_now),
                        "height": float(height),
                    },
                )
            )
        return signals


class InverseHeadShoulders(PatternDetector):
    name = "inverse_head_shoulders"
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 50

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 80,
            "peak_distance": 5,
            "prominence_atr_mult": 1.0,
            "shoulder_tolerance_pct": 0.04,
            "head_min_lower_pct": 0.02,
            "horizon_bars": 15,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        atr = atr_series(df, 14)
        lb = int(self.params["lookback"])
        signals: list[PatternSignal] = []
        for i in range(lb, len(df)):
            window = df.iloc[i - lb : i + 1]
            highs = window["high"].to_numpy()
            lows = window["low"].to_numpy()
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue
            prom = cur_atr * float(self.params["prominence_atr_mult"])
            troughs = find_troughs_arr(lows, prom, int(self.params["peak_distance"]))
            if len(troughs) < 3:
                continue
            ls, hd, rs = troughs[-3], troughs[-2], troughs[-1]
            if rs == len(window) - 1:
                continue
            tv_ls, tv_hd, tv_rs = lows[ls], lows[hd], lows[rs]
            if tv_hd >= min(tv_ls, tv_rs):
                continue
            if abs(tv_ls - tv_rs) / min(tv_ls, tv_rs) > float(self.params["shoulder_tolerance_pct"]):
                continue
            if (min(tv_ls, tv_rs) - tv_hd) / min(tv_ls, tv_rs) < float(self.params["head_min_lower_pct"]):
                continue
            p1 = ls + np.argmax(highs[ls:hd + 1])
            p2 = hd + np.argmax(highs[hd:rs + 1])
            ph1, ph2 = highs[p1], highs[p2]
            if p2 == p1:
                continue
            slope = (ph2 - ph1) / (p2 - p1)
            neck_now = ph2 + slope * (len(window) - 1 - p2)
            curr_close = float(window["close"].iloc[-1])
            if curr_close <= neck_now:
                continue
            ts = window.index[-1]
            shoulder_sim = 1.0 - abs(tv_ls - tv_rs) / min(tv_ls, tv_rs) / float(self.params["shoulder_tolerance_pct"])
            head_prom = (min(tv_ls, tv_rs) - tv_hd) / min(tv_ls, tv_rs)
            conf = max(0.0, min(1.0, 0.4 + 0.3 * shoulder_sim + 0.3 * min(1.0, head_prom / 0.10)))
            height = max(ph1, ph2) - tv_hd
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=conf,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(neck_now + height),
                    suggested_stop=float(tv_hd),
                    metadata={
                        "left_shoulder": float(tv_ls),
                        "head": float(tv_hd),
                        "right_shoulder": float(tv_rs),
                        "neckline_now": float(neck_now),
                        "height": float(height),
                    },
                )
            )
        return signals
