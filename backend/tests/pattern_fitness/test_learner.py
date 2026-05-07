"""End-to-end FitnessLearner tests."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pattern_fitness import FitnessLearner  # noqa: E402
from app.pattern_fitness.learner import benjamini_hochberg_mask  # noqa: E402


def _ohlcv(n=500, drift=0.0005, vol=0.001, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01 09:00", periods=n, freq="5min")
    rets = drift + rng.normal(0, vol, n)
    closes = 100.0 * np.exp(rets.cumsum())
    return pd.DataFrame(
        {"open": closes, "high": closes * 1.001, "low": closes * 0.999, "close": closes,
         "volume": np.full(n, 1000)},
        index=idx,
    )


def _regime_df(ohlcv: pd.DataFrame, cell_id: str = "trending_up|mid|normal|positive") -> pd.DataFrame:
    """Synthetic regime DF: every bar is in the same cell, none warmup."""
    return pd.DataFrame(
        {"cell_id": [cell_id] * len(ohlcv), "is_warmup": [False] * len(ohlcv)},
        index=ohlcv.index,
    )


def _signals(ohlcv: pd.DataFrame, n_signals: int = 50, direction: str = "bull",
             pattern: str = "p1", tf: str = "5m") -> pd.DataFrame:
    """Synthetic signals, evenly spaced."""
    step = max(1, len(ohlcv) // (n_signals + 1))
    rows = []
    for i in range(n_signals):
        ix = (i + 1) * step
        if ix + 5 >= len(ohlcv):
            break
        rows.append({
            "timeframe": tf,
            "pattern_name": pattern,
            "timestamp": ohlcv.index[ix],
            "direction": direction,
            "confidence": 0.7,
            "horizon_bars": 5,
            "suggested_target": None,
            "suggested_stop": None,
            "metadata": {},
            "symbol": "TEST",
        })
    return pd.DataFrame(rows)


class TestBenjaminiHochberg(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(len(benjamini_hochberg_mask(np.array([]), 0.05)), 0)

    def test_all_pass(self):
        # all very small p-values
        ps = np.array([0.001, 0.002, 0.003])
        mask = benjamini_hochberg_mask(ps, 0.05)
        self.assertTrue(mask.all())

    def test_all_fail(self):
        ps = np.array([0.5, 0.6, 0.7])
        mask = benjamini_hochberg_mask(ps, 0.05)
        self.assertFalse(mask.any())

    def test_partial(self):
        # smallest p passes, others don't
        ps = np.array([0.001, 0.6, 0.7, 0.8])
        mask = benjamini_hochberg_mask(ps, 0.05)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1:].any())


class TestFitnessLearner(unittest.TestCase):
    def test_learn_returns_tensor_with_metadata(self):
        ohlcv = _ohlcv(500, drift=0.0005, vol=0.001, seed=1)
        signals = _signals(ohlcv, n_signals=50)
        regime = _regime_df(ohlcv)
        learner = FitnessLearner(min_samples=30)
        tensor = learner.learn(
            symbol="TEST",
            signals_df=signals,
            ohlcv_by_tf={"5m": ohlcv},
            regime_by_tf={"5m": regime},
        )
        self.assertEqual(tensor.meta.symbol, "TEST")
        self.assertGreater(tensor.meta.n_cells_total, 0)
        self.assertEqual(len(tensor), tensor.meta.n_cells_total)

    def test_drift_signal_detected_as_active(self):
        """A bull signal in a strong-drift series should pass FDR."""
        ohlcv = _ohlcv(500, drift=0.001, vol=0.0005, seed=2)
        signals = _signals(ohlcv, n_signals=80, direction="bull")
        regime = _regime_df(ohlcv)
        tensor = FitnessLearner(min_samples=30).learn(
            symbol="TEST",
            signals_df=signals,
            ohlcv_by_tf={"5m": ohlcv},
            regime_by_tf={"5m": regime},
        )
        active = tensor.all_active()
        self.assertEqual(len(active), 1)
        self.assertGreater(active[0].edge_mean, 0)
        self.assertGreater(active[0].n, 30)

    def test_random_walk_few_or_no_active(self):
        """Random walk should rarely produce active cells (FDR working)."""
        ohlcv = _ohlcv(500, drift=0.0, vol=0.001, seed=3)
        signals = _signals(ohlcv, n_signals=80, direction="bull")
        regime = _regime_df(ohlcv)
        tensor = FitnessLearner(min_samples=30, fdr_alpha=0.05).learn(
            symbol="TEST",
            signals_df=signals,
            ohlcv_by_tf={"5m": ohlcv},
            regime_by_tf={"5m": regime},
        )
        # Expect 0 or 1 false positives at alpha=0.05 for a single test
        self.assertLessEqual(len(tensor.all_active()), 1)

    def test_min_samples_filter(self):
        """Cells with fewer than min_samples should never be active."""
        ohlcv = _ohlcv(500, drift=0.001, vol=0.0005, seed=4)
        signals = _signals(ohlcv, n_signals=10)  # only 10 signals < 30 min_samples
        regime = _regime_df(ohlcv)
        tensor = FitnessLearner(min_samples=30).learn(
            symbol="TEST",
            signals_df=signals,
            ohlcv_by_tf={"5m": ohlcv},
            regime_by_tf={"5m": regime},
        )
        for cell in tensor.cells.values():
            if cell.n < 30:
                self.assertFalse(cell.is_active)

    def test_save_load_roundtrip(self):
        import tempfile
        ohlcv = _ohlcv(500, drift=0.0005, vol=0.001, seed=5)
        signals = _signals(ohlcv, n_signals=40)
        regime = _regime_df(ohlcv)
        tensor = FitnessLearner(min_samples=30).learn(
            symbol="TEST", signals_df=signals,
            ohlcv_by_tf={"5m": ohlcv}, regime_by_tf={"5m": regime},
        )
        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as f:
            FitnessLearner.save(tensor, f.name)
            loaded = FitnessLearner.load(f.name)
        self.assertEqual(loaded.meta.symbol, tensor.meta.symbol)
        self.assertEqual(len(loaded), len(tensor))

    def test_empty_signals_returns_empty_tensor(self):
        empty = pd.DataFrame(
            columns=["timeframe", "pattern_name", "timestamp", "direction",
                     "confidence", "horizon_bars", "suggested_target",
                     "suggested_stop", "metadata", "symbol"]
        )
        tensor = FitnessLearner().learn(
            symbol="TEST", signals_df=empty,
            ohlcv_by_tf={"5m": _ohlcv(100)},
            regime_by_tf={"5m": _regime_df(_ohlcv(100))},
        )
        self.assertEqual(len(tensor), 0)
        self.assertEqual(tensor.meta.n_cells_active, 0)


if __name__ == "__main__":
    unittest.main()
