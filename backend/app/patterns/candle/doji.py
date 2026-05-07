"""Doji — single bar with body ~0 vs total range. Indecision marker.

By itself a Doji is direction=neutral. Composer combines with surrounding context.
Confidence rises with smaller body/range ratio AND larger relative range
(a tiny doji in noise is uninformative).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


class Doji(PatternDetector):
    name = "doji"
    category = "candle"
    # On 1m a "doji" is just a quiet minute. Restrict to >=15m where the bar
    # represents a meaningful indecision period.
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 21

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "max_body_to_range_ratio": 0.10,  # body <= 10% of range
            "min_range_to_avg": 0.7,          # range >= 70% of avg range
            "lookback": 20,
            "horizon_bars": 3,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body = (df["close"] - df["open"]).abs()
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        body_ratio = body / rng

        avg_rng = rng.rolling(int(self.params["lookback"]), min_periods=5).mean()
        rng_vs_avg = rng / avg_rng

        mask = (body_ratio <= float(self.params["max_body_to_range_ratio"])) & (
            rng_vs_avg >= float(self.params["min_range_to_avg"])
        )
        mask = mask.fillna(False)

        signals: list[PatternSignal] = []
        for ts, row_mask in mask.items():
            if not bool(row_mask):
                continue
            br = float(body_ratio.loc[ts] or 0.0)
            ra = float(rng_vs_avg.loc[ts] or 0.0)
            base = 0.4 + 0.4 * (1.0 - br / float(self.params["max_body_to_range_ratio"]))
            base += 0.2 * min(1.0, max(0.0, (ra - 0.7) / 1.3))
            base = max(0.0, min(1.0, base))
            high = float(df.loc[ts, "high"])
            low = float(df.loc[ts, "low"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="neutral",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=None,
                    metadata={
                        "body_to_range": br,
                        "range_vs_avg": ra,
                        "high": high,
                        "low": low,
                    },
                )
            )
        return signals
