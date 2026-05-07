"""Volume Climax — abnormal volume surge that often marks exhaustion.

Bull climax  : volume >> avg AND close near low (sellers exhausted) → bull.
Bear climax  : volume >> avg AND close near high (buyers exhausted) → bear.

We classify by close-position-in-range (CPR) of the climactic bar:
   CPR = (close - low) / (high - low)
   CPR <= 0.3 → bull (capitulation low)
   CPR >= 0.7 → bear (blow-off top)
   else neutral (still informative; emit with low confidence)

Confidence scales with vol_z and CPR extremity.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


class VolumeClimax(PatternDetector):
    name = "volume_climax"
    category = "volume"
    min_bars = 30

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 20,
            "min_vol_z": 3.0,         # raised from 2.5 — 3 sigma is more genuinely climactic
            "cooldown_bars": 10,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        lookback = int(self.params["lookback"])
        v_mean = df["volume"].rolling(lookback, min_periods=5).mean()
        v_std = df["volume"].rolling(lookback, min_periods=5).std(ddof=0)
        vol_z = (df["volume"] - v_mean) / v_std.replace(0, np.nan)

        rng = (df["high"] - df["low"]).replace(0, np.nan)
        cpr = (df["close"] - df["low"]) / rng

        mask = vol_z >= float(self.params["min_vol_z"])
        mask = mask.fillna(False)
        # Cooldown — climaxes shouldn't fire repeatedly within minutes.
        cooldown = int(self.params["cooldown_bars"])
        last_idx = -10**9
        for i, ts in enumerate(df.index):
            if bool(mask.loc[ts]):
                if i - last_idx < cooldown:
                    mask.loc[ts] = False
                else:
                    last_idx = i

        signals: list[PatternSignal] = []
        for ts, is_climax in mask.items():
            if not bool(is_climax):
                continue
            z = float(vol_z.loc[ts] or 0.0)
            c = float(cpr.loc[ts] or 0.5)
            if c <= 0.3:
                direction = "bull"
                extremity = (0.3 - c) / 0.3  # 0..1
            elif c >= 0.7:
                direction = "bear"
                extremity = (c - 0.7) / 0.3
            else:
                direction = "neutral"
                extremity = 0.0
            z_score = min(1.0, (z - float(self.params["min_vol_z"])) / 3.0)
            base = 0.4 + 0.35 * z_score + 0.25 * extremity
            base = max(0.0, min(1.0, base))
            high = float(df.loc[ts, "high"])
            low = float(df.loc[ts, "low"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction=direction,
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=None,
                    suggested_stop=low if direction == "bull" else high,
                    metadata={"vol_z": z, "cpr": c, "high": high, "low": low},
                )
            )
        return signals
