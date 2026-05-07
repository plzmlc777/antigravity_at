"""Pin-bar family: Hammer, HangingMan, ShootingStar.

All three share geometry: small body, one long shadow >= 2x body, other shadow tiny.
Direction depends on body position + prior trend context.

  Hammer       : long lower shadow at downtrend bottom → bull reversal
  HangingMan   : long lower shadow at uptrend top    → bear reversal
  ShootingStar : long upper shadow at uptrend top    → bear reversal

Trend context approximated by close vs MA(20):
  - close < MA20  → "downtrend context" (favors Hammer)
  - close > MA20  → "uptrend context"   (favors HangingMan / ShootingStar)
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


def _pin_bar_components(df: pd.DataFrame):
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)
    lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
    return body, rng, upper_shadow, lower_shadow


class Hammer(PatternDetector):
    name = "hammer"
    category = "candle"
    min_bars = 25

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "min_lower_shadow_to_body": 2.0,
            "max_upper_shadow_to_body": 0.5,
            "trend_ma": 20,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body, rng, up, down = _pin_bar_components(df)
        ma = df["close"].rolling(int(self.params["trend_ma"]), min_periods=1).mean()
        body_safe = body.replace(0, np.nan)
        ls_ratio = down / body_safe
        us_ratio = up / body_safe
        mask = (
            (ls_ratio >= float(self.params["min_lower_shadow_to_body"]))
            & (us_ratio <= float(self.params["max_upper_shadow_to_body"]))
            & (df["close"] < ma)  # downtrend context
        ).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            r = float((down.loc[ts] / rng.loc[ts]) or 0.0)
            base = 0.45 + 0.35 * min(1.0, r / 0.7) + 0.20 * min(1.0, float((ls_ratio.loc[ts] or 0.0) / 4.0))
            base = max(0.0, min(1.0, base))
            high = float(df.loc[ts, "high"])
            low = float(df.loc[ts, "low"])
            close = float(df.loc[ts, "close"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close + (close - low) * 1.5,
                    suggested_stop=low,
                    metadata={"ls_ratio": float(ls_ratio.loc[ts] or 0), "high": high, "low": low},
                )
            )
        return signals


class HangingMan(PatternDetector):
    name = "hanging_man"
    category = "candle"
    min_bars = 25

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "min_lower_shadow_to_body": 2.0,
            "max_upper_shadow_to_body": 0.5,
            "trend_ma": 20,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body, rng, up, down = _pin_bar_components(df)
        ma = df["close"].rolling(int(self.params["trend_ma"]), min_periods=1).mean()
        body_safe = body.replace(0, np.nan)
        ls_ratio = down / body_safe
        us_ratio = up / body_safe
        mask = (
            (ls_ratio >= float(self.params["min_lower_shadow_to_body"]))
            & (us_ratio <= float(self.params["max_upper_shadow_to_body"]))
            & (df["close"] > ma)
        ).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            r = float((down.loc[ts] / rng.loc[ts]) or 0.0)
            base = 0.40 + 0.30 * min(1.0, r / 0.7) + 0.20 * min(1.0, float((ls_ratio.loc[ts] or 0.0) / 4.0))
            base = max(0.0, min(1.0, base))
            high = float(df.loc[ts, "high"])
            close = float(df.loc[ts, "close"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close - (high - close) * 1.5,
                    suggested_stop=high,
                    metadata={"ls_ratio": float(ls_ratio.loc[ts] or 0), "high": high},
                )
            )
        return signals


class ShootingStar(PatternDetector):
    name = "shooting_star"
    category = "candle"
    min_bars = 25

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "min_upper_shadow_to_body": 2.0,
            "max_lower_shadow_to_body": 0.5,
            "trend_ma": 20,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body, rng, up, down = _pin_bar_components(df)
        ma = df["close"].rolling(int(self.params["trend_ma"]), min_periods=1).mean()
        body_safe = body.replace(0, np.nan)
        ls_ratio = down / body_safe
        us_ratio = up / body_safe
        mask = (
            (us_ratio >= float(self.params["min_upper_shadow_to_body"]))
            & (ls_ratio <= float(self.params["max_lower_shadow_to_body"]))
            & (df["close"] > ma)
        ).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            r = float((up.loc[ts] / rng.loc[ts]) or 0.0)
            base = 0.45 + 0.35 * min(1.0, r / 0.7) + 0.20 * min(1.0, float((us_ratio.loc[ts] or 0.0) / 4.0))
            base = max(0.0, min(1.0, base))
            high = float(df.loc[ts, "high"])
            close = float(df.loc[ts, "close"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close - (high - close) * 1.5,
                    suggested_stop=high,
                    metadata={"us_ratio": float(us_ratio.loc[ts] or 0), "high": high},
                )
            )
        return signals
