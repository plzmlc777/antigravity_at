"""Tests for regime feature extraction."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.regime.features import (  # noqa: E402
    compute_liquidity_score,
    compute_momentum_score,
    compute_trend_score,
    compute_volatility_score,
)


def _ohlcv_synth(n: int, closes: np.ndarray, volumes: np.ndarray | None = None) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=n, freq="1min")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.001
    lows = np.minimum(opens, closes) * 0.999
    if volumes is None:
        volumes = np.full(n, 1000, dtype=int)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


class TestTrendScore(unittest.TestCase):
    def test_uptrend_positive_score(self):
        n = 300
        closes = 100 + np.arange(n) * 0.05  # steady up
        df = _ohlcv_synth(n, closes)
        score = compute_trend_score(df, fast=20, slow=60)
        # last value should be strongly positive (clipped to ≤1)
        self.assertGreater(score.iloc[-1], 0.5)

    def test_downtrend_negative_score(self):
        n = 300
        closes = 100 - np.arange(n) * 0.05
        df = _ohlcv_synth(n, closes)
        score = compute_trend_score(df, fast=20, slow=60)
        self.assertLess(score.iloc[-1], -0.5)

    def test_sideways_near_zero(self):
        rng = np.random.default_rng(0)
        closes = 100 + rng.normal(0, 0.5, 300).cumsum() * 0.0  # truly flat
        # purely flat → divisions by 0; ensure no crash
        closes = closes + rng.normal(0, 0.02, 300)
        df = _ohlcv_synth(300, closes)
        score = compute_trend_score(df, fast=20, slow=60)
        self.assertLess(abs(score.iloc[-1]), 0.5)


class TestVolatilityScore(unittest.TestCase):
    def test_in_unit_interval(self):
        rng = np.random.default_rng(1)
        closes = 100 + rng.normal(0, 0.3, 300).cumsum()
        df = _ohlcv_synth(300, closes)
        score = compute_volatility_score(df, atr_period=14, lookback=200)
        valid = score.dropna()
        self.assertTrue((valid >= 0).all())
        self.assertTrue((valid <= 1).all())

    def test_transition_period_high_rank(self):
        """When vol just spiked, the new bars rank near the top of the
        recent (low-vol) window. Tests that the percentile rank captures
        the *change* in vol regime, even though within-stationary periods
        the score is uniform by definition."""
        n = 600
        rng = np.random.default_rng(2)
        first = 100 + rng.normal(0, 0.1, n // 2).cumsum()
        last = first[-1] + rng.normal(0, 1.0, n // 2).cumsum()
        closes = np.concatenate([first, last])
        df = _ohlcv_synth(n, closes)
        score = compute_volatility_score(df, atr_period=14, lookback=100)
        # right after the regime change, the new high-vol bars should rank
        # near the top of the past 100 bars (which were mostly low-vol).
        transition_avg = score.iloc[n // 2 + 5 : n // 2 + 25].mean()
        self.assertGreater(transition_avg, 0.7)


class TestLiquidityScore(unittest.TestCase):
    def test_volume_surge_positive(self):
        n = 300
        rng = np.random.default_rng(3)
        closes = 100 + rng.normal(0, 0.1, n).cumsum()
        volumes = np.full(n, 1000, dtype=int)
        # last 30 bars: volume 5x
        volumes[-30:] = 5000
        df = _ohlcv_synth(n, closes, volumes)
        score = compute_liquidity_score(df, short=20, long=200)
        self.assertGreater(score.iloc[-1], 0.3)

    def test_volume_drought_negative(self):
        n = 300
        rng = np.random.default_rng(4)
        closes = 100 + rng.normal(0, 0.1, n).cumsum()
        volumes = np.full(n, 1000, dtype=int)
        volumes[-30:] = 200  # 5x lower
        df = _ohlcv_synth(n, closes, volumes)
        score = compute_liquidity_score(df, short=20, long=200)
        self.assertLess(score.iloc[-1], -0.2)


class TestMomentumScore(unittest.TestCase):
    def test_steady_up_positive(self):
        closes = 100 * (1.0005 ** np.arange(400))  # geometric uptrend
        df = _ohlcv_synth(400, closes)
        score = compute_momentum_score(df)
        self.assertGreater(score.iloc[-1], 0.3)

    def test_steady_down_negative(self):
        closes = 100 * (0.9995 ** np.arange(400))
        df = _ohlcv_synth(400, closes)
        score = compute_momentum_score(df)
        self.assertLess(score.iloc[-1], -0.3)


if __name__ == "__main__":
    unittest.main()
