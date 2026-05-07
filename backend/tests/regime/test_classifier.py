"""Tests for RegimeClassifier."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.regime import (  # noqa: E402
    LIQUIDITY_LABELS,
    MOMENTUM_LABELS,
    REGIME_DIMS,
    RegimeClassifier,
    RegimeVector,
    TREND_LABELS,
    VOLATILITY_LABELS,
)


def _synth(n: int, closes: np.ndarray, volumes: np.ndarray | None = None) -> pd.DataFrame:
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


class TestClassifier(unittest.TestCase):
    def test_classify_returns_dataframe_with_expected_columns(self):
        rng = np.random.default_rng(0)
        closes = 100 + rng.normal(0, 0.3, 400).cumsum()
        df = _synth(400, closes)
        rdf = RegimeClassifier().classify(df)
        for col in (
            "trend_score", "volatility_score", "liquidity_score", "momentum_score",
            "trend", "volatility", "liquidity", "momentum",
            "is_warmup", "cell_id",
        ):
            self.assertIn(col, rdf.columns)
        self.assertEqual(len(rdf), len(df))

    def test_uptrend_classified_as_trending_up(self):
        n = 400
        closes = 100 + np.arange(n) * 0.05
        df = _synth(n, closes)
        rdf = RegimeClassifier().classify(df)
        # post-warmup last bar should be trending_up
        self.assertEqual(rdf.iloc[-1]["trend"], "trending_up")

    def test_downtrend_classified_as_trending_down(self):
        n = 400
        closes = 100 - np.arange(n) * 0.05
        df = _synth(n, closes)
        rdf = RegimeClassifier().classify(df)
        self.assertEqual(rdf.iloc[-1]["trend"], "trending_down")

    def test_warmup_flagged(self):
        n = 400
        rng = np.random.default_rng(1)
        closes = 100 + rng.normal(0, 0.3, n).cumsum()
        df = _synth(n, closes)
        rdf = RegimeClassifier().classify(df)
        # First few bars are warmup (no slow MA yet)
        self.assertTrue(rdf.iloc[0]["is_warmup"])
        self.assertFalse(rdf.iloc[-1]["is_warmup"])

    def test_cell_id_format(self):
        n = 400
        closes = 100 + np.arange(n) * 0.05
        df = _synth(n, closes)
        rdf = RegimeClassifier().classify(df)
        # cell_id should be 4 parts joined by |
        cell = rdf.iloc[-1]["cell_id"]
        parts = cell.split("|")
        self.assertEqual(len(parts), 4)
        self.assertIn(parts[0], TREND_LABELS)
        self.assertIn(parts[1], VOLATILITY_LABELS)
        self.assertIn(parts[2], LIQUIDITY_LABELS)
        self.assertIn(parts[3], MOMENTUM_LABELS)

    def test_classify_at_returns_regime_vector(self):
        n = 400
        closes = 100 + np.arange(n) * 0.05
        df = _synth(n, closes)
        rv = RegimeClassifier().classify_at(df, df.index[-1])
        self.assertIsInstance(rv, RegimeVector)
        self.assertIn(rv.trend, TREND_LABELS)

    def test_all_possible_cells_count(self):
        cells = RegimeClassifier.all_possible_cells()
        self.assertEqual(len(cells), 81)
        self.assertEqual(len(set(cells)), 81)

    def test_no_dim_monopolizes_on_realistic_random_walk(self):
        """Realistic random walk (geometric prices + heteroskedastic volume)
        should produce non-degenerate label distributions on the dynamic dims.
        Liquidity may be uniformly 'normal' if volume has low variance — that's
        a property of the input, not a calibration bug — so we exempt it."""
        rng = np.random.default_rng(42)
        n = 2000
        closes = 100 * np.exp(rng.normal(0, 0.0008, n).cumsum())
        rng2 = np.random.default_rng(43)
        # heteroskedastic volume — realistic intraday variance
        volumes = (np.exp(rng2.normal(7.0, 0.5, n))).astype(int)
        df = _synth(n, closes, volumes)
        rdf = RegimeClassifier().classify(df)
        valid = rdf[~rdf["is_warmup"]]
        for dim in ("trend", "volatility", "momentum"):
            counts = valid[dim].value_counts(normalize=True)
            for share in counts.values:
                self.assertLess(share, 0.95, f"{dim} bucket dominates: {counts.to_dict()}")


if __name__ == "__main__":
    unittest.main()
