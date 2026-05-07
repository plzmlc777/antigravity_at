#!/usr/bin/env python3
"""CLI: Learn the Fitness tensor for a symbol from previously-saved
Signal Tensor (PatternScanner output) and per-TF regime DataFrames.

Pipeline:
  1. Load 1m OHLCV (re-fetch from DB for the same window)
  2. Resample to all SUPPORTED_TIMEFRAMES
  3. Load Signal Tensor (joblib snapshot from scan_patterns.py)
  4. Build regime DF for each TF using RegimeClassifier
  5. Run FitnessLearner → save FitnessTensor

Usage:
    python -m scripts.learn_fitness --symbol 005930 --days 365
"""
from __future__ import annotations

import argparse
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
from app.pattern_fitness import FitnessLearner  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.pattern_scanner.types import SUPPORTED_TIMEFRAMES  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("learn_fitness")


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
            raise RuntimeError(f"No 1m OHLCV for {symbol} in last {days}d")
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
    p.add_argument("--min-samples", type=int, default=30)
    p.add_argument("--fdr-alpha", type=float, default=0.05)
    p.add_argument(
        "--signals",
        type=str,
        default=None,
        help="path to signals .joblib (default: backend/runs/pattern_scanner/{symbol}__{days}d__signals.joblib)",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT / "runs" / "pattern_fitness"),
    )
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sig_path = (
        Path(args.signals)
        if args.signals
        else ROOT / "runs" / "pattern_scanner" / f"{args.symbol}__{args.days}d__signals.joblib"
    )
    if not sig_path.exists():
        log.error("Signals file not found: %s. Run scan_patterns first.", sig_path)
        return 2
    log.info("Loading signals: %s", sig_path)
    signals = joblib.load(sig_path)
    log.info("  %d signals", len(signals))

    log.info("Loading 1m OHLCV for %s (last %dd)...", args.symbol, args.days)
    df_1m = load_1m(args.symbol, args.days)
    log.info("  %d 1m bars from %s to %s", len(df_1m), df_1m.index[0], df_1m.index[-1])

    log.info("Resampling to all TFs + classifying regimes...")
    ohlcv_by_tf = {}
    regime_by_tf = {}
    for tf in SUPPORTED_TIMEFRAMES:
        ohlcv_by_tf[tf] = resample_ohlcv(df_1m, tf)
        if tf in ("4h", "1d"):
            classifier = RegimeClassifier.for_daily()
        else:
            classifier = RegimeClassifier.for_intraday()
        regime_by_tf[tf] = classifier.classify(ohlcv_by_tf[tf])
        log.info("  %s: %d bars, %d active cells",
                 tf, len(ohlcv_by_tf[tf]),
                 regime_by_tf[tf].loc[~regime_by_tf[tf]["is_warmup"], "cell_id"].nunique())

    log.info("Running FitnessLearner...")
    learner = FitnessLearner(min_samples=args.min_samples, fdr_alpha=args.fdr_alpha)
    tensor = learner.learn(
        symbol=args.symbol,
        signals_df=signals,
        ohlcv_by_tf=ohlcv_by_tf,
        regime_by_tf=regime_by_tf,
    )

    out_path = output_dir / f"{args.symbol}__{args.days}d__fitness.joblib"
    FitnessLearner.save(tensor, out_path)
    log.info("Saved → %s", out_path)

    print()
    print("=== Fitness Tensor — meta ===")
    print(f"  symbol                : {tensor.meta.symbol}")
    print(f"  train window          : {tensor.meta.train_window_start} → {tensor.meta.train_window_end}")
    print(f"  cells total           : {tensor.meta.n_cells_total}")
    print(f"  cells with min_samples: {tensor.meta.n_cells_with_min_samples}")
    print(f"  cells active (FDR)    : {tensor.meta.n_cells_active}")
    print(f"  min_samples / α       : {tensor.meta.min_samples} / {tensor.meta.fdr_alpha}")
    print()

    if tensor.meta.n_cells_active == 0:
        print("(no FDR-significant cells)")
        return 0

    print("Top 20 active cells by edge_mean (with sample size & win rate):")
    rows = sorted(
        (c for c in tensor.cells.values() if c.is_active),
        key=lambda c: c.edge_mean,
        reverse=True,
    )[:20]
    for c in rows:
        print(
            f"  {c.pattern:25s} | {c.timeframe:3s} | {c.cell_id:55s} | "
            f"{c.direction:7s} | n={c.n:5d} | "
            f"edge={c.edge_mean*100:+6.2f}% | wr={c.win_rate:.2f} | "
            f"CI=[{c.edge_ci_low*100:+5.2f}%, {c.edge_ci_high*100:+5.2f}%]"
        )

    print()
    print("Bottom 5 (most-negative edge — useful for short or contra-signals):")
    rows_b = sorted(
        (c for c in tensor.cells.values() if c.is_active),
        key=lambda c: c.edge_mean,
    )[:5]
    for c in rows_b:
        print(
            f"  {c.pattern:25s} | {c.timeframe:3s} | {c.cell_id:55s} | "
            f"{c.direction:7s} | n={c.n:5d} | "
            f"edge={c.edge_mean*100:+6.2f}% | wr={c.win_rate:.2f}"
        )

    print()
    print("Active cells per pattern (top 10 patterns):")
    counts: dict[str, int] = {}
    for c in tensor.cells.values():
        if c.is_active:
            counts[c.pattern] = counts.get(c.pattern, 0) + 1
    for pat, n in sorted(counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {pat:32s}: {n} active cells")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
