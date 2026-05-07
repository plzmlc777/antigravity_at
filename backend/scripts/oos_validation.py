#!/usr/bin/env python3
"""Out-of-sample validation: train fitness on first half, test on second.

If the fitness tensor's edges are real (not overfit), OOS top cells should
roughly match IS top cells. If they diverge wildly, the IS edges were spurious.

Usage:
    python -m scripts.oos_validation --symbol 005930 --days 365
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.pattern_composer import (  # noqa: E402
    EventBacktestConfig,
    EventDrivenBacktester,
    FloorBacktestConfig,
    PositionFloorBacktester,
)
from app.pattern_fitness import FitnessLearner  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.pattern_scanner.types import SUPPORTED_TIMEFRAMES  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def load_1m(symbol: str, days: int) -> pd.DataFrame:
    db = SessionLocal()
    try:
        end = datetime.now().replace(second=0, microsecond=0)
        start = end - timedelta(days=days)
        sql = text("""SELECT timestamp, open, high, low, close, volume FROM ohlcv
                     WHERE symbol = :sym AND time_frame = '1m' AND timestamp >= :start
                     ORDER BY timestamp ASC""")
        rows = db.execute(sql, {"sym": symbol, "start": start}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--initial-capital", type=float, default=3_000_000)
    args = p.parse_args()

    sig_path = ROOT / "runs" / "pattern_scanner" / f"{args.symbol}__{args.days}d__signals.joblib"
    print(f"Loading signals + 1m + regimes...")
    signals = joblib.load(sig_path)
    df_1m = load_1m(args.symbol, args.days)

    midpoint = df_1m.index[len(df_1m) // 2]
    df_1m_train = df_1m.loc[:midpoint]
    df_1m_test = df_1m.loc[midpoint:]
    sig_train = signals[pd.to_datetime(signals["timestamp"]) <= midpoint].copy()
    sig_test = signals[pd.to_datetime(signals["timestamp"]) > midpoint].copy()

    print(f"Train: {df_1m_train.index[0]} → {midpoint} ({len(df_1m_train)} bars, {len(sig_train)} signals)")
    print(f"Test : {midpoint} → {df_1m.index[-1]} ({len(df_1m_test)} bars, {len(sig_test)} signals)")

    # Build TF + regime for FULL window (regime classifier needs warmup; train uses train data only)
    print("\nBuilding regimes for train + test windows separately...")
    ohlcv_by_tf_train = {tf: resample_ohlcv(df_1m_train, tf) for tf in SUPPORTED_TIMEFRAMES}
    ohlcv_by_tf_test = {tf: resample_ohlcv(df_1m_test, tf) for tf in SUPPORTED_TIMEFRAMES}
    regime_by_tf_train = {}
    regime_by_tf_test = {}
    for tf in SUPPORTED_TIMEFRAMES:
        cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
        regime_by_tf_train[tf] = cls.classify(ohlcv_by_tf_train[tf])
        regime_by_tf_test[tf] = cls.classify(ohlcv_by_tf_test[tf])

    # 1. TRAIN: Learn fitness on train half only
    print("\nLearning fitness on TRAIN half...")
    learner = FitnessLearner(min_samples=20, fdr_alpha=0.05)
    fitness_train = learner.learn(
        symbol=args.symbol,
        signals_df=sig_train,
        ohlcv_by_tf=ohlcv_by_tf_train,
        regime_by_tf=regime_by_tf_train,
    )
    print(f"  IS active cells: {fitness_train.meta.n_cells_active} / {fitness_train.meta.n_cells_with_min_samples} eligible")

    # 2. TEST: Use train fitness on test signals
    print("\nRunning event-driven backtest on TEST half with TRAIN fitness...")
    bt = EventDrivenBacktester(
        fitness=fitness_train, initial_capital=args.initial_capital,
        config=EventBacktestConfig(sl_pct=0.02, tp_pct=0.04, long_only=True),
    )
    r_event = bt.run(
        symbol=args.symbol, ohlcv_1m=df_1m_test,
        ohlcv_by_tf=ohlcv_by_tf_test,
        signals_df=sig_test, regime_by_tf=regime_by_tf_test,
    )

    # 3. Compare to test-half buy-hold
    bh_test = (df_1m_test.iloc[-1]["close"] - df_1m_test.iloc[0]["open"]) / df_1m_test.iloc[0]["open"]

    # 4. ALSO compute IS-fitness's "would-be" edge if applied to TEST signals
    # — measure top-cell decay
    sig_test_with_cell = sig_test.copy()
    sig_test_with_cell["timestamp"] = pd.to_datetime(sig_test_with_cell["timestamp"])
    sig_test_with_cell["cell_id"] = pd.NA
    for tf, gidx in sig_test_with_cell.groupby("timeframe").groups.items():
        rdf = regime_by_tf_test.get(tf)
        if rdf is None: continue
        sub = sig_test_with_cell.loc[gidx]
        mapped = rdf.reindex(sub["timestamp"].values)
        sig_test_with_cell.loc[sub.index, "cell_id"] = mapped["cell_id"].values
    sig_test_with_cell = sig_test_with_cell.dropna(subset=["cell_id"])

    # For each test signal, did the train fitness say it's active+positive? If so, what was the actual outcome?
    from app.pattern_fitness.forward_returns import attach_forward_returns
    sig_test_fwd = attach_forward_returns(sig_test_with_cell, ohlcv_by_tf_test).dropna(subset=["forward_return"])

    is_active_in_train = []
    fwd_returns_active = []
    for _, row in sig_test_fwd.iterrows():
        cell = fitness_train.get(row["pattern_name"], row["timeframe"], str(row["cell_id"]), row["direction"])
        if cell and cell.fdr_significant and cell.edge_mean > 0 and row["direction"] in ("bull","bear"):
            fwd_returns_active.append(row["forward_return"])
            is_active_in_train.append(True)
    fwd_returns_active = np.array(fwd_returns_active)

    print()
    print(f"=== OUT-OF-SAMPLE VALIDATION ===")
    print(f"Test-half buy-hold:           {bh_test*100:+.2f}%")
    print(f"Test-half event-driven (long-only):")
    print(f"  trades={r_event.n_trades}, return={r_event.total_return_pct*100:+.2f}%, sharpe={r_event.sharpe_ratio:.2f}, win={r_event.win_rate*100:.1f}%")
    print()
    print(f"Train fitness applied to test signals (no overlap rules, just naive):")
    if len(fwd_returns_active):
        print(f"  IS-active signals in test: {len(fwd_returns_active)}")
        print(f"  Mean fwd return: {fwd_returns_active.mean()*100:+.3f}%")
        print(f"  Win rate: {(fwd_returns_active > 0).mean()*100:.1f}%")
        print(f"  Sum: {fwd_returns_active.sum()*100:+.2f}%")
        print(f"  Sharpe (per-trade × sqrt(n)): {fwd_returns_active.mean()/fwd_returns_active.std()*np.sqrt(len(fwd_returns_active)):.2f}")
    else:
        print("  No signals were both train-active AND in test window")

    # 5. IS edge vs OOS edge per pattern
    print()
    print(f"=== IS edge vs OOS realized (per pattern, top-5 IS by edge) ===")
    is_top = sorted(
        (c for c in fitness_train.cells.values() if c.is_active and c.direction in ("bull","bear")),
        key=lambda c: -c.edge_mean,
    )[:8]
    for c in is_top:
        # find this exact cell's signals in test
        in_test = sig_test_fwd[
            (sig_test_fwd["pattern_name"] == c.pattern)
            & (sig_test_fwd["timeframe"] == c.timeframe)
            & (sig_test_fwd["cell_id"] == c.cell_id)
            & (sig_test_fwd["direction"] == c.direction)
        ]
        if len(in_test) == 0:
            print(f"  {c.pattern:25s} {c.timeframe:3s} {c.direction:5s} cell '{c.cell_id[:30]:30s}' IS edge={c.edge_mean*100:+.2f}% n={c.n}  | OOS: 0 signals")
        else:
            oos_ret = in_test["forward_return"].mean()
            print(f"  {c.pattern:25s} {c.timeframe:3s} {c.direction:5s} cell '{c.cell_id[:30]:30s}' IS edge={c.edge_mean*100:+.2f}% n={c.n}  | OOS edge={oos_ret*100:+.2f}% n={len(in_test)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
