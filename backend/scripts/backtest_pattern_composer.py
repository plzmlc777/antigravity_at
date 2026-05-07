#!/usr/bin/env python3
"""CLI: Backtest the DynamicPatternComposer on a symbol.

Reads:
  - Trained Fitness Tensor (from learn_fitness.py)
  - Signal Tensor (from scan_patterns.py)
  - Re-fetches OHLCV + builds regime DFs

Usage:
    python -m scripts.backtest_pattern_composer --symbol 005930 --days 365
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.pattern_composer import (  # noqa: E402
    Backtester,
    ComposerConfig,
    DynamicPatternComposer,
    EventBacktestConfig,
    EventDrivenBacktester,
)
from app.pattern_fitness import FitnessLearner  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.pattern_scanner.types import SUPPORTED_TIMEFRAMES  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("backtest_pattern_composer")


def load_1m(symbol: str, days: int) -> pd.DataFrame:
    db = SessionLocal()
    try:
        end = datetime.now().replace(second=0, microsecond=0)
        start = end - timedelta(days=days)
        sql = text(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = :sym AND time_frame = '1m'
              AND timestamp >= :start
            ORDER BY timestamp ASC
            """
        )
        rows = db.execute(sql, {"sym": symbol, "start": start}).fetchall()
        if not rows:
            raise RuntimeError(f"No 1m OHLCV for {symbol}")
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--initial-capital", type=float, default=3_000_000)
    p.add_argument("--eval-freq-min", type=int, default=5)
    p.add_argument("--entry-threshold", type=float, default=0.005)
    p.add_argument("--exit-threshold", type=float, default=0.002)
    p.add_argument("--sl-pct", type=float, default=0.015)
    p.add_argument("--tp-pct", type=float, default=0.030)
    p.add_argument("--time-stop-bars", type=int, default=60)
    p.add_argument("--cooldown-bars", type=int, default=5)
    p.add_argument(
        "--signals",
        default=None,
        help="path to signals.joblib (default: backend/runs/pattern_scanner/{sym}__{days}d__signals.joblib)",
    )
    p.add_argument(
        "--fitness",
        default=None,
        help="path to fitness.joblib (default: backend/runs/pattern_fitness/{sym}__{days}d__fitness.joblib)",
    )
    p.add_argument(
        "--output-dir",
        default=str(ROOT / "runs" / "pattern_composer"),
    )
    p.add_argument(
        "--mode",
        choices=("ensemble", "event"),
        default="event",
        help="event = trade-per-signal w/ TF-bar horizon (recommended); "
             "ensemble = continuous composer (legacy v1)",
    )
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sig_path = (
        Path(args.signals) if args.signals
        else ROOT / "runs" / "pattern_scanner" / f"{args.symbol}__{args.days}d__signals.joblib"
    )
    fit_path = (
        Path(args.fitness) if args.fitness
        else ROOT / "runs" / "pattern_fitness" / f"{args.symbol}__{args.days}d__fitness.joblib"
    )
    if not sig_path.exists():
        log.error("Signals not found: %s", sig_path); return 2
    if not fit_path.exists():
        log.error("Fitness not found: %s", fit_path); return 2

    log.info("Loading signals: %s", sig_path)
    signals = joblib.load(sig_path)
    log.info("  %d signals", len(signals))

    log.info("Loading fitness: %s", fit_path)
    fitness = FitnessLearner.load(fit_path)
    log.info("  %d cells (%d active)", len(fitness), fitness.meta.n_cells_active)
    if fitness.meta.n_cells_active == 0:
        log.error("No active fitness cells — composer can't act. Re-train fitness first.")
        return 2

    log.info("Loading 1m OHLCV...")
    df_1m = load_1m(args.symbol, args.days)
    log.info("  %d 1m bars", len(df_1m))

    log.info("Building regime per TF...")
    regime_by_tf = {}
    for tf in SUPPORTED_TIMEFRAMES:
        df_tf = resample_ohlcv(df_1m, tf)
        if tf in ("4h", "1d"):
            cls = RegimeClassifier.for_daily()
        else:
            cls = RegimeClassifier.for_intraday()
        regime_by_tf[tf] = cls.classify(df_tf)

    if args.mode == "ensemble":
        cfg = ComposerConfig(
            entry_threshold=args.entry_threshold,
            exit_threshold=args.exit_threshold,
            sl_pct=args.sl_pct,
            tp_pct=args.tp_pct,
            time_stop_bars=args.time_stop_bars,
            cooldown_bars=args.cooldown_bars,
            long_only=True,
        )
        composer = DynamicPatternComposer(fitness=fitness, config=cfg)
        backtester = Backtester(composer=composer, initial_capital=args.initial_capital)
        log.info("Running ENSEMBLE backtest (eval every %d minutes)...", args.eval_freq_min)
        result = backtester.run(
            symbol=args.symbol,
            ohlcv_1m=df_1m,
            signals_df=signals,
            regime_by_tf=regime_by_tf,
            eval_freq_minutes=args.eval_freq_min,
        )
    else:  # event
        ohlcv_by_tf = {}
        for tf in SUPPORTED_TIMEFRAMES:
            ohlcv_by_tf[tf] = resample_ohlcv(df_1m, tf)
        ev_cfg = EventBacktestConfig(
            sl_pct=args.sl_pct,
            tp_pct=args.tp_pct,
            long_only=True,
        )
        ev_bt = EventDrivenBacktester(
            fitness=fitness, initial_capital=args.initial_capital, config=ev_cfg,
        )
        log.info("Running EVENT-DRIVEN backtest (TF-bar horizon)...")
        result = ev_bt.run(
            symbol=args.symbol,
            ohlcv_1m=df_1m,
            ohlcv_by_tf=ohlcv_by_tf,
            signals_df=signals,
            regime_by_tf=regime_by_tf,
        )

    out_path = output_dir / f"{args.symbol}__{args.days}d__backtest.joblib"
    joblib.dump(result, out_path, compress=3)
    log.info("Saved → %s", out_path)

    print()
    print(result.summary())

    # Top contributing patterns from winning trades
    if result.trades:
        wins = [t for t in result.trades if t.return_pct > 0]
        losses = [t for t in result.trades if t.return_pct <= 0]
        from collections import Counter
        win_pats = Counter()
        loss_pats = Counter()
        for t in wins:
            for p in t.contributing_patterns:
                win_pats[p] += 1
        for t in losses:
            for p in t.contributing_patterns:
                loss_pats[p] += 1
        print()
        print("Top patterns in WINNING trades:")
        for p, n in win_pats.most_common(10):
            print(f"  {p}: {n}")
        print()
        print("Top patterns in LOSING trades:")
        for p, n in loss_pats.most_common(10):
            print(f"  {p}: {n}")

    # Brief JSON metrics for downstream tooling
    metrics = {
        "symbol": result.symbol,
        "n_trades": result.n_trades,
        "win_rate": result.win_rate,
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "profit_factor": result.profit_factor,
        "avg_holding_bars": result.avg_holding_bars,
        "exit_reasons": result.exit_reason_counts,
    }
    with open(output_dir / f"{args.symbol}__{args.days}d__metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
