"""Tests for PatternDetector ABC, PatternSignal validation, and PatternRegistry."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

# Make backend/ importable
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.patterns import (  # noqa: E402
    PatternDetector,
    PatternRegistry,
    PatternSignal,
)


class TestPatternSignal(unittest.TestCase):
    def test_construct_valid(self):
        s = PatternSignal(
            pattern_name="x",
            timestamp=datetime(2025, 1, 1),
            direction="bull",
            confidence=0.7,
            horizon_bars=5,
        )
        self.assertEqual(s.pattern_name, "x")
        self.assertEqual(s.confidence, 0.7)

    def test_invalid_confidence(self):
        with self.assertRaises(ValueError):
            PatternSignal(
                pattern_name="x", timestamp=datetime(2025, 1, 1),
                direction="bull", confidence=1.5, horizon_bars=5,
            )
        with self.assertRaises(ValueError):
            PatternSignal(
                pattern_name="x", timestamp=datetime(2025, 1, 1),
                direction="bull", confidence=-0.1, horizon_bars=5,
            )

    def test_invalid_horizon(self):
        with self.assertRaises(ValueError):
            PatternSignal(
                pattern_name="x", timestamp=datetime(2025, 1, 1),
                direction="bull", confidence=0.5, horizon_bars=0,
            )

    def test_invalid_direction(self):
        with self.assertRaises(ValueError):
            PatternSignal(
                pattern_name="x", timestamp=datetime(2025, 1, 1),
                direction="up",  # type: ignore
                confidence=0.5, horizon_bars=5,
            )


class TestPatternRegistry(unittest.TestCase):
    def test_discover_finds_detectors(self):
        PatternRegistry.discover(force=True)
        names = PatternRegistry.names()
        self.assertGreaterEqual(len(names), 6)
        # Spot-check a few we know we wrote
        for required in [
            "bullish_engulfing", "bearish_engulfing", "doji",
            "double_top", "double_bottom",
            "golden_cross", "death_cross",
            "volume_climax",
        ]:
            self.assertIn(required, names)

    def test_categories_balanced(self):
        PatternRegistry.discover(force=True)
        counts = PatternRegistry.category_counts()
        for cat in ("candle", "chart", "indicator", "volume"):
            self.assertGreaterEqual(counts.get(cat, 0), 1, f"no detectors in {cat}")

    def test_get_unknown_raises(self):
        with self.assertRaises(KeyError):
            PatternRegistry.get("nonexistent_pattern_xyz")

    def test_instantiate_all(self):
        instances = PatternRegistry.instantiate_all()
        self.assertGreaterEqual(len(instances), 6)
        for inst in instances:
            self.assertIsInstance(inst, PatternDetector)


if __name__ == "__main__":
    unittest.main()
