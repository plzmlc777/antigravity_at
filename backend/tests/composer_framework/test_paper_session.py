"""Tests for PaperSession + SessionStore + PipelineSpec construction."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.composer_framework import (  # noqa: E402
    PaperSession,
    SessionStore,
    build_pipeline,
    validate_spec,
)


_VALID_SPEC = {
    "sources": [
        {"type": "market_state", "kwargs": {}},
        {"type": "regime", "kwargs": {"daily_preset": True}},
    ],
    "composer": {"type": "lgbm", "kwargs": {}},
    "policy": {
        "type": "long_only_threshold",
        "kwargs": {"entry_threshold": 0.005, "sl_pct": 0.04, "tp_pct": 0.10, "max_hold_bars": 5},
    },
    "config": {"eval_freq_minutes": 1440, "forward_bars": 5},
}


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_no_errors(self):
        self.assertEqual(validate_spec(_VALID_SPEC), [])

    def test_unknown_source_type(self):
        spec = {**_VALID_SPEC, "sources": [{"type": "nonexistent_xyz"}]}
        errs = validate_spec(spec)
        self.assertTrue(any("nonexistent_xyz" in e for e in errs))

    def test_missing_source_type_key(self):
        spec = {**_VALID_SPEC, "sources": [{"kwargs": {}}]}
        errs = validate_spec(spec)
        self.assertTrue(any("type missing" in e for e in errs))


class TestPipelineBuild(unittest.TestCase):
    def test_build_minimal(self):
        # only stateless sources (no signals/flow needed)
        pipe = build_pipeline(_VALID_SPEC)
        self.assertEqual(len(pipe.sources), 2)
        # composer + policy should be set
        self.assertIsNotNone(pipe.composer)
        self.assertIsNotNone(pipe.policy)

    def test_build_with_pattern_requires_signals(self):
        spec = {
            **_VALID_SPEC,
            "sources": _VALID_SPEC["sources"] + [{"type": "pattern", "kwargs": {}}],
        }
        with self.assertRaises(KeyError):
            build_pipeline(spec)
        # but with runtime data it succeeds
        empty_signals = pd.DataFrame(columns=[
            "pattern_name", "timestamp", "direction", "confidence", "timeframe"])
        pipe = build_pipeline(spec, runtime_data={"signals_df": empty_signals})
        self.assertEqual(len(pipe.sources), 3)

    def test_build_with_kr_flow_requires_flow_or_symbol(self):
        spec = {
            **_VALID_SPEC,
            "sources": _VALID_SPEC["sources"] + [{"type": "kr_flow", "kwargs": {}}],
        }
        with self.assertRaises(KeyError):
            build_pipeline(spec)


class TestSessionRoundTrip(unittest.TestCase):
    def test_save_load_session(self):
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(td)
            s = PaperSession(
                session_id="", name="test_sess", symbol="X",
                pipeline_spec=_VALID_SPEC, initial_capital=1_000_000,
            )
            store.save(s)
            loaded = store.load(s.session_id)
            self.assertEqual(loaded.name, "test_sess")
            self.assertEqual(loaded.symbol, "X")
            self.assertAlmostEqual(loaded.cash, 1_000_000)
            self.assertEqual(loaded.side, "flat")

    def test_list_all(self):
        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(td)
            for i in range(3):
                store.save(PaperSession(
                    session_id="", name=f"s{i}", symbol="X",
                    pipeline_spec=_VALID_SPEC,
                ))
            self.assertEqual(len(store.list_all()), 3)


class TestOrchestrator(unittest.TestCase):
    def test_run_cycle_with_synthetic_data(self):
        from app.composer_framework import (  # local imports
            PaperOrchestrator, RuntimeBundle, SourceContext,
        )

        # synthetic 1m and daily-eval bars
        rng = np.random.default_rng(0)
        idx_1m = pd.date_range("2025-01-01 09:00", periods=600, freq="1min")
        rets = rng.normal(0.0001, 0.0005, len(idx_1m))
        closes = 100.0 * np.exp(rets.cumsum())
        opens = np.concatenate([[closes[0]], closes[:-1]])
        highs = np.maximum(opens, closes) * 1.001
        lows = np.minimum(opens, closes) * 0.999
        df_1m = pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes,
             "volume": rng.integers(900, 1100, len(idx_1m))},
            index=idx_1m,
        )

        # daily eval needs ≥ 200 daily bars; synthesize directly
        idx_d = pd.date_range("2025-01-01", periods=300, freq="1D")
        rets_d = rng.normal(0.001, 0.01, 300)
        closes_d = 100.0 * np.exp(rets_d.cumsum())
        opens_d = np.concatenate([[closes_d[0]], closes_d[:-1]])
        df_eval = pd.DataFrame(
            {"open": opens_d, "high": closes_d * 1.01, "low": closes_d * 0.99,
             "close": closes_d, "volume": rng.integers(900, 1100, 300)},
            index=idx_d,
        )

        with tempfile.TemporaryDirectory() as td:
            store = SessionStore(td)
            session = PaperSession(
                session_id="", name="t1", symbol="SYNTH",
                pipeline_spec=_VALID_SPEC, initial_capital=10_000,
            )
            store.save(session)

            orch = PaperOrchestrator(store)
            bundle = RuntimeBundle(ohlcv_1m=df_1m, ohlcv_eval=df_eval)
            cycle = orch.run_cycle(session, bundle)
            self.assertIsNotNone(cycle.timestamp)
            self.assertEqual(session.n_cycles, 1)
            self.assertIn(session.side, ("flat", "long"))


if __name__ == "__main__":
    unittest.main()
