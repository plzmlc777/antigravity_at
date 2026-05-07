"""Tests for ABCs and structural invariants of the composer framework."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.composer_framework import (  # noqa: E402
    Action,
    Composer,
    LongOnlyThresholdPolicy,
    LongShortThresholdPolicy,
    Pipeline,
    PipelineConfig,
    PolicyContext,
    SignalSource,
    SourceContext,
    source_feature_prefix,
)
from app.composer_framework.composers import LGBMComposerAdapter  # noqa: E402


def _synth_ohlcv(n=300, drift=0.0005, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="1D")
    rets = drift + rng.normal(0, 0.02, n)
    closes = 100 * np.exp(rets.cumsum())
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.01
    lows = np.minimum(opens, closes) * 0.99
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": rng.integers(800, 1200, n)},
        index=idx,
    )


class TestSignalSourceContract(unittest.TestCase):
    def test_prefix_helper(self):
        self.assertEqual(source_feature_prefix("pattern"), "pattern_")
        self.assertEqual(source_feature_prefix("kr_flow"), "kr_flow_")
        self.assertEqual(source_feature_prefix("MARKET"), "market_")

    def test_subclass_auto_prefix(self):
        class FooSource(SignalSource):
            name = "foo"
            def build_features(self, ctx): return pd.DataFrame()
        self.assertEqual(FooSource.feature_prefix, "foo_")

    def test_explicit_prefix_overrides_auto(self):
        class BarSource(SignalSource):
            name = "bar"
            feature_prefix = "b_"
            def build_features(self, ctx): return pd.DataFrame()
        self.assertEqual(BarSource.feature_prefix, "b_")

    def test_prefixed_helper(self):
        class TestSrc(SignalSource):
            name = "test"
            def build_features(self, ctx):
                df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
                return self._prefixed(df)
        s = TestSrc()
        df = s.build_features(SourceContext(symbol="X", eval_freq_minutes=1440))
        self.assertEqual(list(df.columns), ["test_a", "test_b"])


class TestPolicy(unittest.TestCase):
    def test_long_only_enters_on_positive_pred(self):
        policy = LongOnlyThresholdPolicy(entry_threshold=0.005, sl_pct=0.04, tp_pct=0.10)
        ctx = PolicyContext(timestamp=datetime(2025, 1, 1), prediction=0.01,
                            open_price=100.0, high_price=101.0, low_price=99.0, close_price=100.5,
                            in_position=False, side="flat")
        action = policy.decide(ctx)
        self.assertEqual(action.kind, "enter_long")
        self.assertAlmostEqual(action.sl_price, 96.0, places=5)
        self.assertAlmostEqual(action.tp_price, 110.0, places=5)

    def test_long_only_holds_on_negative(self):
        policy = LongOnlyThresholdPolicy(entry_threshold=0.005)
        ctx = PolicyContext(timestamp=datetime(2025, 1, 1), prediction=-0.01,
                            open_price=100, high_price=101, low_price=99, close_price=100,
                            in_position=False, side="flat")
        self.assertEqual(policy.decide(ctx).kind, "hold")

    def test_long_short_enters_short(self):
        policy = LongShortThresholdPolicy(entry_threshold=0.005)
        ctx = PolicyContext(timestamp=datetime(2025, 1, 1), prediction=-0.02,
                            open_price=100, high_price=101, low_price=99, close_price=100,
                            in_position=False, side="flat")
        self.assertEqual(policy.decide(ctx).kind, "enter_short")

    def test_time_stop(self):
        policy = LongOnlyThresholdPolicy(max_hold_bars=5)
        ctx = PolicyContext(timestamp=datetime(2025, 1, 1), prediction=0.01,
                            open_price=100, high_price=101, low_price=99, close_price=100,
                            in_position=True, side="long", entry_price=98, bars_held=5)
        self.assertEqual(policy.decide(ctx).kind, "exit")


class _FakeSource(SignalSource):
    name = "fake"

    def __init__(self, columns):
        self._columns = columns

    def build_features(self, ctx):
        df = pd.DataFrame(
            {c: range(len(ctx.ohlcv_eval)) for c in self._columns},
            index=ctx.ohlcv_eval.index,
        )
        return self._prefixed(df)


class _FakeSource2(_FakeSource):
    name = "fake2"


class TestPipelineFeatureBuilding(unittest.TestCase):
    def test_duplicate_prefix_rejected(self):
        composer = LGBMComposerAdapter()
        policy = LongOnlyThresholdPolicy()
        with self.assertRaises(ValueError):
            Pipeline(
                sources=[_FakeSource(["a"]), _FakeSource(["b"])],
                composer=composer, policy=policy,
            )

    def test_concat_with_different_prefixes(self):
        df = _synth_ohlcv()
        ctx = SourceContext(symbol="X", eval_freq_minutes=1440, ohlcv_eval=df)
        feat = Pipeline(
            sources=[_FakeSource(["a"]), _FakeSource2(["b"])],
            composer=LGBMComposerAdapter(),
            policy=LongOnlyThresholdPolicy(),
        ).build_features(ctx)
        self.assertIn("fake_a", feat.columns)
        self.assertIn("fake2_b", feat.columns)
        self.assertIn("target_fwd_ret", feat.columns)


class TestPipelineFitPredict(unittest.TestCase):
    def test_end_to_end_with_synth_data(self):
        df = _synth_ohlcv(n=200, drift=0.001)
        ctx = SourceContext(symbol="X", eval_freq_minutes=1440, ohlcv_eval=df)
        from app.composer_framework.sources import MarketStateSource
        pipe = Pipeline(
            sources=[MarketStateSource()],
            composer=LGBMComposerAdapter(),
            policy=LongOnlyThresholdPolicy(),
        )
        feat = pipe.build_features(ctx)
        # Drop NaNs from rolling/forward windows
        train = feat.iloc[:120]
        test = feat.iloc[120:]
        pipe.fit(train)
        preds = pipe.predict(test)
        self.assertEqual(len(preds), len(test))
        self.assertFalse(np.isnan(preds).all())


if __name__ == "__main__":
    unittest.main()
