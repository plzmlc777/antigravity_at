"""Resampling tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402


def make_1m(n: int = 600, start: str = "2025-01-02 09:00") -> pd.DataFrame:
    rng = np.random.default_rng(0)
    idx = pd.date_range(start=start, periods=n, freq="1min")
    closes = 100 + rng.normal(0, 0.05, n).cumsum()
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) + 0.05
    lows = np.minimum(opens, closes) - 0.05
    volumes = rng.integers(80, 120, n).astype(int)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


class TestResample(unittest.TestCase):
    def setUp(self):
        self.df_1m = make_1m(n=600)

    def test_passthrough_1m(self):
        out = resample_ohlcv(self.df_1m, "1m")
        self.assertEqual(list(out.columns), ["open", "high", "low", "close", "volume"])
        self.assertEqual(len(out), len(self.df_1m))

    def test_resample_5m_count(self):
        out = resample_ohlcv(self.df_1m, "5m")
        # 600 bars / 5 = 120, last partial dropped → 119 or 120 depending on alignment
        self.assertGreaterEqual(len(out), 118)
        self.assertLessEqual(len(out), 120)

    def test_resample_15m(self):
        out = resample_ohlcv(self.df_1m, "15m")
        self.assertGreaterEqual(len(out), 39)
        self.assertLessEqual(len(out), 40)

    def test_resample_1h(self):
        out = resample_ohlcv(self.df_1m, "1h")
        self.assertGreaterEqual(len(out), 9)
        self.assertLessEqual(len(out), 10)

    def test_aggregation_correctness(self):
        """5-bar high should be max of constituent 1m highs."""
        out_5m = resample_ohlcv(self.df_1m, "5m")
        first_bar_5m = out_5m.iloc[0]
        first_5_1m = self.df_1m.iloc[:5]
        self.assertAlmostEqual(first_bar_5m["high"], first_5_1m["high"].max(), places=5)
        self.assertAlmostEqual(first_bar_5m["low"], first_5_1m["low"].min(), places=5)
        self.assertAlmostEqual(first_bar_5m["open"], first_5_1m["open"].iloc[0], places=5)
        self.assertAlmostEqual(first_bar_5m["close"], first_5_1m["close"].iloc[-1], places=5)
        self.assertEqual(int(first_bar_5m["volume"]), int(first_5_1m["volume"].sum()))

    def test_unsupported_tf_raises(self):
        with self.assertRaises(ValueError):
            resample_ohlcv(self.df_1m, "30m")

    def test_no_datetime_index_raises(self):
        df = self.df_1m.reset_index(drop=True)
        with self.assertRaises(ValueError):
            resample_ohlcv(df, "5m")


if __name__ == "__main__":
    unittest.main()
