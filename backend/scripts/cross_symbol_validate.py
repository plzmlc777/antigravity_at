#!/usr/bin/env python3
"""Final ablation: cross-symbol fitness + pre-screening + adaptive backtest.

Tests two ideas in sequence:
  A. CROSS-SYMBOL FITNESS POOLING — train fitness on ALL symbols' first half,
     apply to each symbol's second half. Should generalize better than
     single-symbol fitness.
  B. PRE-SCREENING — compute trend-strength of each symbol on the LATEST 60d.
     If trend > threshold (strong-bull), use buy-hold; else use pattern strategy.
     The selector ITSELF is data-driven, not hand-picked.

Compares:
  - Per-symbol single fitness (baseline, what we had)
  - Per-symbol cross-fitness only
  - Per-symbol cross-fitness + pre-screen
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
    AdaptiveConfig,
    DefensiveConfig,
    DefensiveTimingBacktester,
    RegimeAdaptiveBacktester,
)
from app.pattern_fitness import CrossSymbolFitnessLearner, FitnessLearner  # noqa: E402
from app.pattern_scanner import PatternScanner  # noqa: E402
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
        if len(rows) < 100:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def get_signals(symbol: str, days: int, df_1m: pd.DataFrame) -> pd.DataFrame:
    sig_path = ROOT / "runs" / "pattern_scanner" / f"{symbol}__{days}d__signals.joblib"
    if sig_path.exists():
        return joblib.load(sig_path)
    print(f"  [scanning {symbol}]")
    tensor = PatternScanner().scan(df_1m, symbol=symbol)
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(tensor, sig_path, compress=3)
    return tensor


def trend_strength(df_1m: pd.DataFrame, lookback_days: int = 60) -> float:
    """Compute |drift|/vol on the LATEST lookback_days. Used for pre-screening."""
    daily = df_1m["close"].resample("1D").last().dropna()
    if len(daily) < 5:
        return 0.0
    tail = daily.tail(lookback_days)
    rets = tail.pct_change().dropna()
    if len(rets) < 2 or rets.std() == 0:
        return 0.0
    drift = (np.log(tail.iloc[-1]) - np.log(tail.iloc[0])) / max(len(tail) / 252.0, 0.01)
    vol = rets.std() * np.sqrt(252)
    return float(abs(drift) / max(vol, 0.001))


def evaluate_oos(
    symbol: str, df_1m: pd.DataFrame, signals: pd.DataFrame,
    fitness, initial_capital: float, screen_skip: bool = False,
):
    """OOS test: train fitness already supplied; backtest on second half.
    If screen_skip=True, return buy-hold as the "strategy" (skip pattern bot)."""
    midpoint = df_1m.index[len(df_1m) // 2]
    df_test = df_1m.loc[midpoint:]
    if len(df_test) < 100:
        return None
    sig_test = signals[pd.to_datetime(signals["timestamp"]) > midpoint]

    ohlcv_test = {tf: resample_ohlcv(df_test, tf) for tf in SUPPORTED_TIMEFRAMES}
    regime_test = {}
    for tf in SUPPORTED_TIMEFRAMES:
        cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
        regime_test[tf] = cls.classify(ohlcv_test[tf])

    bh = (df_test.iloc[-1]["close"] - df_test.iloc[0]["open"]) / df_test.iloc[0]["open"]

    if screen_skip:
        return {"return_pct": float(bh), "screened": True, "n_trades": 0}

    cfg = AdaptiveConfig(
        pressure_window_min=60 * 24, exit_threshold=3, enter_threshold=0,
        min_n_in_cell=20, use_negative_edge_cells=True,
    )
    bt = RegimeAdaptiveBacktester(fitness=fitness, initial_capital=initial_capital, config=cfg)
    r = bt.run(symbol=symbol, ohlcv_1m=df_test, signals_df=sig_test, regime_by_tf=regime_test)
    return {"return_pct": float(r.total_return_pct), "screened": False, "n_trades": int(r.n_trades),
            "sharpe": float(r.sharpe_ratio), "mdd": float(r.max_drawdown_pct), "wr": float(r.win_rate)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--initial-capital", type=float, default=3_000_000)
    p.add_argument("--trend-screen-threshold", type=float, default=1.5,
                   help="if trend strength > this, skip pattern bot (use buy-hold)")
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {symbols}")
    print(f"Loading data for all symbols...")

    data = {}
    for sym in symbols:
        df_1m = load_1m(sym, args.days)
        if len(df_1m) == 0:
            continue
        sigs = get_signals(sym, args.days, df_1m)
        data[sym] = (df_1m, sigs)

    # Build TRAIN data per symbol (first half)
    print("Building train-half ohlcv + regimes per symbol...")
    train_signals_by_sym = {}
    train_ohlcv_by_sym_tf = {}
    train_regime_by_sym_tf = {}
    for sym, (df_1m, sigs) in data.items():
        midpoint = df_1m.index[len(df_1m) // 2]
        df_train = df_1m.loc[:midpoint]
        sig_train = sigs[pd.to_datetime(sigs["timestamp"]) <= midpoint]
        train_signals_by_sym[sym] = sig_train
        train_ohlcv_by_sym_tf[sym] = {tf: resample_ohlcv(df_train, tf) for tf in SUPPORTED_TIMEFRAMES}
        train_regime_by_sym_tf[sym] = {}
        for tf in SUPPORTED_TIMEFRAMES:
            cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
            train_regime_by_sym_tf[sym][tf] = cls.classify(train_ohlcv_by_sym_tf[sym][tf])

    # 1) Single-symbol fitness for baseline
    print("Building per-symbol baseline fitness...")
    single_fits = {}
    for sym in data:
        learner = FitnessLearner(min_samples=15, fdr_alpha=0.05)
        single_fits[sym] = learner.learn(
            symbol=sym, signals_df=train_signals_by_sym[sym],
            ohlcv_by_tf=train_ohlcv_by_sym_tf[sym],
            regime_by_tf=train_regime_by_sym_tf[sym],
        )

    # 2) Cross-symbol fitness
    print("Building cross-symbol fitness (pooled)...")
    cross_learner = CrossSymbolFitnessLearner(min_samples=30, fdr_alpha=0.05)
    cross_fit = cross_learner.learn(
        signals_by_symbol=train_signals_by_sym,
        ohlcv_by_symbol_tf=train_ohlcv_by_sym_tf,
        regime_by_symbol_tf=train_regime_by_sym_tf,
    )
    print(f"  cross-symbol cells: total={cross_fit.meta.n_cells_total}, "
          f"min_samples={cross_fit.meta.n_cells_with_min_samples}, "
          f"FDR-active={cross_fit.meta.n_cells_active}")

    # 3) Pre-screening: compute trend strength on TRAIN half (look-ahead safe!)
    print("Computing trend strength per symbol (train half only)...")
    screen_decisions = {}
    for sym, (df_1m, _) in data.items():
        midpoint = df_1m.index[len(df_1m) // 2]
        df_train = df_1m.loc[:midpoint]
        ts = trend_strength(df_train, lookback_days=60)
        screen_skip = ts > args.trend_screen_threshold
        screen_decisions[sym] = (ts, screen_skip)
        print(f"  {sym}: trend_strength={ts:.2f} → {'SKIP (use BH)' if screen_skip else 'apply pattern bot'}")

    # 4) OOS test all variants
    print()
    print(f"{'Symbol':8s} {'BH_oos%':>9s} {'Single F':>10s} {'Cross F':>9s} {'Cross+Scr':>10s}")
    print("-" * 75)

    summary = {"single": [], "cross": [], "screened": []}
    bh_oos_list = []

    for sym, (df_1m, sigs) in data.items():
        ts_strength, screen_skip = screen_decisions[sym]
        midpoint = df_1m.index[len(df_1m) // 2]
        df_test = df_1m.loc[midpoint:]
        bh_oos = (df_test.iloc[-1]["close"] - df_test.iloc[0]["open"]) / df_test.iloc[0]["open"]
        bh_oos_list.append(bh_oos)

        r_single = evaluate_oos(sym, df_1m, sigs, single_fits[sym], args.initial_capital, screen_skip=False)
        r_cross = evaluate_oos(sym, df_1m, sigs, cross_fit, args.initial_capital, screen_skip=False)
        r_screened = evaluate_oos(sym, df_1m, sigs, cross_fit, args.initial_capital, screen_skip=screen_skip)

        line = f"{sym:8s} {bh_oos*100:>+8.2f}% {r_single['return_pct']*100:>+9.2f}% {r_cross['return_pct']*100:>+8.2f}% {r_screened['return_pct']*100:>+9.2f}%"
        if r_screened["screened"]:
            line += "  [SCR]"
        print(line)

        summary["single"].append(r_single["return_pct"])
        summary["cross"].append(r_cross["return_pct"])
        summary["screened"].append(r_screened["return_pct"])

    print("-" * 75)
    bh_avg = float(np.mean(bh_oos_list))
    print(f"{'AVG':8s} {bh_avg*100:>+8.2f}% "
          f"{np.mean(summary['single'])*100:>+9.2f}% "
          f"{np.mean(summary['cross'])*100:>+8.2f}% "
          f"{np.mean(summary['screened'])*100:>+9.2f}%")
    print()
    print(f"Alpha vs BH (avg pts):")
    print(f"  Single fitness:        {(np.mean(summary['single']) - bh_avg)*100:+.2f}")
    print(f"  Cross fitness:         {(np.mean(summary['cross']) - bh_avg)*100:+.2f}")
    print(f"  Cross + pre-screen:    {(np.mean(summary['screened']) - bh_avg)*100:+.2f}")
    print()
    n_beat_bh = lambda arr: sum(r > b for r, b in zip(arr, bh_oos_list))
    print(f"Symbols beating BH OOS:")
    print(f"  Single fitness:        {n_beat_bh(summary['single'])}/{len(symbols)}")
    print(f"  Cross fitness:         {n_beat_bh(summary['cross'])}/{len(symbols)}")
    print(f"  Cross + pre-screen:    {n_beat_bh(summary['screened'])}/{len(symbols)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
