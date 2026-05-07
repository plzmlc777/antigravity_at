#!/usr/bin/env python3
"""CLI: Run the Pattern Scanner against a symbol's 1m OHLCV from the project DB.

Usage:
  python -m scripts.scan_patterns --symbol 005930 --days 365
  python -m scripts.scan_patterns --symbol 005930 --days 365 --no-cache
  python -m scripts.scan_patterns --symbol 005930 --days 365 --tf 5m,1h,1d

Outputs a parquet file under backend/runs/pattern_scanner/ and prints stats.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Make backend/ importable when invoked as `python -m scripts.scan_patterns`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.pattern_scanner import (  # noqa: E402
    PatternScanner,
    SUPPORTED_TIMEFRAMES,
    SignalTensorCache,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("scan_patterns")


def load_1m_ohlcv(symbol: str, days: int) -> pd.DataFrame:
    """Fetch 1m OHLCV from the project's PostgreSQL DB.

    Returns DataFrame with DatetimeIndex (timestamp) and OHLCV columns.
    """
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
            raise RuntimeError(
                f"No 1m OHLCV found for {symbol} in last {days} days"
            )
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        return df
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Run Pattern Scanner against DB OHLCV")
    p.add_argument("--symbol", required=True, help="e.g. 005930")
    p.add_argument("--days", type=int, default=365, help="lookback days (default: 365)")
    p.add_argument(
        "--tf",
        type=str,
        default=",".join(SUPPORTED_TIMEFRAMES),
        help=f"comma-separated timeframes (default: {','.join(SUPPORTED_TIMEFRAMES)})",
    )
    p.add_argument("--no-cache", action="store_true", help="bypass disk cache")
    p.add_argument(
        "--output-dir",
        type=str,
        default=str(ROOT / "runs" / "pattern_scanner"),
        help="root directory for cache + output (default: backend/runs/pattern_scanner)",
    )
    args = p.parse_args()

    timeframes = [t.strip() for t in args.tf.split(",") if t.strip()]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache = SignalTensorCache(root=output_dir / "cache")

    log.info("Loading 1m OHLCV for %s (last %d days)...", args.symbol, args.days)
    df = load_1m_ohlcv(args.symbol, args.days)
    log.info("  %d 1m bars from %s to %s", len(df), df.index[0], df.index[-1])

    key = cache.make_key(symbol=args.symbol, start=df.index[0], end=df.index[-1])
    if not args.no_cache and cache.has(key):
        log.info("Cache hit: %s", cache.path(key))
        tensor = cache.get(key)
        if tensor is None:
            log.warning("Cache file present but failed to load — rescanning")
        else:
            print(f"Cached signals: {len(tensor)}")
            print(tensor.head(20).to_string())
            return 0

    scanner = PatternScanner(timeframes=timeframes)
    tensor, stats = scanner.scan_with_stats(df, symbol=args.symbol)
    log.info("\n%s", stats.summary())

    if not args.no_cache:
        cache.put(key, tensor)
        log.info("Cached → %s", cache.path(key))

    import joblib
    out_path = output_dir / f"{args.symbol}__{args.days}d__signals.joblib"
    joblib.dump(tensor, out_path, compress=3)
    log.info("Snapshot → %s", out_path)

    # quick top-line summary
    if len(tensor):
        print()
        print("Signals by pattern (top 15):")
        by_pat = tensor.groupby("pattern_name").size().sort_values(ascending=False)
        print(by_pat.head(15).to_string())
        print()
        print("Signals by (timeframe, direction):")
        print(tensor.groupby(["timeframe", "direction"]).size().to_string())
    else:
        print("No signals emitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
