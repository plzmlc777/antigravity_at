"""Cup and Handle — rounded bottom (cup) followed by a short pullback (handle),
then breakout above the cup's right rim.

Quantitative criteria (William O'Neil-inspired, simplified):
  - Cup depth: 15~30% from rim to bottom
  - Cup duration: lookback_min~lookback_max bars
  - Handle: short pullback in the last handle_max_bars, depth max ~ cup_depth/3
  - Breakout: close > cup right rim
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


class CupAndHandle(PatternDetector):
    name = "cup_and_handle"
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "cup_min_bars": 30,
            "cup_max_bars": 130,
            "cup_depth_min": 0.10,
            "cup_depth_max": 0.35,
            "handle_max_bars": 15,
            "handle_max_depth_ratio": 0.5,  # handle depth <= cup_depth * 0.5
            "horizon_bars": 20,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        params = self.params
        signals: list[PatternSignal] = []
        cup_min = int(params["cup_min_bars"])
        cup_max = int(params["cup_max_bars"])
        h_max = int(params["handle_max_bars"])

        for i in range(cup_min + h_max, len(df)):
            best = None
            for cup_len in range(cup_min, min(cup_max, i - h_max) + 1, max(1, cup_min // 6)):
                cup_start_idx = i - h_max - cup_len
                if cup_start_idx < 0:
                    continue
                cup = df.iloc[cup_start_idx : i - h_max + 1]
                handle = df.iloc[i - h_max : i + 1]
                left_rim = cup["high"].iloc[:5].max()
                right_rim = cup["high"].iloc[-5:].max()
                rim = max(left_rim, right_rim)
                bottom = cup["low"].min()
                cup_depth = (rim - bottom) / rim
                if not (float(params["cup_depth_min"]) <= cup_depth <= float(params["cup_depth_max"])):
                    continue
                # rims approximately equal
                if abs(left_rim - right_rim) / rim > 0.05:
                    continue
                # rounded shape: bottom near middle of cup
                bottom_idx = cup["low"].values.argmin()
                pos = bottom_idx / len(cup)
                if not (0.30 <= pos <= 0.70):
                    continue
                # handle: shallow pullback
                handle_high = handle["high"].max()
                handle_low = handle["low"].min()
                handle_depth = (handle_high - handle_low) / handle_high
                if handle_depth > cup_depth * float(params["handle_max_depth_ratio"]):
                    continue
                # breakout: current close > rim
                curr_close = float(df["close"].iloc[i])
                if curr_close <= rim:
                    continue
                quality = (1.0 - abs(left_rim - right_rim) / rim / 0.05) * 0.4
                quality += min(1.0, cup_depth / 0.25) * 0.3
                quality += (1.0 - handle_depth / max(0.001, cup_depth * float(params["handle_max_depth_ratio"]))) * 0.3
                if best is None or quality > best[0]:
                    best = (quality, rim, bottom, cup_depth, handle_low, handle_depth)
            if best is None:
                continue
            quality, rim, bottom, cup_depth, handle_low, handle_depth = best
            base = max(0.0, min(1.0, 0.45 + 0.55 * quality))
            curr_close = float(df["close"].iloc[i])
            ts = df.index[i]
            target = rim + (rim - bottom)  # height of cup projected up
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(handle_low),
                    metadata={
                        "rim": float(rim),
                        "cup_bottom": float(bottom),
                        "cup_depth": float(cup_depth),
                        "handle_depth": float(handle_depth),
                    },
                )
            )
        return signals
