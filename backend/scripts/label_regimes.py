#!/usr/bin/env python3
"""CLI: Label market regimes for a symbol's 1m OHLCV.

Usage:
  python -m scripts.label_regimes --symbol 005930 --days 365
  python -m scripts.label_regimes --symbol 005930 --days 365 --tf 1d

Outputs:
  - backend/runs/regime/{symbol}__{days}d__{tf}__regimes.joblib  (full regime DF)
  - prints distribution of cells, top-20 most common cells, sample timeline
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
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.pattern_scanner.types import SUPPORTED_TIMEFRAMES  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("label_regimes")


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
    p.add_argument(
        "--tf",
        type=str,
        default="1d",
        help=f"timeframe to label at (one of {','.join(SUPPORTED_TIMEFRAMES)})",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT / "runs" / "regime"),
    )
    args = p.parse_args()

    if args.tf not in SUPPORTED_TIMEFRAMES:
        log.error("Unsupported tf: %s", args.tf)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading 1m OHLCV for %s (last %dd)...", args.symbol, args.days)
    df_1m = load_1m(args.symbol, args.days)
    log.info("  %d 1m bars from %s to %s", len(df_1m), df_1m.index[0], df_1m.index[-1])

    if args.tf == "1m":
        df_at_tf = df_1m
    else:
        df_at_tf = resample_ohlcv(df_1m, args.tf)
        log.info("  Resampled to %s: %d bars", args.tf, len(df_at_tf))

    if args.tf in ("4h", "1d"):
        classifier = RegimeClassifier.for_daily()
        log.info("Using daily-tuned classifier preset")
    else:
        classifier = RegimeClassifier.for_intraday()
        log.info("Using intraday-tuned classifier preset")
    rdf = classifier.classify(df_at_tf)

    out_path = output_dir / f"{args.symbol}__{args.days}d__{args.tf}__regimes.joblib"
    joblib.dump(rdf, out_path, compress=3)
    log.info("Saved → %s", out_path)

    # diagnostics
    valid = rdf[~rdf["is_warmup"]]
    print()
    print(f"Regime classification — {args.symbol} @ {args.tf}")
    print(f"  Total bars: {len(rdf)}, post-warmup: {len(valid)}")
    print(f"  Warmup bars dropped from analysis: {int(rdf['is_warmup'].sum())}")
    print()
    print("Per-dimension distribution (post-warmup):")
    for dim in ("trend", "volatility", "liquidity", "momentum"):
        pct = valid[dim].value_counts(normalize=True).sort_index()
        print(f"  {dim:10s}: " + ", ".join(f"{k}={v:.0%}" for k, v in pct.items()))
    print()
    print("Top 20 most common cells:")
    cell_counts = valid["cell_id"].value_counts().head(20)
    for cell, n in cell_counts.items():
        print(f"  {cell}: {n} ({n/len(valid):.1%})")
    print()
    print("Cells active vs total possible (81):")
    print(f"  active = {valid['cell_id'].nunique()}/81 ({valid['cell_id'].nunique()/81:.0%})")

    print()
    print("Sample timeline (10 evenly-spaced post-warmup bars):")
    sample_idx = valid.index[
        [int(x) for x in pd.Series(range(len(valid))).sample(min(10, len(valid)),
                                                              random_state=0).sort_values()]
    ]
    print(valid.loc[sample_idx, ["trend_score", "volatility_score", "liquidity_score",
                                 "momentum_score", "cell_id"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
