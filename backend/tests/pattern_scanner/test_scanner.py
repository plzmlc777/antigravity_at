"""End-to-end scanner tests with synthetic data + cache round-trip."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pattern_scanner import (  # noqa: E402
    PatternScanner,
    SUPPORTED_TIMEFRAMES,
    SignalTensorCache,
)
from app.pattern_scanner.types import signal_tensor_columns  # noqa: E402


def make_1m_long(n: int = 5000) -> pd.DataFrame:
    """Long enough to support 1d resample (5000min = 83h ≈ 3.5 days)."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2025-01-02 09:00", periods=n, freq="1min")
    closes = 1000 * np.exp(rng.normal(0, 0.0008, n).cumsum())
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.001, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.001, n))
    vols = rng.integers(800, 1200, n).astype(int)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols},
        index=idx,
    )


class TestScanner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df_1m = make_1m_long()

    def test_scan_returns_tensor_dataframe(self):
        scanner = PatternScanner(timeframes=("5m", "15m", "1h"))
        tensor = scanner.scan(self.df_1m, symbol="TEST")
        self.assertIsInstance(tensor, pd.DataFrame)
        self.assertEqual(list(tensor.columns), signal_tensor_columns())

    def test_scan_with_stats(self):
        scanner = PatternScanner(timeframes=("5m", "1h"))
        tensor, stats = scanner.scan_with_stats(self.df_1m, symbol="TEST")
        self.assertEqual(stats.symbol, "TEST")
        self.assertEqual(stats.n_input_bars, len(self.df_1m))
        self.assertEqual(stats.timeframes_scanned, ["5m", "1h"])
        self.assertEqual(stats.detectors_run, len(scanner.detectors))
        self.assertEqual(len(tensor), stats.total_signals)
        # signals_by_tf should sum to total
        self.assertEqual(sum(stats.signals_by_tf.values()), stats.total_signals)

    def test_invalid_tf_raises(self):
        with self.assertRaises(ValueError):
            PatternScanner(timeframes=("3m",))

    def test_missing_columns_raises(self):
        bad = self.df_1m.drop(columns=["volume"])
        scanner = PatternScanner(timeframes=("5m",))
        with self.assertRaises(ValueError):
            scanner.scan(bad, symbol="TEST")

    def test_empty_input_returns_empty_tensor(self):
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], name="ts"),
        )
        scanner = PatternScanner(timeframes=("5m",))
        tensor = scanner.scan(empty, symbol="TEST")
        self.assertEqual(len(tensor), 0)
        self.assertEqual(list(tensor.columns), signal_tensor_columns())

    def test_tensor_metadata_preserved(self):
        scanner = PatternScanner(timeframes=("5m",))
        tensor = scanner.scan(self.df_1m, symbol="TEST")
        if len(tensor) > 0:
            for md in tensor["metadata"].head(5):
                self.assertIsInstance(md, dict)


class TestCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df_1m = make_1m_long()

    def test_cache_round_trip(self):
        scanner = PatternScanner(timeframes=("5m",))
        tensor, _ = scanner.scan_with_stats(self.df_1m, symbol="TEST")

        with tempfile.TemporaryDirectory() as td:
            cache = SignalTensorCache(root=td)
            key = cache.make_key(
                symbol="TEST",
                start=self.df_1m.index[0],
                end=self.df_1m.index[-1],
            )
            self.assertFalse(cache.has(key))
            cache.put(key, tensor)
            self.assertTrue(cache.has(key))

            loaded = cache.get(key)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded), len(tensor))
            self.assertEqual(list(loaded.columns), list(tensor.columns))
            # metadata round-trip
            if len(tensor) > 0:
                self.assertIsInstance(loaded["metadata"].iloc[0], dict)

    def test_cache_invalidate(self):
        with tempfile.TemporaryDirectory() as td:
            cache = SignalTensorCache(root=td)
            key = cache.make_key(
                symbol="TEST",
                start=pd.Timestamp("2025-01-01"),
                end=pd.Timestamp("2025-12-31"),
            )
            empty = pd.DataFrame(columns=signal_tensor_columns())
            cache.put(key, empty)
            self.assertTrue(cache.has(key))
            cache.invalidate(key)
            self.assertFalse(cache.has(key))


if __name__ == "__main__":
    unittest.main()
