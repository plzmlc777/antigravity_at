"""VWAP Reclaim / Reject — intraday volume-weighted average price interactions.

VWAP Reclaim : price was below VWAP, then closes back above it on rising volume → bull.
VWAP Reject  : price was above VWAP, then closes back below it on rising volume → bear.

VWAP is computed cumulatively per session (per calendar date in the index).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]
    # group by date
    date_key = df.index.date if hasattr(df.index, "date") else df.index
    cum_pv = pd.Series(pv.values, index=df.index).groupby(date_key).cumsum()
    cum_v = df["volume"].groupby(date_key).cumsum()
    return cum_pv / cum_v.replace(0, np.nan)


class VWAPReclaim(PatternDetector):
    name = "vwap_reclaim"
    category = "volume"
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "vol_lookback": 20,
            "min_vol_ratio": 1.2,
            "min_bars_below": 3,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        vwap = _session_vwap(df)
        below = df["close"] < vwap
        # require >= N consecutive bars below before reclaim
        n = int(self.params["min_bars_below"])
        was_below = below.shift(1).rolling(n, min_periods=n).sum() >= n
        cross_up = (df["close"].shift(1) <= vwap.shift(1)) & (df["close"] > vwap)

        avg_v = df["volume"].rolling(int(self.params["vol_lookback"]), min_periods=1).mean()
        vol_ok = df["volume"] > avg_v * float(self.params["min_vol_ratio"])

        mask = (was_below & cross_up & vol_ok).fillna(False)
        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            close = float(df.loc[ts, "close"])
            v = float(vwap.loc[ts])
            base = 0.50 + 0.25 * min(1.0, (close - v) / max(close, 1.0) / 0.005) + 0.25
            base = max(0.0, min(1.0, base))
            low = float(df.loc[ts, "low"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close + (close - v),
                    suggested_stop=min(low, v),
                    metadata={"vwap": v, "close": close},
                )
            )
        return signals


class VWAPReject(PatternDetector):
    name = "vwap_reject"
    category = "volume"
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "vol_lookback": 20,
            "min_vol_ratio": 1.2,
            "min_bars_above": 3,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        vwap = _session_vwap(df)
        above = df["close"] > vwap
        n = int(self.params["min_bars_above"])
        was_above = above.shift(1).rolling(n, min_periods=n).sum() >= n
        cross_down = (df["close"].shift(1) >= vwap.shift(1)) & (df["close"] < vwap)

        avg_v = df["volume"].rolling(int(self.params["vol_lookback"]), min_periods=1).mean()
        vol_ok = df["volume"] > avg_v * float(self.params["min_vol_ratio"])

        mask = (was_above & cross_down & vol_ok).fillna(False)
        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            close = float(df.loc[ts, "close"])
            v = float(vwap.loc[ts])
            base = 0.50 + 0.25 * min(1.0, (v - close) / max(close, 1.0) / 0.005) + 0.25
            base = max(0.0, min(1.0, base))
            high = float(df.loc[ts, "high"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close - (v - close),
                    suggested_stop=max(high, v),
                    metadata={"vwap": v, "close": close},
                )
            )
        return signals
