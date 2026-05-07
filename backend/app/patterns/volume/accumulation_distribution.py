"""Wyckoff-style Accumulation / Distribution phase detection.

Accumulation : sideways range + above-avg volume + close-position-in-range (CPR) bias
               UP — sellers absorbed by smart money. Bull bias.
Distribution : sideways range + above-avg volume + CPR bias DOWN — buyers absorbed.
               Bear bias.

We use simple proxies:
  - "sideways range": rolling stddev of close < threshold
  - "above-avg volume": rolling mean volume > long-term mean by mult
  - "CPR bias": rolling mean of (close-low)/(high-low) above 0.55 (accum) or below 0.45 (distrib)
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


def _cpr(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    return (df["close"] - df["low"]) / rng


class AccumulationPhase(PatternDetector):
    name = "accumulation_phase"
    category = "volume"
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "window": 20,
            "long_window": 60,
            "max_close_std_pct": 0.025,
            "min_vol_ratio": 1.2,
            "min_cpr_mean": 0.60,
            "min_phase_persist": 5,   # phase must hold for >=N bars before signaling
            "cooldown_bars": 30,
            "horizon_bars": 15,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        w = int(self.params["window"])
        lw = int(self.params["long_window"])
        close_std = (df["close"].rolling(w, min_periods=w).std(ddof=0) / df["close"]).clip(0, 1)
        vol_ratio = df["volume"].rolling(w, min_periods=w).mean() / df["volume"].rolling(lw, min_periods=lw).mean()
        cpr_mean = _cpr(df).rolling(w, min_periods=w).mean()

        cond = (
            (close_std <= float(self.params["max_close_std_pct"]))
            & (vol_ratio >= float(self.params["min_vol_ratio"]))
            & (cpr_mean >= float(self.params["min_cpr_mean"]))
        ).fillna(False)

        # require persistence + cooldown
        n = int(self.params["min_phase_persist"])
        persisted = cond.rolling(n, min_periods=n).sum() >= n
        first = persisted & ~persisted.shift(1, fill_value=False)
        cooldown = int(self.params["cooldown_bars"])
        last_idx = -10**9
        for i, ts in enumerate(df.index):
            if bool(first.loc[ts]):
                if i - last_idx < cooldown:
                    first.loc[ts] = False
                else:
                    last_idx = i
        signals: list[PatternSignal] = []
        for ts, hit in first.items():
            if not bool(hit):
                continue
            cpr_v = float(cpr_mean.loc[ts] or 0.0)
            vol_v = float(vol_ratio.loc[ts] or 1.0)
            base = 0.40 + 0.30 * min(1.0, (cpr_v - 0.5) / 0.3) + 0.30 * min(1.0, (vol_v - 1.0) / 0.5)
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            low = float(df.loc[ts, "low"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=low,
                    metadata={"cpr_mean": cpr_v, "vol_ratio": vol_v, "close_std": float(close_std.loc[ts] or 0)},
                )
            )
        return signals


class DistributionPhase(PatternDetector):
    name = "distribution_phase"
    category = "volume"
    min_bars = 60

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "window": 20,
            "long_window": 60,
            "max_close_std_pct": 0.025,
            "min_vol_ratio": 1.2,
            "max_cpr_mean": 0.40,
            "min_phase_persist": 5,
            "cooldown_bars": 30,
            "horizon_bars": 15,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        w = int(self.params["window"])
        lw = int(self.params["long_window"])
        close_std = (df["close"].rolling(w, min_periods=w).std(ddof=0) / df["close"]).clip(0, 1)
        vol_ratio = df["volume"].rolling(w, min_periods=w).mean() / df["volume"].rolling(lw, min_periods=lw).mean()
        cpr_mean = _cpr(df).rolling(w, min_periods=w).mean()

        cond = (
            (close_std <= float(self.params["max_close_std_pct"]))
            & (vol_ratio >= float(self.params["min_vol_ratio"]))
            & (cpr_mean <= float(self.params["max_cpr_mean"]))
        ).fillna(False)

        n = int(self.params["min_phase_persist"])
        persisted = cond.rolling(n, min_periods=n).sum() >= n
        first = persisted & ~persisted.shift(1, fill_value=False)
        cooldown = int(self.params["cooldown_bars"])
        last_idx = -10**9
        for i, ts in enumerate(df.index):
            if bool(first.loc[ts]):
                if i - last_idx < cooldown:
                    first.loc[ts] = False
                else:
                    last_idx = i
        signals: list[PatternSignal] = []
        for ts, hit in first.items():
            if not bool(hit):
                continue
            cpr_v = float(cpr_mean.loc[ts] or 0.0)
            vol_v = float(vol_ratio.loc[ts] or 1.0)
            base = 0.40 + 0.30 * min(1.0, (0.5 - cpr_v) / 0.3) + 0.30 * min(1.0, (vol_v - 1.0) / 0.5)
            base = max(0.0, min(1.0, base))
            close = float(df.loc[ts, "close"])
            high = float(df.loc[ts, "high"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=high,
                    metadata={"cpr_mean": cpr_v, "vol_ratio": vol_v, "close_std": float(close_std.loc[ts] or 0)},
                )
            )
        return signals
