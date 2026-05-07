"""Piercing Line (bull) / Dark Cloud Cover (bear) — 2-bar reversal patterns.

Piercing Line:
  prev: long bearish bar
  curr: opens below prev low, closes above midpoint of prev body (but below prev open)

Dark Cloud Cover: mirror.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import PatternDetector, PatternSignal


class PiercingLine(PatternDetector):
    name = "piercing_line"
    category = "candle"
    min_bars = 22

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_prev_body_to_avg": 1.0,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body = (df["close"] - df["open"]).abs()
        avg_body = body.rolling(int(self.params["body_lookback"]), min_periods=1).mean()

        prev_o = df["open"].shift(1)
        prev_c = df["close"].shift(1)
        prev_low = df["low"].shift(1)
        prev_body = (prev_o - prev_c).abs()

        prev_bear = prev_c < prev_o
        big_prev = prev_body >= avg_body.shift(1) * float(self.params["min_prev_body_to_avg"])
        gap_below = df["open"] < prev_low
        bull_now = df["close"] > df["open"]
        midpoint = (prev_o + prev_c) / 2.0
        close_above_mid = (df["close"] > midpoint) & (df["close"] < prev_o)

        mask = (prev_bear & big_prev & gap_below & bull_now & close_above_mid).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            close = float(df.loc[ts, "close"])
            low = float(df.loc[ts, "low"])
            penetration = float((close - midpoint.loc[ts]) / prev_body.loc[ts]) if prev_body.loc[ts] > 0 else 0.0
            base = 0.50 + 0.30 * min(1.0, penetration) + 0.20
            base = max(0.0, min(1.0, base))
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close + (close - low) * 1.5,
                    suggested_stop=low,
                    metadata={"penetration_ratio": penetration},
                )
            )
        return signals


class DarkCloudCover(PatternDetector):
    name = "dark_cloud_cover"
    category = "candle"
    min_bars = 22

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_prev_body_to_avg": 1.0,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body = (df["close"] - df["open"]).abs()
        avg_body = body.rolling(int(self.params["body_lookback"]), min_periods=1).mean()

        prev_o = df["open"].shift(1)
        prev_c = df["close"].shift(1)
        prev_high = df["high"].shift(1)
        prev_body = (prev_c - prev_o).abs()

        prev_bull = prev_c > prev_o
        big_prev = prev_body >= avg_body.shift(1) * float(self.params["min_prev_body_to_avg"])
        gap_above = df["open"] > prev_high
        bear_now = df["close"] < df["open"]
        midpoint = (prev_o + prev_c) / 2.0
        close_below_mid = (df["close"] < midpoint) & (df["close"] > prev_o)

        mask = (prev_bull & big_prev & gap_above & bear_now & close_below_mid).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            close = float(df.loc[ts, "close"])
            high = float(df.loc[ts, "high"])
            penetration = float((midpoint.loc[ts] - close) / prev_body.loc[ts]) if prev_body.loc[ts] > 0 else 0.0
            base = 0.50 + 0.30 * min(1.0, penetration) + 0.20
            base = max(0.0, min(1.0, base))
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close - (high - close) * 1.5,
                    suggested_stop=high,
                    metadata={"penetration_ratio": penetration},
                )
            )
        return signals
