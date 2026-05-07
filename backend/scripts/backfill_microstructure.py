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
        if out_path.exists():
            try:
                existing = joblib.load(out_path)
                log.info("[%s] existing file: %d rows %s~%s — skipping",
                         sym, len(existing), existing.index[0], existing.index[-1])
                continue
            except Exception:
                log.info("[%s] existing file unreadable, re-downloading", sym)

        log.info("[%s] downloading %d days...", sym, args.days)
        df = download_metrics_range(sym, start_dt, end_dt, cache_dir=cache_dir, parallel=args.parallel)
        if df.empty:
            log.warning("[%s] EMPTY result", sym)
            continue
        joblib.dump(df, out_path, compress=3)
        log.info("[%s] saved %d rows (%s ~ %s) → %s",
                 sym, len(df), df.index[0], df.index[-1], out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
