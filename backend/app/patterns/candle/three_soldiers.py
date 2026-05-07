"""Three White Soldiers (bull) / Three Black Crows (bear).

Three consecutive bars in the same direction, each opening within prior body and
closing higher (white) / lower (black). Confirms strong momentum.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from ..base import PatternDetector, PatternSignal


class ThreeWhiteSoldiers(PatternDetector):
    name = "three_white_soldiers"
    category = "candle"
    min_bars = 23

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_body_to_avg": 0.8,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body = (df["close"] - df["open"]).abs()
        avg_body = body.rolling(int(self.params["body_lookback"]), min_periods=1).mean()
        bull1 = (df["close"].shift(2) > df["open"].shift(2))
        bull2 = (df["close"].shift(1) > df["open"].shift(1))
        bull3 = (df["close"] > df["open"])
        # each closes higher than previous
        higher_close = (df["close"].shift(1) > df["close"].shift(2)) & (df["close"] > df["close"].shift(1))
        # each opens within prior body
        in_prior_body_2 = (df["open"].shift(1) >= df["open"].shift(2)) & (df["open"].shift(1) <= df["close"].shift(2))
        in_prior_body_3 = (df["open"] >= df["open"].shift(1)) & (df["open"] <= df["close"].shift(1))
        # each body decent size
        big_enough = (body >= avg_body * float(self.params["min_body_to_avg"]))
        big_enough_all = big_enough & big_enough.shift(1) & big_enough.shift(2)

        mask = (bull1 & bull2 & bull3 & higher_close & in_prior_body_2 & in_prior_body_3 & big_enough_all).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            close = float(df.loc[ts, "close"])
            close_2 = float(df.loc[ts, "close"]) if pd.isna(df.shift(2).loc[ts, "close"]) else float(df.shift(2).loc[ts, "close"])
            move = close - close_2
            base = 0.55 + 0.25 * min(1.0, abs(move) / (close * 0.05)) + 0.20
            base = max(0.0, min(1.0, base))
            low_3 = float(df.shift(2).loc[ts, "low"]) if not pd.isna(df.shift(2).loc[ts, "low"]) else float(df.loc[ts, "low"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bull",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close + move,
                    suggested_stop=low_3,
                    metadata={"3bar_move": float(move)},
                )
            )
        return signals


class ThreeBlackCrows(PatternDetector):
    name = "three_black_crows"
    category = "candle"
    min_bars = 23

    @classmethod
    def default_params(cls) -> dict[str, Any]:
        return {
            "body_lookback": 20,
            "min_body_to_avg": 0.8,
            "horizon_bars": 5,
        }

    def _detect_impl(self, ohlcv: pd.DataFrame) -> list[PatternSignal]:
        df = ohlcv
        body = (df["close"] - df["open"]).abs()
        avg_body = body.rolling(int(self.params["body_lookback"]), min_periods=1).mean()
        bear1 = (df["close"].shift(2) < df["open"].shift(2))
        bear2 = (df["close"].shift(1) < df["open"].shift(1))
        bear3 = (df["close"] < df["open"])
        lower_close = (df["close"].shift(1) < df["close"].shift(2)) & (df["close"] < df["close"].shift(1))
        in_prior_body_2 = (df["open"].shift(1) <= df["open"].shift(2)) & (df["open"].shift(1) >= df["close"].shift(2))
        in_prior_body_3 = (df["open"] <= df["open"].shift(1)) & (df["open"] >= df["close"].shift(1))
        big_enough = body >= avg_body * float(self.params["min_body_to_avg"])
        big_enough_all = big_enough & big_enough.shift(1) & big_enough.shift(2)

        mask = (bear1 & bear2 & bear3 & lower_close & in_prior_body_2 & in_prior_body_3 & big_enough_all).fillna(False)

        signals: list[PatternSignal] = []
        for ts, hit in mask.items():
            if not bool(hit):
                continue
            close = float(df.loc[ts, "close"])
            close_2 = float(df.shift(2).loc[ts, "close"]) if not pd.isna(df.shift(2).loc[ts, "close"]) else close
            move = close_2 - close
            base = 0.55 + 0.25 * min(1.0, move / (close * 0.05)) + 0.20
            base = max(0.0, min(1.0, base))
            high_3 = float(df.shift(2).loc[ts, "high"]) if not pd.isna(df.shift(2).loc[ts, "high"]) else float(df.loc[ts, "high"])
            signals.append(
                PatternSignal(
                    pattern_name=self.name,
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    direction="bear",
                    confidence=base,
                    horizon_bars=int(self.params["horizon_bars"]),
                    suggested_target=close - move,
                    suggested_stop=high_3,
                    metadata={"3bar_move": float(move)},
                )
            )
        return signals
