"""End-to-end backtester smoke tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.composer_framework import (  # noqa: E402
    GenericBacktester,
    LongOnlyThresholdPolicy,
    Pipeline,
    PipelineConfig,
    SourceContext,
)
from app.composer_framework.composers import LGBMComposerAdapter  # noqa: E402
from app.composer_framework.sources import MarketStateSource  # noqa: E402


def _synth_ohlcv(n=300, drift=0.001, vol=0.01, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="1D")
    rets = drift + rng.normal(0, vol, n)
    closes = 100 * np.exp(rets.cumsum())
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.005, n))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.005, n))
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": rng.integers(800, 1200, n)},
        index=idx,
    )


class TestStaticBacktest(unittest.TestCase):
    def test_runs_to_completion(self):
        df = _synth_ohlcv(n=300, drift=0.001)
        ctx = SourceContext(symbol="SYNTH", eval_freq_minutes=1440, ohlcv_eval=df)
        pipe = Pipeline(
            sources=[MarketStateSource()],
            composer=LGBMComposerAdapter(),
            policy=LongOnlyThresholdPolicy(entry_threshold=0.001, sl_pct=0.05, tp_pct=0.1),
        )
        bt = GenericBacktester(initial_capital=10_000)
        kpis = bt.run_static(pipeline=pipe, ctx=ctx, train_frac=0.5)
        self.assertEqual(kpis.symbol, "SYNTH")
        self.assertEqual(kpis.initial_capital, 10_000)
        # equity curve covers test half
        self.assertGreater(len(kpis.equity_curve), 100)
        # KPIs computed
        self.assertGreaterEqual(kpis.n_trades, 0)
        self.assertIsInstance(kpis.total_return_pct, float)
        self.assertIsInstance(kpis.max_drawdown_pct, float)


class TestWalkForward(unittest.TestCase):
    def test_runs_to_completion(self):
        df = _synth_ohlcv(n=400, drift=0.0008)
        ctx = SourceContext(symbol="WF", eval_freq_minutes=1440, ohlcv_eval=df)
        pipe = Pipeline(
            sources=[MarketStateSource()],
            composer=LGBMComposerAdapter(),
            policy=LongOnlyThresholdPolicy(entry_threshold=0.001),
        )
        bt = GenericBacktester(initial_capital=10_000)
        kpis = bt.run_walk_forward(
            pipeline=pipe, ctx=ctx,
            train_window_bars=100, retrain_step_bars=30,
        )
        self.assertEqual(kpis.symbol, "WF")
        self.assertGreaterEqual(kpis.n_trades, 0)


if __name__ == "__main__":
    unittest.main()
