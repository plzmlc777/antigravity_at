"""Bollinger Band patterns: Squeeze (low vol → coiled spring) + Breakout.

Squeeze: BBWidth (= (UB-LB)/MB) hits a multi-bar low — neutral signal of
         imminent volatility expansion, direction TBD.
Breakout: close crosses above UB (bull) or below LB (bear) AFTER a recent squeeze.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import PatternDetector, PatternSignal


def _bollinger(close: pd.Series, period: int = 20, std_mult: float = 2.0):
    mid = close.rolling(period, min_periods=period).mean()
    sd = close.rolling(period, min_periods=period).std(ddof=0)
    ub = mid + std_mult * sd
    lb = mid - std_mult * sd
    return ub, mid, lb


class BollingerSqueeze(PatternDetector):
    name = "bollinger_squeeze"
    category = "indicator"
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "period": 20,
            "std_mult": 2.0,
            "squeeze_lookback": 100,
            "min_squeeze_persist_bars": 5,  # squeeze must hold for ≥N bars
            "cooldown_bars": 30,            # don't re-fire within 30 bars
            "horizon_bars": 10,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        ub, mid, lb = _bollinger(df["close"], int(self.params["period"]), float(self.params["std_mult"]))
        width = (ub - lb) / mid
        roll_min = width.rolling(int(self.params["squeeze_lookback"]), min_periods=20).min()
        is_squeeze = (width <= roll_min * 1.01).fillna(False)

        # require squeeze to persist for N consecutive bars before emitting
        n = int(self.params["min_squeeze_persist_bars"])
        persisted = is_squeeze.rolling(n, min_periods=n).sum() >= n

        # emit only at the bar persistence is first reached (with cooldown)
        prev_persisted = persisted.shift(1, fill_value=False)
        candidate = persisted & ~prev_persisted

        signals: list[PatternSignal] = []
        cooldown = int(self.params["cooldown_bars"])
        last_idx = -10**9
        for i, ts in enumerate(df.index):
            if not bool(candidate.loc[ts]):
                continue
            if i - last_idx < cooldown:
                continue
            last_idx = i
            w = float(width.loc[ts])
            rmin = float(roll_min.loc[ts]) if not pd.isna(roll_min.loc[ts]) else w
            # confidence: how much tighter than typical the squeeze is
            tightness = 1.0 - min(1.0, w / 0.05)
            base = 0.40 + 0.50 * tightness
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="neutral",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=None,
                    metadata={"width": w, "close": close, "ub": float(ub.loc[ts]), "lb": float(lb.loc[ts])},
                )
            )
        return signals


class BollingerBreakout(PatternDetector):
    name = "bollinger_breakout"
    category = "indicator"
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "period": 20,
            "std_mult": 2.0,
            "squeeze_lookback": 50,
            "max_bars_since_squeeze": 10,
            "horizon_bars": 10,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        ub, mid, lb = _bollinger(df["close"], int(self.params["period"]), float(self.params["std_mult"]))
        width = (ub - lb) / mid
        roll_min = width.rolling(int(self.params["squeeze_lookback"]), min_periods=10).min()
        is_squeeze = width <= roll_min * 1.01

        # bars since squeeze
        recently_squeezed = is_squeeze.rolling(
            int(self.params["max_bars_since_squeeze"]), min_periods=1
        ).max().astype(bool)

        cross_up = (df["close"].shift(1) <= ub.shift(1)) & (df["close"] > ub)
        cross_down = (df["close"].shift(1) >= lb.shift(1)) & (df["close"] < lb)

        signals: list[PatternSignal] = []
        for ts in df.index:
            if not bool(recently_squeezed.get(ts, False)):
                continue
            close = float(df.loc[ts, "close"])
            mid_v = float(mid.loc[ts]) if not pd.isna(mid.loc[ts]) else close
            if bool(cross_up.get(ts, False)):
                base = 0.55 + 0.25 * min(1.0, (close - float(ub.loc[ts])) / mid_v / 0.01)
                base = max(0.0, min(1.0, base))
                signals.append(
                    PatternSignal(
                        pattern_name=self.name,
                        timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                        direction="bull",
                        confidence=base,
                        horizon_bars=int(self.params["horizon_bars"]),
                        suggested_target=close + (float(ub.loc[ts]) - float(lb.loc[ts])),
                        suggested_stop=mid_v,
                        metadata={"side": "upper", "ub": float(ub.loc[ts]), "lb": float(lb.loc[ts])},
                    )
                )
            elif bool(cross_down.get(ts, False)):
                base = 0.55 + 0.25 * min(1.0, (float(lb.loc[ts]) - close) / mid_v / 0.01)
                base = max(0.0, min(1.0, base))
                signals.append(
                    PatternSignal(
                        pattern_name=self.name,
                        timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                        direction="bear",
                        confidence=base,
                        horizon_bars=int(self.params["horizon_bars"]),
                        suggested_target=close - (float(ub.loc[ts]) - float(lb.loc[ts])),
                        suggested_stop=mid_v,
                        metadata={"side": "lower", "ub": float(ub.loc[ts]), "lb": float(lb.loc[ts])},
                    )
                )
        return signals
