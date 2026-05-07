#!/usr/bin/env python3
"""Walk-forward validation: retrain fitness monthly, backtest forward 1 month.

If pattern alpha is real but regime-dependent, walk-forward (continuous
retraining) should recover it where a single static fitness fails OOS.

Algorithm:
  For each test month i ∈ [train_min_months, ... last]:
    - train on data up to start of month i
    - test on month i
    - record trades + KPIs

Output: per-month KPI table + aggregate stats.

Usage:
    python -m scripts.walkforward_backtest --symbol 005930 --days 365 \
        --train-min-months 3 --test-month-step 1
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
    p.add_argument("--train-min-months", type=int, default=3,
                   help="minimum months of data needed before first test")
    p.add_argument("--test-month-step", type=int, default=1, help="test window length (months)")
    p.add_argument("--initial-capital", type=float, default=3_000_000)
    p.add_argument("--min-samples", type=int, default=15,
                   help="min samples per cell (lower than full-year because windows are smaller)")
    args = p.parse_args()

    sig_path = ROOT / "runs" / "pattern_scanner" / f"{args.symbol}__{args.days}d__signals.joblib"
    print("Loading signals + 1m...")
    signals = joblib.load(sig_path)
    signals["timestamp"] = pd.to_datetime(signals["timestamp"])
    df_1m = load_1m(args.symbol, args.days)

    # month boundaries
    start = df_1m.index[0].normalize()
    end = df_1m.index[-1].normalize()
    months = pd.date_range(start.replace(day=1), end + pd.Timedelta(days=31), freq="MS")
    months = months[(months >= start.replace(day=1)) & (months <= end + pd.Timedelta(days=1))]

    print(f"Symbol: {args.symbol}, full window: {start.date()} → {end.date()}")
    print(f"Months identified: {[m.strftime('%Y-%m') for m in months]}")
    print(f"Train min months: {args.train_min_months}")
    print()

    capital = args.initial_capital
    all_trades = []
    monthly_kpis = []
    bh_each_month = []

    for i, month_start in enumerate(months):
        if i < args.train_min_months:
            continue
        if i + args.test_month_step > len(months):
            break
        train_end = month_start
        test_start = month_start
        test_end = months[i + args.test_month_step] if i + args.test_month_step < len(months) else df_1m.index[-1]

        df_train = df_1m.loc[:train_end]
        df_test = df_1m.loc[test_start:test_end]
        if len(df_test) < 100:
            continue
        sig_train = signals[signals["timestamp"] <= train_end].copy()
        sig_test = signals[(signals["timestamp"] > test_start) & (signals["timestamp"] <= test_end)].copy()

        # Build TF + regime for train and test
        ohlcv_tf_train = {tf: resample_ohlcv(df_train, tf) for tf in SUPPORTED_TIMEFRAMES}
        ohlcv_tf_test = {tf: resample_ohlcv(df_test, tf) for tf in SUPPORTED_TIMEFRAMES}
        regime_tf_train, regime_tf_test = {}, {}
        for tf in SUPPORTED_TIMEFRAMES:
            cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
            regime_tf_train[tf] = cls.classify(ohlcv_tf_train[tf])
            regime_tf_test[tf] = cls.classify(ohlcv_tf_test[tf])

        # Train fitness on data up to month_start
        learner = FitnessLearner(min_samples=args.min_samples, fdr_alpha=0.05)
        fitness = learner.learn(
            symbol=args.symbol, signals_df=sig_train,
            ohlcv_by_tf=ohlcv_tf_train, regime_by_tf=regime_tf_train,
        )

        # Backtest on test month
        bt = EventDrivenBacktester(
            fitness=fitness, initial_capital=capital,
            config=EventBacktestConfig(sl_pct=0.02, tp_pct=0.04, long_only=True),
        )
        r = bt.run(
            symbol=args.symbol, ohlcv_1m=df_test,
            ohlcv_by_tf=ohlcv_tf_test, signals_df=sig_test,
            regime_by_tf=regime_tf_test,
        )

        capital_before = capital
        capital = r.final_capital
        ret_pct = r.total_return_pct
        bh_month = (df_test.iloc[-1]["close"] - df_test.iloc[0]["open"]) / df_test.iloc[0]["open"]
        all_trades.extend(r.trades)
        monthly_kpis.append({
            "month": month_start.strftime("%Y-%m"),
            "n_active_cells": fitness.meta.n_cells_active,
            "n_eligible": fitness.meta.n_cells_with_min_samples,
            "trades": r.n_trades,
            "wf_return": ret_pct,
            "bh_return": bh_month,
            "win_rate": r.win_rate,
        })
        bh_each_month.append(bh_month)
        print(f"  Test {month_start.strftime('%Y-%m')}: train_n_cells_active={fitness.meta.n_cells_active}, "
              f"test_trades={r.n_trades}, WF={ret_pct*100:+.2f}%, BH={bh_month*100:+.2f}%")

    # Aggregate
    print()
    print("=" * 100)
    print(f"{'Month':10s} {'Active':>7s} {'Eligible':>9s} {'Trades':>7s} {'WF Ret':>8s} {'BH Ret':>8s} {'Win':>5s}")
    print("-" * 100)
    for k in monthly_kpis:
        print(f"{k['month']:10s} {k['n_active_cells']:>7d} {k['n_eligible']:>9d} {k['trades']:>7d} "
              f"{k['wf_return']*100:>+7.2f}% {k['bh_return']*100:>+7.2f}% {k['win_rate']*100:>4.0f}%")
    print("-" * 100)

    final_ret = (capital - args.initial_capital) / args.initial_capital
    bh_compound = np.prod([1 + r for r in bh_each_month]) - 1
    print(f"WF compound:  {final_ret*100:+.2f}% (capital {args.initial_capital:,.0f} → {capital:,.0f})")
    print(f"BH compound:  {bh_compound*100:+.2f}%")
    print(f"Total trades: {len(all_trades)}")
    if len(all_trades):
        rets = np.array([t.return_pct for t in all_trades])
        print(f"Win rate:     {(rets > 0).mean()*100:.1f}%")
        print(f"Avg/trade:    {rets.mean()*100:+.3f}%")
        print(f"Sharpe approx: {rets.mean()/rets.std()*np.sqrt(len(rets)/(len(monthly_kpis)/12)):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
