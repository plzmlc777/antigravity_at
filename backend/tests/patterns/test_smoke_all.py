"""Smoke test for the entire PatternRegistry.

Verifies every registered detector:
  - Instantiates with default params
  - Runs detect() on realistic noisy OHLCV without raising
  - Every emitted signal passes PatternSignal validation (confidence in [0,1] etc.)
  - Direction is one of {bull, bear, neutral}

This is the safety net for the ~40+ pattern library — adding a new pattern
automatically goes through these checks.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.patterns import PatternRegistry, PatternSignal  # noqa: E402


def make_realistic_ohlcv(n: int = 500, seed: int = 7) -> pd.DataFrame:
    """Random walk with drift + intraday-style timestamps to exercise all detectors."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01 09:00", periods=n, freq="5min")
    rets = rng.normal(0.0, 0.005, n)
    closes = 1000.0 * np.exp(rets.cumsum())
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.003, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.003, n))
    volumes = rng.integers(800, 1500, n).astype(int)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


class TestAllDetectorsSmoke(unittest.TestCase):
    """Every registered detector must pass this contract."""

    @classmethod
    def setUpClass(cls):
        PatternRegistry.discover(force=True)
        cls.df = make_realistic_ohlcv()

    def test_target_count(self):
        """Phase 1 target ≈ 40+ detectors across 4 categories."""
        self.assertGreaterEqual(len(PatternRegistry.all()), 40)

    def test_each_category_populated(self):
        counts = PatternRegistry.category_counts()
        self.assertGreaterEqual(counts.get("chart", 0), 10)
        self.assertGreaterEqual(counts.get("candle", 0), 10)
        self.assertGreaterEqual(counts.get("indicator", 0), 6)
        self.assertGreaterEqual(counts.get("volume", 0), 4)

    def test_unique_names(self):
        names = [d.name for d in PatternRegistry.all()]
        self.assertEqual(len(names), len(set(names)), "duplicate pattern names")

    def test_all_run_without_exception(self):
        failures: list[tuple[str, str]] = []
        for det_cls in PatternRegistry.all():
            try:
                det = det_cls()
                _ = det.detect(self.df)
            except Exception as e:  # noqa: BLE001
                failures.append((det_cls.name, repr(e)))
        if failures:
            self.fail(f"Detectors raised: {failures}")

    def test_all_signals_valid(self):
        """Every emitted signal must pass dataclass validation
        (confidence ∈ [0,1], horizon_bars >= 1, valid direction)."""
        for det_cls in PatternRegistry.all():
            det = det_cls()
            for sig in det.detect(self.df):
                self.assertIsInstance(sig, PatternSignal)
                self.assertIn(sig.direction, ("bull", "bear", "neutral"))
                self.assertGreaterEqual(sig.confidence, 0.0)
                self.assertLessEqual(sig.confidence, 1.0)
                self.assertGreaterEqual(sig.horizon_bars, 1)
                self.assertEqual(sig.pattern_name, det_cls.name)

    def test_no_lookahead_in_signal_timestamp(self):
        """Signal timestamp must be within the input data's time range."""
        first_ts = self.df.index[0].to_pydatetime()
        last_ts = self.df.index[-1].to_pydatetime()
        for det_cls in PatternRegistry.all():
            det = det_cls()
            for sig in det.detect(self.df):
                self.assertGreaterEqual(sig.timestamp, first_ts)
                self.assertLessEqual(sig.timestamp, last_ts)


if __name__ == "__main__":
    unittest.main()
