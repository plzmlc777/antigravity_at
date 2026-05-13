"""Download 1 year of Binance Futures 5-min metrics archive for symbols.

Wraps app.microstructure.archive_downloader.download_metrics_range.
Output: backend/runs/microstructure/{SYMBOL}_full_metrics.joblib
Cache: backend/runs/microstructure/cache/{SYMBOL}__YYYY-MM-DD.joblib

Usage:
  python3 -m scripts.backfill_microstructure --symbols LINKUSDT,DOGEUSDT,AVAXUSDT --days 365
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.microstructure.archive_downloader import download_metrics_range  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_microstructure")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="comma-separated USDT-perp symbols")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD (default: yesterday)")
    p.add_argument("--parallel", type=int, default=8)
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "microstructure"))
    p.add_argument("--refresh", action="store_true",
                   help="Incremental: read existing joblib, fetch only days after its last date, merge")
    args = p.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "cache"

    end_date = (datetime.utcnow() - timedelta(days=1)).date() if args.end_date is None \
        else datetime.strptime(args.end_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=args.days - 1)
    end_dt = datetime.combine(end_date, datetime.min.time())
    start_dt = datetime.combine(start_date, datetime.min.time())

    log.info("Range: %s ~ %s (%d days)", start_date, end_date, args.days)

    for sym in symbols:
        out_path = out_dir / f"{sym}_full_metrics.joblib"

        existing = None
        fetch_start = start_dt
        if out_path.exists():
            try:
                existing = joblib.load(out_path)
                last_existing = existing.index.max()
                log.info("[%s] existing: %d rows %s~%s",
                         sym, len(existing), existing.index[0], last_existing)
                if not args.refresh:
                    log.info("[%s] skip — use --refresh for incremental", sym)
                    continue
                # Re-fetch from last existing day forward (1-day overlap is fine,
                # archive_downloader caches per-day so overlap is free).
                fetch_start = datetime.combine(last_existing.date(), datetime.min.time())
                if fetch_start.date() >= end_dt.date():
                    log.info("[%s] up-to-date (last %s) — skip", sym, last_existing.date())
                    continue
                log.info("[%s] incremental from %s", sym, fetch_start.date())
            except Exception:
                log.info("[%s] existing file unreadable, re-downloading full range", sym)
                existing = None
                fetch_start = start_dt

        log.info("[%s] downloading %s ~ %s...", sym, fetch_start.date(), end_date)
        df = download_metrics_range(sym, fetch_start, end_dt, cache_dir=cache_dir, parallel=args.parallel)
        if df.empty:
            log.warning("[%s] EMPTY result", sym)
            continue

        if existing is not None and len(existing) > 0:
            df = pd.concat([existing, df]).sort_index()
            df = df[~df.index.duplicated(keep="last")]

        joblib.dump(df, out_path, compress=3)
        log.info("[%s] saved %d rows (%s ~ %s) → %s",
                 sym, len(df), df.index[0], df.index[-1], out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
