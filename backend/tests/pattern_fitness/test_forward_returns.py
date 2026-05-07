"""Tests for forward-return computation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pattern_fitness.forward_returns import attach_forward_returns  # noqa: E402


def _make_tf_ohlcv(n=100, start_close=100.0, drift=0.001) -> pd.DataFrame:
    """Geometric drift series for predictable returns."""
    idx = pd.date_range("2025-01-01 09:00", periods=n, freq="5min")
    closes = start_close * (1 + drift) ** np.arange(n)
    return pd.DataFrame(
        {"open": closes, "high": closes * 1.001, "low": closes * 0.999, "close": closes,
         "volume": np.full(n, 1000)},
        index=idx,
    )


class TestForwardReturns(unittest.TestCase):
    def setUp(self):
        self.tf_5m = _make_tf_ohlcv(100, drift=0.001)  # +0.1% per 5m bar
        self.signals = pd.DataFrame(
            [
                {"timeframe": "5m", "timestamp": self.tf_5m.index[10], "direction": "bull",
                 "horizon_bars": 5, "pattern_name": "test", "confidence": 0.7,
                 "suggested_target": None, "suggested_stop": None, "metadata": {}},
                {"timeframe": "5m", "timestamp": self.tf_5m.index[20], "direction": "bear",
                 "horizon_bars": 5, "pattern_name": "test", "confidence": 0.7,
                 "suggested_target": None, "suggested_stop": None, "metadata": {}},
                {"timeframe": "5m", "timestamp": self.tf_5m.index[30], "direction": "neutral",
                 "horizon_bars": 5, "pattern_name": "test", "confidence": 0.7,
                 "suggested_target": None, "suggested_stop": None, "metadata": {}},
                # past end of data — should be dropped (NaN return)
                {"timeframe": "5m", "timestamp": self.tf_5m.index[98], "direction": "bull",
                 "horizon_bars": 10, "pattern_name": "test", "confidence": 0.7,
                 "suggested_target": None, "suggested_stop": None, "metadata": {}},
            ]
        )

    def test_columns_added(self):
        out = attach_forward_returns(self.signals, {"5m": self.tf_5m})
        for col in ("forward_return", "forward_return_raw", "exit_timestamp"):
            self.assertIn(col, out.columns)

    def test_bull_direction_positive_drift(self):
        out = attach_forward_returns(self.signals, {"5m": self.tf_5m})
        # bull signal in +drift series: forward_return ≈ +(1.001^5 - 1) ≈ +0.005
        bull_row = out[(out["direction"] == "bull") & (out["timestamp"] == self.tf_5m.index[10])].iloc[0]
        self.assertAlmostEqual(bull_row["forward_return"], 1.001**5 - 1, places=5)
        self.assertAlmostEqual(bull_row["forward_return_raw"], 1.001**5 - 1, places=5)

    def test_bear_direction_negates_raw(self):
        out = attach_forward_returns(self.signals, {"5m": self.tf_5m})
        bear_row = out[(out["direction"] == "bear")].iloc[0]
        # raw is positive (price drifted up), bear adjusted should be negative
        self.assertGreater(bear_row["forward_return_raw"], 0)
        self.assertLess(bear_row["forward_return"], 0)
        self.assertAlmostEqual(bear_row["forward_return"], -bear_row["forward_return_raw"], places=8)

    def test_neutral_direction_abs(self):
        out = attach_forward_returns(self.signals, {"5m": self.tf_5m})
        neu_row = out[(out["direction"] == "neutral")].iloc[0]
        self.assertGreaterEqual(neu_row["forward_return"], 0)
        self.assertAlmostEqual(neu_row["forward_return"], abs(neu_row["forward_return_raw"]), places=8)

    def test_unfinished_signal_has_nan(self):
        out = attach_forward_returns(self.signals, {"5m": self.tf_5m})
        unfinished = out[out["timestamp"] == self.tf_5m.index[98]].iloc[0]
        self.assertTrue(pd.isna(unfinished["forward_return"]))

    def test_empty_signals(self):
        empty = self.signals.iloc[:0].copy()
        out = attach_forward_returns(empty, {"5m": self.tf_5m})
        self.assertEqual(len(out), 0)
        self.assertIn("forward_return", out.columns)


if __name__ == "__main__":
    unittest.main()
