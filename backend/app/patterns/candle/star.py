"""Morning Star (bull) and Evening Star (bear) — 3-bar reversal patterns.

Morning Star:
  bar -2: long bearish body
  bar -1: small body (gaps down or doji-like, low at/below bar -2 body bottom)
  bar  0: long bullish body, closes well into bar -2 body (>50%)

Evening Star: mirror.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import PatternDetector, PatternSignal


def _bodies(df: pd.DataFrame):
    return (df["close"] - df["open"]).abs()


class MorningStar(PatternDetector):
    name = "morning_star"
    category = "candle"
    min_bars = 23

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_first_body_to_avg": 1.2,
            "max_middle_body_to_first": 0.4,
            "min_third_close_into_first": 0.5,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        bodies = _bodies(df)
        avg_body = bodies.rolling(int(self.params["body_lookback"]), min_periods=1).mean()

        first_open = df["open"].shift(2)
        first_close = df["close"].shift(2)
        mid_open = df["open"].shift(1)
        mid_close = df["close"].shift(1)

        first_body = (first_close - first_open).abs()
        mid_body = (mid_close - mid_open).abs()
        curr_body = (df["close"] - df["open"]).abs()

        first_bear = first_close < first_open
        third_bull = df["close"] > df["open"]
        first_big = first_body >= avg_body.shift(2) * float(self.params["min_first_body_to_avg"])
        mid_small = mid_body <= first_body * float(self.params["max_middle_body_to_first"])

        first_body_top = first_open
        first_body_bottom = first_close
        first_body_mid = (first_open + first_close) / 2.0
        third_close_into = df["close"] >= first_body_mid - (first_open - first_close) * float(
            self.params["min_third_close_into_first"]
        )
        # Approximation: third close above middle of first bearish body
        third_close_into = df["close"] >= (first_open + first_close) / 2.0

        mask = (first_bear & third_bull & first_big & mid_small & third_close_into).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            ratio = float((curr_body.loc[ts] / first_body.loc[ts]) or 0.0)
            base = 0.55 + 0.25 * min(1.0, ratio) + 0.20 * (1.0 - float((mid_body.loc[ts] / first_body.loc[ts]) or 0.0))
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            low = float(df.loc[ts, "low"])
            high = float(df.loc[ts, "high"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close + (high - low) * 1.5,
                    suggested_stop=low,
                    metadata={"third_to_first_body_ratio": ratio},
                )
            )
        return signals


class EveningStar(PatternDetector):
    name = "evening_star"
    category = "candle"
    min_bars = 23

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_first_body_to_avg": 1.2,
            "max_middle_body_to_first": 0.4,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        bodies = _bodies(df)
        avg_body = bodies.rolling(int(self.params["body_lookback"]), min_periods=1).mean()

        first_open = df["open"].shift(2)
        first_close = df["close"].shift(2)
        mid_open = df["open"].shift(1)
        mid_close = df["close"].shift(1)

        first_body = (first_close - first_open).abs()
        mid_body = (mid_close - mid_open).abs()
        curr_body = (df["close"] - df["open"]).abs()

        first_bull = first_close > first_open
        third_bear = df["close"] < df["open"]
        first_big = first_body >= avg_body.shift(2) * float(self.params["min_first_body_to_avg"])
        mid_small = mid_body <= first_body * float(self.params["max_middle_body_to_first"])
        third_close_into = df["close"] <= (first_open + first_close) / 2.0

        mask = (first_bull & third_bear & first_big & mid_small & third_close_into).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            ratio = float((curr_body.loc[ts] / first_body.loc[ts]) or 0.0)
            base = 0.55 + 0.25 * min(1.0, ratio) + 0.20 * (1.0 - float((mid_body.loc[ts] / first_body.loc[ts]) or 0.0))
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            low = float(df.loc[ts, "low"])
            high = float(df.loc[ts, "high"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close - (high - low) * 1.5,
                    suggested_stop=high,
                    metadata={"third_to_first_body_ratio": ratio},
                )
            )
        return signals
