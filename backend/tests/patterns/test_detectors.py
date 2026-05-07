"""Tests for individual pattern detectors against synthetic data.

Each detector should:
  1. Detect its target pattern when synthetically planted (positive case).
  2. Not detect (or detect only with low confidence) on flat noise (negative).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.patterns.candle.engulfing import BullishEngulfing, BearishEngulfing  # noqa: E402
from app.patterns.candle.doji import Doji  # noqa: E402
from app.patterns.chart.double_top_bottom import DoubleTop, DoubleBottom  # noqa: E402
from app.patterns.indicator.ma_cross import GoldenCross, DeathCross  # noqa: E402
from app.patterns.volume.climax import VolumeClimax  # noqa: E402

from tests.patterns.synth import (  # noqa: E402
    bearish_engulfing_at,
    bullish_engulfing_at,
    doji_at,
    double_bottom,
    double_top,
    flat_noise,
    golden_cross_setup,
    volume_climax_at,
)


class TestBullishEngulfing(unittest.TestCase):
    def test_detects_planted(self):
        df = bullish_engulfing_at(n=50, idx_pos=30)
        d = BullishEngulfing()
        sigs = d.detect(df)
        self.assertGreaterEqual(len(sigs), 1)
        target_ts = df.index[30]
        matched = [s for s in sigs if s.timestamp == target_ts.to_pydatetime()]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].direction, "bull")
        self.assertGreater(matched[0].confidence, 0.5)

    def test_no_signal_in_flat_noise(self):
        df = flat_noise(n=200, vol=0.05, seed=99)
        sigs = BullishEngulfing().detect(df)
        self.assertLessEqual(len(sigs), 5)


class TestBearishEngulfing(unittest.TestCase):
    def test_detects_planted(self):
        df = bearish_engulfing_at(n=50, idx_pos=30)
        sigs = BearishEngulfing().detect(df)
        target_ts = df.index[30].to_pydatetime()
        matched = [s for s in sigs if s.timestamp == target_ts]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].direction, "bear")


class TestDoji(unittest.TestCase):
    def test_detects_planted(self):
        df = doji_at(n=50, idx_pos=30)
        sigs = Doji().detect(df)
        target_ts = df.index[30].to_pydatetime()
        matched = [s for s in sigs if s.timestamp == target_ts]
        self.assertGreaterEqual(len(matched), 1)
        self.assertEqual(matched[0].direction, "neutral")


class TestDoubleTop(unittest.TestCase):
    def test_detects_synthetic(self):
        df = double_top(n=100)
        sigs = DoubleTop().detect(df)
        self.assertGreaterEqual(len(sigs), 1)
        # Should be bear direction
        self.assertTrue(all(s.direction == "bear" for s in sigs))
        # Suggested target should be below neckline (i.e., target < stop)
        for s in sigs:
            self.assertIsNotNone(s.suggested_target)
            self.assertIsNotNone(s.suggested_stop)
            self.assertLess(s.suggested_target, s.suggested_stop)


class TestDoubleBottom(unittest.TestCase):
    def test_detects_synthetic(self):
        df = double_bottom(n=100)
        sigs = DoubleBottom().detect(df)
        self.assertGreaterEqual(len(sigs), 1)
        self.assertTrue(all(s.direction == "bull" for s in sigs))
        for s in sigs:
            self.assertGreater(s.suggested_target, s.suggested_stop)


class TestGoldenDeathCross(unittest.TestCase):
    def test_golden_cross_setup(self):
        df = golden_cross_setup(n=120)
        gc = GoldenCross().detect(df)
        dc = DeathCross().detect(df)
        # Should find at least one golden cross in our setup
        self.assertGreaterEqual(len(gc), 1)
        # Direction sanity
        for s in gc:
            self.assertEqual(s.direction, "bull")
        for s in dc:
            self.assertEqual(s.direction, "bear")


class TestVolumeClimax(unittest.TestCase):
    def test_bull_climax(self):
        df = volume_climax_at(n=60, idx_pos=40, kind="bull")
        sigs = VolumeClimax().detect(df)
        self.assertGreaterEqual(len(sigs), 1)
        target_ts = df.index[40].to_pydatetime()
        matched = [s for s in sigs if s.timestamp == target_ts]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].direction, "bull")

    def test_bear_climax(self):
        df = volume_climax_at(n=60, idx_pos=40, kind="bear")
        sigs = VolumeClimax().detect(df)
        target_ts = df.index[40].to_pydatetime()
        matched = [s for s in sigs if s.timestamp == target_ts]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].direction, "bear")


if __name__ == "__main__":
    unittest.main()
