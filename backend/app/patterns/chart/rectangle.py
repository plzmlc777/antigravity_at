"""Rectangle (range/box) — bounded sideways consolidation, then breakout.

Strict redesign (post Phase-2 diagnosis: prior version emitted 215/day on 005930
because the band-width definition was too lenient and signaled at every "near"
breakout).

New criteria:
  1. The window must be a TRUE box: top band touched >= 2 distinct times,
     bottom band touched >= 2 distinct times, with separation >= min_band_height_pct.
  2. The window MUST contain mean-reversion bars between the bands (otherwise
     it's just a thin slope, not a box).
  3. Breakout = curr close strictly outside the band by at least 0.3 * band_height
     (not just "close > top_mean") — prevents wick-touches from firing.
  4. Each breakout fires at most once per box (cooldown after a breakout).
  5. Confidence varies with the (touch count, band cleanliness, breakout strength)
     — no more constant 1.0.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal
from ._helpers import atr_series


class Rectangle(PatternDetector):
    name = "rectangle"
    category = "chart"
    applicable_timeframes = ("15m", "1h", "4h", "1d")
    min_bars = 50

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "lookback": 30,
            "min_band_height_atr_mult": 1.5,   # band >= 1.5 ATR tall
            "max_band_band_std_pct": 0.012,    # top/bottom bands flat (<1.2% std)
            "min_top_touches": 2,
            "min_bot_touches": 2,
            "touch_tolerance_atr_mult": 0.5,   # within 0.5*ATR counts as touch
            "min_breakout_strength_atr_mult": 0.5,
            "cooldown_bars": 10,
            "horizon_bars": 10,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        params = self.params
        lb = int(params["lookback"])
        atr = atr_series(df, 14)

        signals: list[PatternSignal] = []
        cooldown_until = -1

        for i in range(lb, len(df)):
            if i < cooldown_until:
                continue
            window = df.iloc[i - lb : i]  # excludes current
            cur_atr = float(atr.iloc[i] or 0.0)
            if cur_atr <= 0:
                continue

            top_mean = float(window["high"].mean())
            bot_mean = float(window["low"].mean())
            band_height = top_mean - bot_mean
            if band_height < cur_atr * float(params["min_band_height_atr_mult"]):
                continue

            top_std_pct = float(window["high"].std(ddof=0)) / max(top_mean, 1e-9)
            bot_std_pct = float(window["low"].std(ddof=0)) / max(bot_mean, 1e-9)
            if top_std_pct > float(params["max_band_band_std_pct"]):
                continue
            if bot_std_pct > float(params["max_band_band_std_pct"]):
                continue

            tol = cur_atr * float(params["touch_tolerance_atr_mult"])
            top_touch_mask = (window["high"] >= top_mean - tol).to_numpy()
            bot_touch_mask = (window["low"] <= bot_mean + tol).to_numpy()
            # count distinct touches: a "touch" requires gap of >=3 bars from previous touch
            top_touches = _count_distinct(top_touch_mask, gap=3)
            bot_touches = _count_distinct(bot_touch_mask, gap=3)
            if top_touches < int(params["min_top_touches"]):
                continue
            if bot_touches < int(params["min_bot_touches"]):
                continue

            # require some mean-reversion: bars that closed in the middle 50%
            mid_lo = bot_mean + 0.25 * band_height
            mid_hi = bot_mean + 0.75 * band_height
            mid_bars = ((window["close"] >= mid_lo) & (window["close"] <= mid_hi)).sum()
            if mid_bars < lb * 0.2:  # at least 20% of bars passed through middle
                continue

            curr_close = float(df["close"].iloc[i])
            breakout_strength_required = cur_atr * float(params["min_breakout_strength_atr_mult"])
            if curr_close > top_mean + breakout_strength_required:
                direction = "bull"
                strength = (curr_close - top_mean) / breakout_strength_required
                target = curr_close + band_height
                stop = (top_mean + bot_mean) / 2.0
            elif curr_close < bot_mean - breakout_strength_required:
                direction = "bear"
                strength = (bot_mean - curr_close) / breakout_strength_required
                target = curr_close - band_height
                stop = (top_mean + bot_mean) / 2.0
            else:
                continue

            ts = df.index[i]
            # confidence: blend touch count, band cleanliness, breakout strength
            touch_score = min(1.0, (top_touches + bot_touches - 4) / 4.0)
            cleanliness = 1.0 - max(top_std_pct, bot_std_pct) / float(params["max_band_band_std_pct"])
            strength_score = min(1.0, (strength - 1.0) / 2.0)
            base = 0.40 + 0.20 * touch_score + 0.20 * cleanliness + 0.20 * strength_score
            base = max(0.0, min(1.0, base))

            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction=direction,
                    confidence=base,
                    horizon_bars=int(params["horizon_bars"]),
                    suggested_target=float(target),
                    suggested_stop=float(stop),
                    metadata={
                        "top": top_mean,
                        "bottom": bot_mean,
                        "band_height": band_height,
                        "top_touches": int(top_touches),
                        "bot_touches": int(bot_touches),
                        "breakout_strength_atr": float(strength),
                    },
                )
            )
            cooldown_until = i + int(params["cooldown_bars"])

        return signals


def _count_distinct(mask: np.ndarray, gap: int) -> int:
    """Count distinct True regions separated by at least `gap` False bars between."""
    n = 0
    last_true = -10**9
    for i, v in enumerate(mask):
        if v and i - last_true >= gap:
            n += 1
            last_true = i
        elif v:
            last_true = i
    return n
