"""End-to-end Backtester tests."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.pattern_composer import (  # noqa: E402
    Backtester,
    ComposerConfig,
    DynamicPatternComposer,
)
from app.pattern_fitness.types import (  # noqa: E402
    FitnessCell,
    FitnessTensor,
    FitnessTensorMeta,
)


def _make_ohlcv_1m(n=400, drift=0.0001) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2025-01-02 09:00", periods=n, freq="1min")
    rets = drift + rng.normal(0, 0.0003, n)
    closes = 1000.0 * np.exp(rets.cumsum())
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) * 1.0005
    lows = np.minimum(opens, closes) * 0.9995
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes,
         "volume": rng.integers(800, 1200, n)}, index=idx,
    )


def _make_tensor_with_one_active_cell() -> FitnessTensor:
    cell = FitnessCell(
        pattern="p1", timeframe="5m", cell_id="trending_up|mid|normal|positive",
        direction="bull", n=50, edge_mean=0.02, edge_std=0.005,
        edge_ci_low=0.018, edge_ci_high=0.022, win_rate=0.7,
        p_value=0.001, fdr_significant=True,
        last_updated=datetime(2025, 1, 1),
    )
    meta = FitnessTensorMeta(
        symbol="TEST", learned_at=datetime(2025, 1, 1),
        train_window_start=datetime(2025, 1, 1),
        train_window_end=datetime(2025, 6, 1),
        min_samples=30, fdr_alpha=0.05,
        n_cells_total=1, n_cells_with_min_samples=1, n_cells_active=1,
        forward_horizon_policy="test",
    )
    return FitnessTensor(meta=meta, cells={cell.key(): cell})


def _make_signals(ohlcv: pd.DataFrame, n_signals=5) -> pd.DataFrame:
    """Plant a few bull signals at known timestamps."""
    step = max(1, len(ohlcv) // (n_signals + 1))
    rows = []
    for i in range(n_signals):
        ix = (i + 1) * step
        rows.append({
            "symbol": "TEST",
            "pattern_name": "p1", "timeframe": "5m",
            "timestamp": ohlcv.index[ix],
            "direction": "bull",
            "confidence": 0.7, "horizon_bars": 30,
            "suggested_target": None, "suggested_stop": None,
            "metadata": {},
        })
    return pd.DataFrame(rows)


def _make_regime_df(ohlcv: pd.DataFrame, cell_id: str = "trending_up|mid|normal|positive") -> pd.DataFrame:
    return pd.DataFrame(
        {"cell_id": [cell_id] * len(ohlcv), "is_warmup": [False] * len(ohlcv)},
        index=ohlcv.index,
    )


class TestBacktester(unittest.TestCase):
    def test_run_completes_without_error(self):
        ohlcv = _make_ohlcv_1m(400, drift=0.0001)
        signals = _make_signals(ohlcv, n_signals=5)
        regime = _make_regime_df(ohlcv)
        tensor = _make_tensor_with_one_active_cell()
        composer = DynamicPatternComposer(tensor, ComposerConfig(entry_threshold=0.001))
        bt = Backtester(composer, initial_capital=1_000_000)
        result = bt.run(
            symbol="TEST", ohlcv_1m=ohlcv, signals_df=signals,
            regime_by_tf={"5m": regime}, eval_freq_minutes=1,
        )
        self.assertEqual(result.symbol, "TEST")
        self.assertEqual(result.initial_capital, 1_000_000)
        # equity curve has one entry per bar
        self.assertEqual(len(result.equity_curve), len(ohlcv))

    def test_uptrend_with_bull_signals_produces_positive_return(self):
        """Strong uptrend + bull signals + active fitness → expect positive return."""
        ohlcv = _make_ohlcv_1m(800, drift=0.0008)  # strong drift
        signals = _make_signals(ohlcv, n_signals=10)
        regime = _make_regime_df(ohlcv)
        tensor = _make_tensor_with_one_active_cell()
        cfg = ComposerConfig(entry_threshold=0.001, sl_pct=0.05, tp_pct=0.10, time_stop_bars=120)
        composer = DynamicPatternComposer(tensor, cfg)
        bt = Backtester(composer, initial_capital=1_000_000, fee_rate=0.0)
        result = bt.run(
            symbol="TEST", ohlcv_1m=ohlcv, signals_df=signals,
            regime_by_tf={"5m": regime}, eval_freq_minutes=1,
        )
        self.assertGreater(result.n_trades, 0)
        self.assertGreater(result.total_return_pct, 0)

    def test_no_active_cells_no_trades(self):
        ohlcv = _make_ohlcv_1m(400, drift=0.0001)
        signals = _make_signals(ohlcv, n_signals=5)
        regime = _make_regime_df(ohlcv)
        # tensor with no active cells
        meta = FitnessTensorMeta(
            symbol="TEST", learned_at=datetime(2025, 1, 1),
            train_window_start=datetime(2025, 1, 1),
            train_window_end=datetime(2025, 6, 1),
            min_samples=30, fdr_alpha=0.05,
            n_cells_total=0, n_cells_with_min_samples=0, n_cells_active=0,
            forward_horizon_policy="test",
        )
        tensor = FitnessTensor(meta=meta, cells={})
        composer = DynamicPatternComposer(tensor)
        bt = Backtester(composer, initial_capital=1_000_000)
        result = bt.run(
            symbol="TEST", ohlcv_1m=ohlcv, signals_df=signals,
            regime_by_tf={"5m": regime}, eval_freq_minutes=1,
        )
        self.assertEqual(result.n_trades, 0)


if __name__ == "__main__":
    unittest.main()
