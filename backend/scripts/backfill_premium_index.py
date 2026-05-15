"""Download Binance Futures premiumIndex klines from data.binance.vision.

URL: https://data.binance.vision/data/futures/um/daily/premiumIndexKlines/{SYM}/{interval}/{SYM}-{interval}-YYYY-MM-DD.zip

For 1d: each daily zip has 1 row. For 5m/15m/etc: 288/96 rows per daily zip.
premium = (mark_price - index_price) / index_price (approximately)

Output:
  1d (default):  backend/runs/premium_index/{SYMBOL}_premium.joblib
  non-1d:        backend/runs/premium_index/{SYMBOL}_premium_{interval}.joblib

Usage:
  python -m scripts.backfill_premium_index --symbols BTCUSDT,ETHUSDT --days 800
  python -m scripts.backfill_premium_index --symbols BTCUSDT --interval 5m --days 730
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_premium_index")

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/premiumIndexKlines"
KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "count",
              "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def _url(sym: str, date, interval: str = "1d") -> str:
    return f"{ARCHIVE_BASE}/{sym}/{interval}/{sym}-{interval}-{date.isoformat()}.zip"


def _fetch(sym: str, date, session: requests.Session, retries: int = 2, interval: str = "1d"):
    url = _url(sym, date, interval=interval)
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                names = z.namelist()
                if not names: return None
                with z.open(names[0]) as fh:
                    df = pd.read_csv(fh, names=KLINE_COLS, header=0)
            return df
        except Exception as e:
            if attempt == retries:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True)
    p.add_argument("--days", type=int, default=800)
    p.add_argument("--end-date", default=None)
    p.add_argument("--parallel", type=int, default=16)
    p.add_argument("--interval", default="1d",
                   help="Kline interval: 1d/12h/4h/1h/30m/15m/5m/1m (default 1d)")
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "premium_index"))
    p.add_argument("--refresh", action="store_true",
                   help="Incremental: read existing joblib, fetch only days after its last date, merge")
    args = p.parse_args()

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    end_date = (datetime.utcnow() - timedelta(days=1)).date() if args.end_date is None \
        else datetime.strptime(args.end_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=args.days - 1)
    log.info("Range: %s ~ %s (%d days, refresh=%s)", start_date, end_date, args.days, args.refresh)

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    target_days = [start_date + timedelta(days=i) for i in range(args.days)]

    for sym in syms:
        suffix = "" if args.interval == "1d" else f"_{args.interval}"
        out_path = out_dir / f"{sym}_premium{suffix}.joblib"

        existing = None
        days_to_fetch = target_days
        if out_path.exists():
            if not args.refresh:
                log.info("[%s] skip — exists (use --refresh for incremental)", sym)
                continue
            try:
                existing = joblib.load(out_path)
                last_existing = existing.index.max().date()
                days_to_fetch = [d for d in target_days if d > last_existing]
                if not days_to_fetch:
                    log.info("[%s] up-to-date (last %s) — skip", sym, last_existing)
                    continue
                log.info("[%s] incremental: %d new days from %s",
                         sym, len(days_to_fetch), days_to_fetch[0])
            except Exception as e:
                log.warning("[%s] existing unreadable (%s) — full rebuild", sym, e)
                existing = None
                days_to_fetch = target_days

        t0 = time.time()
        frames = []
        session = requests.Session()
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futs = {ex.submit(_fetch, sym, d, session, 2, args.interval): d
                    for d in days_to_fetch}
            for f in as_completed(futs):
                df = f.result()
                if df is not None and not df.empty:
                    frames.append(df)
        if not frames:
            log.warning("[%s] no new data fetched", sym)
            continue
        out = pd.concat(frames).sort_values("open_time").reset_index(drop=True)
        out["timestamp"] = pd.to_datetime(out["open_time"].astype("int64"), unit="ms")
        out = out.set_index("timestamp")[["open", "high", "low", "close", "count"]].astype(float)

        if existing is not None and len(existing) > 0:
            out = pd.concat([existing, out]).sort_index()
            out = out[~out.index.duplicated(keep="last")]

        joblib.dump(out, out_path, compress=3)
        elapsed = time.time() - t0
        log.info("[%s] saved %d rows in %.1fs (range %s ~ %s) → %s",
                 sym, len(out), elapsed, out.index[0].date(), out.index[-1].date(), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
