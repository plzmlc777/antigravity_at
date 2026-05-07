"""Download 1m kline archives from data.binance.vision for Binance Futures USDT-perp,
parse, and INSERT into the ohlcv table (idempotent ON CONFLICT DO NOTHING).

URL pattern:
  https://data.binance.vision/data/futures/um/daily/klines/{SYMBOL}/1m/{SYMBOL}-1m-YYYY-MM-DD.zip

CSV columns:
  open_time, open, high, low, close, volume, close_time, quote_volume,
  count, taker_buy_volume, taker_buy_quote_volume, ignore

(open_time is in milliseconds UTC.)

Usage:
  python3 -m scripts.backfill_ohlcv_archive --symbols BNBUSDT,XRPUSDT --days 800 --parallel 16
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

import pandas as pd
import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal, engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_ohlcv_archive")

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/klines"
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def _archive_url(symbol: str, date) -> str:
    return f"{ARCHIVE_BASE}/{symbol}/1m/{symbol}-1m-{date.isoformat()}.zip"


def _parse_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            # Some zips include a header row, some don't. Try both.
            data = fh.read()
            head_text = data[:200].decode("utf-8", errors="replace").lower()
            has_header = "open_time" in head_text or "open" in head_text.split(",")[0]
            df = pd.read_csv(io.BytesIO(data),
                             names=KLINE_COLUMNS,
                             header=0 if has_header else None)
    if df.empty:
        return df
    return df


def _fetch_one(symbol: str, date, session: requests.Session, retries: int = 2):
    url = _archive_url(symbol, date)
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None  # not yet uploaded / weekend skip
            r.raise_for_status()
            return _parse_zip(r.content)
        except Exception as e:
            if attempt == retries:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def download_klines_range(symbol: str, start_date, end_date, parallel: int = 16) -> pd.DataFrame:
    days = (end_date - start_date).days + 1
    if days <= 0:
        return pd.DataFrame()
    target = [start_date + timedelta(days=i) for i in range(days)]
    log.info("[%s] downloading %d days", symbol, days)
    frames = []
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(_fetch_one, symbol, d, session): d for d in target}
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_values("open_time")
    return out


def insert_to_db(symbol: str, df: pd.DataFrame) -> int:
    """Bulk insert via COPY FROM into a temp table, then INSERT ... ON CONFLICT DO NOTHING.

    ~100x faster than row-by-row executemany on 1M rows.
    """
    if df.empty:
        return 0
    out = pd.DataFrame({
        "symbol": symbol,
        "time_frame": "1m",
        "timestamp": pd.to_datetime(df["open_time"].astype("int64"), unit="ms"),
        "open": df["open"].astype(float),
        "high": df["high"].astype(float),
        "low": df["low"].astype(float),
        "close": df["close"].astype(float),
        "volume": df["volume"].astype(float),
    })
    csv_buf = io.StringIO()
    out.to_csv(csv_buf, index=False, header=False)
    csv_buf.seek(0)

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute("""
                CREATE TEMP TABLE _tmp_ohlcv (
                    symbol VARCHAR(50),
                    time_frame VARCHAR(10),
                    timestamp TIMESTAMP,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume DOUBLE PRECISION
                ) ON COMMIT DROP
            """)
            cur.copy_expert(
                "COPY _tmp_ohlcv (symbol,time_frame,timestamp,open,high,low,close,volume) "
                "FROM STDIN WITH (FORMAT CSV)",
                csv_buf,
            )
            cur.execute("""
                INSERT INTO ohlcv (symbol, time_frame, timestamp, open, high, low, close, volume)
                SELECT symbol, time_frame, timestamp, open, high, low, close, volume
                FROM _tmp_ohlcv
                ON CONFLICT (symbol, time_frame, timestamp) DO NOTHING
            """)
        raw.commit()
    finally:
        raw.close()
    return len(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True)
    p.add_argument("--days", type=int, default=800)
    p.add_argument("--end-date", default=None)
    p.add_argument("--parallel", type=int, default=16)
    args = p.parse_args()

    end_date = (datetime.utcnow() - timedelta(days=1)).date() if args.end_date is None \
        else datetime.strptime(args.end_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=args.days - 1)
    log.info("Range: %s ~ %s (%d days)", start_date, end_date, args.days)

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    for sym in syms:
        # Check current row count first
        db = SessionLocal()
        try:
            n_before = db.execute(text("SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame='1m'"),
                                  {"s": sym}).scalar()
        finally:
            db.close()
        log.info("[%s] before: %s rows in DB", sym, f"{n_before:,}")
        if n_before > args.days * 1000:
            log.info("[%s] already has plenty of data, skipping download", sym)
            continue

        t0 = time.time()
        df = download_klines_range(sym, start_date, end_date, parallel=args.parallel)
        elapsed = time.time() - t0
        log.info("[%s] downloaded %s rows in %.1fs", sym, f"{len(df):,}", elapsed)

        if df.empty:
            log.warning("[%s] empty download result, skip insert", sym)
            continue

        t0 = time.time()
        n = insert_to_db(sym, df)
        elapsed = time.time() - t0
        log.info("[%s] insert %s rows in %.1fs", sym, f"{n:,}", elapsed)

        db = SessionLocal()
        try:
            n_after = db.execute(text("SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame='1m'"),
                                 {"s": sym}).scalar()
        finally:
            db.close()
        log.info("[%s] after: %s rows in DB (delta: +%s)", sym, f"{n_after:,}", f"{n_after - n_before:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
