"""Bullish/Bearish Engulfing — 2-bar reversal pattern.

Bullish:  prev bar bearish (close<open), curr bar bullish (close>open),
          curr open <= prev close, curr close >= prev open. Body of curr engulfs prev.
Bearish:  mirror.

Confidence rises with body size ratio (curr_body / prev_body) clipped to [0,1].
Volume amplification (curr_vol > avg_vol) gives bonus.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..base import PatternDetector, PatternSignal


def _avg_body(df: pd.DataFrame, lookback: int) -> pd.Series:
    return (df["close"] - df["open"]).abs().rolling(lookback, min_periods=1).mean()


def _avg_vol(df: pd.DataFrame, lookback: int) -> pd.Series:
    return df["volume"].rolling(lookback, min_periods=1).mean()


class BullishEngulfing(PatternDetector):
    name = "bullish_engulfing"
    category = "candle"
    min_bars = 21

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_body_ratio": 1.5,         # curr body must be >= 1.5 × prev body
            "min_body_to_avg_ratio": 1.0,  # curr body >= avg body (strong move)
            "vol_bonus_mult": 1.5,         # higher bar for vol bonus
            "trend_ma": 10,                # require recent trend in opposite direction
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        prev_o = df["open"].shift(1)
        prev_c = df["close"].shift(1)
        prev_body = (prev_c - prev_o).abs()
        curr_body = (df["close"] - df["open"]).abs()

        bearish_prev = prev_c < prev_o
        bullish_now = df["close"] > df["open"]
        engulf_body = (df["open"] <= prev_c) & (df["close"] >= prev_o)
        body_ratio = curr_body / prev_body.replace(0, np.nan)
        big_enough = body_ratio >= float(self.params["min_body_ratio"])

        avg_v = _avg_vol(df, int(self.params["body_lookback"]))
        avg_b = _avg_body(df, int(self.params["body_lookback"]))
        vol_bonus = (df["volume"] > avg_v * float(self.params["vol_bonus_mult"]))
        body_vs_avg_raw = curr_body / avg_b.replace(0, np.nan)
        body_vs_avg = body_vs_avg_raw.clip(0, 3) / 3.0
        big_vs_avg = body_vs_avg_raw >= float(self.params["min_body_to_avg_ratio"])

        # bullish engulfing requires preceding downtrend: close < MA(trend_ma) recently
        trend_ma = df["close"].rolling(int(self.params["trend_ma"]), min_periods=1).mean()
        downtrend_ctx = (prev_c < trend_ma.shift(1))

        mask = (
            bearish_prev & bullish_now & engulf_body
            & big_enough.fillna(False) & big_vs_avg.fillna(False)
            & downtrend_ctx
        )

        signals: list[PatternSignal] = []
        for ts, row_mask in mask.items():
            if not bool(row_mask):
                continue
            base = 0.55 + 0.30 * float(body_vs_avg.loc[ts] or 0.0)
            if bool(vol_bonus.loc[ts]):
                base += 0.15
            base = max(0.0, min(1.0, base))
            curr_low = float(df.loc[ts, "low"])
            curr_close = float(df.loc[ts, "close"])
            curr_high = float(df.loc[ts, "high"])
            target = curr_close + (curr_close - curr_low) * 1.5
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=target,
                    suggested_stop=curr_low,
                    metadata={
                        "body_ratio": float(body_ratio.loc[ts] or 0.0),
                        "curr_high": curr_high,
                    },
                )
            )
        return signals


class BearishEngulfing(PatternDetector):
    name = "bearish_engulfing"
    category = "candle"
    min_bars = 21

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_body_ratio": 1.5,
            "min_body_to_avg_ratio": 1.0,
            "vol_bonus_mult": 1.5,
            "trend_ma": 10,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        prev_o = df["open"].shift(1)
        prev_c = df["close"].shift(1)
        prev_body = (prev_o - prev_c).abs()
        curr_body = (df["open"] - df["close"]).abs()

        bullish_prev = prev_c > prev_o
        bearish_now = df["close"] < df["open"]
        engulf_body = (df["open"] >= prev_c) & (df["close"] <= prev_o)
        body_ratio = curr_body / prev_body.replace(0, np.nan)
        big_enough = body_ratio >= float(self.params["min_body_ratio"])

        avg_v = _avg_vol(df, int(self.params["body_lookback"]))
        avg_b = _avg_body(df, int(self.params["body_lookback"]))
        vol_bonus = (df["volume"] > avg_v * float(self.params["vol_bonus_mult"]))
        body_vs_avg_raw = curr_body / avg_b.replace(0, np.nan)
        body_vs_avg = body_vs_avg_raw.clip(0, 3) / 3.0
        big_vs_avg = body_vs_avg_raw >= float(self.params["min_body_to_avg_ratio"])

        trend_ma = df["close"].rolling(int(self.params["trend_ma"]), min_periods=1).mean()
        uptrend_ctx = (prev_c > trend_ma.shift(1))

        mask = (
            bullish_prev & bearish_now & engulf_body
            & big_enough.fillna(False) & big_vs_avg.fillna(False)
            & uptrend_ctx
        )

        signals: list[PatternSignal] = []
        for ts, row_mask in mask.items():
            if not bool(row_mask):
                continue
            base = 0.55 + 0.30 * float(body_vs_avg.loc[ts] or 0.0)
            if bool(vol_bonus.loc[ts]):
                base += 0.15
            base = max(0.0, min(1.0, base))
            curr_high = float(df.loc[ts, "high"])
            curr_close = float(df.loc[ts, "close"])
            curr_low = float(df.loc[ts, "low"])
            target = curr_close - (curr_high - curr_close) * 1.5
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=target,
                    suggested_stop=curr_high,
                    metadata={
                        "body_ratio": float(body_ratio.loc[ts] or 0.0),
                        "curr_low": curr_low,
                    },
                )
            )
        return signals
