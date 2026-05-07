"""Tests for DynamicPatternComposer."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pattern_composer import (  # noqa: E402
    ComposerConfig,
    DynamicPatternComposer,
)
from app.pattern_fitness.types import (  # noqa: E402
    FitnessCell,
    FitnessCellKey,
    FitnessTensor,
    FitnessTensorMeta,
)


def _make_tensor(cells: list[FitnessCell]) -> FitnessTensor:
    meta = FitnessTensorMeta(
        symbol="TEST",
        learned_at=datetime(2025, 1, 1),
        train_window_start=datetime(2025, 1, 1),
        train_window_end=datetime(2025, 6, 1),
        min_samples=30,
        fdr_alpha=0.05,
        n_cells_total=len(cells),
        n_cells_with_min_samples=len(cells),
        n_cells_active=sum(1 for c in cells if c.fdr_significant),
        forward_horizon_policy="test",
    )
    return FitnessTensor(
        meta=meta,
        cells={c.key(): c for c in cells},
    )


def _cell(pattern, tf, regime, direction, edge=0.01, sig=True) -> FitnessCell:
    return FitnessCell(
        pattern=pattern, timeframe=tf, cell_id=regime, direction=direction,
        n=50, edge_mean=edge, edge_std=0.005,
        edge_ci_low=edge - 0.002, edge_ci_high=edge + 0.002,
        win_rate=0.6, p_value=0.001, fdr_significant=sig,
        last_updated=datetime(2025, 6, 1),
    )


def _signal_row(pattern, tf, direction, conf=0.7, regime="trending_up|mid|normal|positive"):
    return {
        "pattern_name": pattern, "timeframe": tf, "direction": direction,
        "confidence": conf, "horizon_bars": 5,
        "suggested_target": None, "suggested_stop": None,
        "metadata": {}, "cell_id": regime,
    }


class TestComposerEntry(unittest.TestCase):
    def test_no_signals_holds(self):
        tensor = _make_tensor([])
        composer = DynamicPatternComposer(tensor)
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=pd.DataFrame())
        self.assertEqual(decision.action, "hold")

    def test_active_bull_signal_with_fitness_enters_long(self):
        cell = _cell("p1", "5m", "trending_up|mid|normal|positive", "bull", edge=0.02)
        tensor = _make_tensor([cell])
        cfg = ComposerConfig(entry_threshold=0.005)
        composer = DynamicPatternComposer(tensor, cfg)
        sigs = pd.DataFrame([_signal_row("p1", "5m", "bull", conf=0.7)])
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=sigs)
        self.assertEqual(decision.action, "enter_long")
        self.assertGreater(decision.ensemble_score, 0)
        self.assertEqual(decision.n_trusted_signals, 1)

    def test_signal_without_fitness_cell_doesnt_enter(self):
        tensor = _make_tensor([])  # no cells
        composer = DynamicPatternComposer(tensor)
        sigs = pd.DataFrame([_signal_row("p1", "5m", "bull")])
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=sigs)
        self.assertEqual(decision.action, "hold")
        self.assertEqual(decision.n_trusted_signals, 0)

    def test_negative_edge_cell_ignored(self):
        cell = _cell("p1", "5m", "trending_up|mid|normal|positive", "bull", edge=-0.02, sig=True)
        tensor = _make_tensor([cell])
        composer = DynamicPatternComposer(tensor)
        sigs = pd.DataFrame([_signal_row("p1", "5m", "bull")])
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=sigs)
        self.assertEqual(decision.action, "hold")

    def test_below_threshold_holds(self):
        cell = _cell("p1", "5m", "trending_up|mid|normal|positive", "bull", edge=0.001)
        tensor = _make_tensor([cell])
        cfg = ComposerConfig(entry_threshold=0.10)
        composer = DynamicPatternComposer(tensor, cfg)
        sigs = pd.DataFrame([_signal_row("p1", "5m", "bull", conf=0.5)])
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=sigs)
        self.assertEqual(decision.action, "hold")


class TestComposerMultiTF(unittest.TestCase):
    def test_multi_tf_agreement_amplifies(self):
        cells = [
            _cell("p1", "5m", "trending_up|mid|normal|positive", "bull", edge=0.01),
            _cell("p1", "1h", "trending_up|mid|normal|positive", "bull", edge=0.01),
        ]
        tensor = _make_tensor(cells)
        cfg = ComposerConfig(entry_threshold=0.001, multi_tf_bonus=0.5)
        composer = DynamicPatternComposer(tensor, cfg)
        sigs = pd.DataFrame([
            _signal_row("p1", "5m", "bull", conf=0.7),
            _signal_row("p1", "1h", "bull", conf=0.7),
        ])
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=sigs)
        # bonus = +50% over single-TF score
        single_tf_score = 0.7 * 0.01 * 2  # 2 signals, no bonus
        self.assertGreater(decision.ensemble_score, single_tf_score)

    def test_opposing_signals_cancel(self):
        cells = [
            _cell("p1", "5m", "trending_up|mid|normal|positive", "bull", edge=0.01),
            _cell("p2", "5m", "trending_up|mid|normal|positive", "bear", edge=0.01),
        ]
        tensor = _make_tensor(cells)
        composer = DynamicPatternComposer(tensor, ComposerConfig(entry_threshold=0.001))
        sigs = pd.DataFrame([
            _signal_row("p1", "5m", "bull", conf=0.7),
            _signal_row("p2", "5m", "bear", conf=0.7),
        ])
        decision = composer.compose(timestamp=datetime(2025, 1, 1), active_signals=sigs)
        # equal weights cancel → ~0 ensemble
        self.assertAlmostEqual(decision.ensemble_score, 0.0, places=8)
        self.assertEqual(decision.action, "hold")


class TestComposerExit(unittest.TestCase):
    def test_should_exit_long_on_strong_bear(self):
        composer = DynamicPatternComposer(_make_tensor([]), ComposerConfig(exit_threshold=0.001))
        self.assertTrue(composer.should_exit(-0.005, "long"))
        self.assertFalse(composer.should_exit(0.005, "long"))


if __name__ == "__main__":
    unittest.main()
