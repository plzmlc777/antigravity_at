#!/usr/bin/env python3
"""Multi-symbol validation of the defensive timing strategy.

For each symbol:
  1. Run scan_patterns (or load cached signals)
  2. Train fitness on full year
  3. Run defensive backtest
  4. Compare to buy-hold

Also: per-symbol OOS test (train first half, test second half).

Usage:
    python -m scripts.multi_symbol_validate --symbols 001210,086980,207940
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
from app.pattern_fitness import FitnessLearner  # noqa: E402
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


def get_or_scan_signals(symbol: str, days: int, df_1m: pd.DataFrame) -> pd.DataFrame:
    sig_path = ROOT / "runs" / "pattern_scanner" / f"{symbol}__{days}d__signals.joblib"
    if sig_path.exists():
        return joblib.load(sig_path)
    print(f"  [no cached signals — scanning {symbol}]")
    scanner = PatternScanner()
    tensor = scanner.scan(df_1m, symbol=symbol)
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(tensor, sig_path, compress=3)
    return tensor


def evaluate_defensive(
    symbol: str, df_1m: pd.DataFrame, signals: pd.DataFrame,
    initial_capital: float, oos_split: bool = False,
    use_adaptive: bool = False,
):
    """Run defensive backtest with config v4.0 (the winning variant on 001210),
    or v5 regime-adaptive."""
    if use_adaptive:
        cfg = AdaptiveConfig(
            pressure_window_min=60 * 24, exit_threshold=3, enter_threshold=0,
            min_n_in_cell=20, use_negative_edge_cells=True,
            hold_trends=("trending_up",), hold_momentums=("positive",),
        )
    else:
        cfg = DefensiveConfig(
            pressure_window_min=60 * 24,
            exit_threshold=3, enter_threshold=0,
            min_n_in_cell=20, use_negative_edge_cells=True,
        )

    if not oos_split:
        # full-year train + full-year backtest
        ohlcv_by_tf = {tf: resample_ohlcv(df_1m, tf) for tf in SUPPORTED_TIMEFRAMES}
        regime_by_tf = {}
        for tf in SUPPORTED_TIMEFRAMES:
            cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
            regime_by_tf[tf] = cls.classify(ohlcv_by_tf[tf])
        learner = FitnessLearner(min_samples=20, fdr_alpha=0.05)
        fitness = learner.learn(symbol=symbol, signals_df=signals,
                                ohlcv_by_tf=ohlcv_by_tf, regime_by_tf=regime_by_tf)
        if use_adaptive:
            bt = RegimeAdaptiveBacktester(fitness=fitness, initial_capital=initial_capital, config=cfg)
        else:
            bt = DefensiveTimingBacktester(fitness=fitness, initial_capital=initial_capital, config=cfg)
        return bt.run(symbol=symbol, ohlcv_1m=df_1m, signals_df=signals, regime_by_tf=regime_by_tf)
    else:
        # OOS: train first half, test second
        midpoint = df_1m.index[len(df_1m) // 2]
        df_train = df_1m.loc[:midpoint]
        df_test = df_1m.loc[midpoint:]
        sig_train = signals[pd.to_datetime(signals["timestamp"]) <= midpoint]
        sig_test = signals[pd.to_datetime(signals["timestamp"]) > midpoint]

        ohlcv_train = {tf: resample_ohlcv(df_train, tf) for tf in SUPPORTED_TIMEFRAMES}
        ohlcv_test = {tf: resample_ohlcv(df_test, tf) for tf in SUPPORTED_TIMEFRAMES}
        regime_train = {}
        regime_test = {}
        for tf in SUPPORTED_TIMEFRAMES:
            cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
            regime_train[tf] = cls.classify(ohlcv_train[tf])
            regime_test[tf] = cls.classify(ohlcv_test[tf])

        learner = FitnessLearner(min_samples=15, fdr_alpha=0.05)
        fitness = learner.learn(
            symbol=symbol, signals_df=sig_train,
            ohlcv_by_tf=ohlcv_train, regime_by_tf=regime_train,
        )
        if use_adaptive:
            bt = RegimeAdaptiveBacktester(fitness=fitness, initial_capital=initial_capital, config=cfg)
        else:
            bt = DefensiveTimingBacktester(fitness=fitness, initial_capital=initial_capital, config=cfg)
        return bt.run(symbol=symbol, ohlcv_1m=df_test, signals_df=sig_test, regime_by_tf=regime_test)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="comma-separated")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--initial-capital", type=float, default=3_000_000)
    p.add_argument("--oos", action="store_true", help="also run OOS split test")
    p.add_argument("--mode", choices=("defensive", "adaptive"), default="adaptive",
                   help="defensive = pure pattern timing; adaptive = hold during macro uptrend")
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {symbols}")
    print(f"{'Symbol':8s} {'Bars':>7s} {'BH%':>9s} {'IS Ret%':>9s} {'IS Sharpe':>10s} {'IS MDD%':>9s} {'IS WR':>6s}", end="")
    if args.oos:
        print(f" {'OOS Ret%':>9s} {'OOS BH%':>9s}")
    else:
        print()
    print("-" * (105 + (20 if args.oos else 0)))

    for sym in symbols:
        df_1m = load_1m(sym, args.days)
        if len(df_1m) == 0:
            print(f"{sym:8s} (no data)")
            continue
        signals = get_or_scan_signals(sym, args.days, df_1m)

        use_adaptive = (args.mode == "adaptive")
        # full-year
        r_is = evaluate_defensive(sym, df_1m, signals, args.initial_capital, oos_split=False, use_adaptive=use_adaptive)
        bh = (df_1m.iloc[-1]["close"] - df_1m.iloc[0]["open"]) / df_1m.iloc[0]["open"]

        line = (f"{sym:8s} {len(df_1m):>7d} {bh*100:>+8.2f}% "
                f"{r_is.total_return_pct*100:>+8.2f}% {r_is.sharpe_ratio:>10.2f} "
                f"{r_is.max_drawdown_pct*100:>8.2f}% {r_is.win_rate*100:>5.1f}%")

        if args.oos:
            r_oos = evaluate_defensive(sym, df_1m, signals, args.initial_capital, oos_split=True, use_adaptive=use_adaptive)
            mp = df_1m.index[len(df_1m) // 2]
            df_test = df_1m.loc[mp:]
            bh_oos = (df_test.iloc[-1]["close"] - df_test.iloc[0]["open"]) / df_test.iloc[0]["open"]
            line += f" {r_oos.total_return_pct*100:>+8.2f}% {bh_oos*100:>+8.2f}%"
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
