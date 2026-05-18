"""Backfill 1m OHLCV for delisted USDS-M perp symbols from data.binance.vision.

For each event (announce_ts, delist_ts, symbol):
  - download window = announce_date − 1 day .. delist_date + 1 day  (inclusive)
  - data.binance.vision/data/futures/um/daily/klines/{SYM}/1m/{SYM}-1m-{DATE}.zip
  - parse to DataFrame, persist to ohlcv_cache/{SYM}.parquet (full per-symbol concat)
"""
from __future__ import annotations
import csv
import io
import logging
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

DIR = Path(__file__).resolve().parent
CSV = DIR / "delisting_events.csv"
CACHE = DIR / "ohlcv_cache"
CACHE.mkdir(exist_ok=True)

BASE = "https://data.binance.vision/data/futures/um/daily/klines"

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "n_trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]


def fetch_day(sym: str, date: datetime) -> pd.DataFrame | None:
    ds = date.strftime("%Y-%m-%d")
    url = f"{BASE}/{sym}/1m/{sym}-1m-{ds}.zip"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
    except Exception as e:
        # 404 = no data for that day (delisted already, or before listing)
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                head = f.read(20)
                f_reset = io.BytesIO(head + f.read())
                # Check if first line is header (col names) or numeric (open_time)
                try:
                    first_val = head.split(b",")[0]
                    has_header = not first_val.isdigit()
                except Exception:
                    has_header = False
                f_reset.seek(0)
                df = pd.read_csv(f_reset, header=0 if has_header else None,
                                 names=None if has_header else KLINE_COLS)
                # Re-pick column subset
                if "open_time" not in df.columns:
                    # rename by position
                    df.columns = KLINE_COLS[:len(df.columns)]
                # Some recent binance CSVs use 'open_time' as header already
        # Normalize open_time -> datetime UTC
        # Binance kline open_time is ms (int)
        ot = df["open_time"]
        if pd.api.types.is_numeric_dtype(ot):
            # if values > 1e14 => microseconds, else ms
            if ot.iloc[0] > 1e14:
                df["ts"] = pd.to_datetime(ot, unit="us", utc=True)
            else:
                df["ts"] = pd.to_datetime(ot, unit="ms", utc=True)
        else:
            df["ts"] = pd.to_datetime(ot, utc=True)
        df = df[["ts", "open", "high", "low", "close", "volume"]].astype(
            {"open": "float64", "high": "float64", "low": "float64", "close": "float64", "volume": "float64"}
        )
        df = df.set_index("ts").sort_index()
        return df
    except Exception as e:
        log.warning("parse %s %s failed: %s", sym, ds, e)
        return None


def backfill_symbol(sym: str, start_d: datetime, end_d: datetime) -> pd.DataFrame:
    """Inclusive day range start_d .. end_d (UTC dates), return concatenated 1m df."""
    out_path = CACHE / f"{sym}.joblib"
    # Resume if exists & covers
    if out_path.exists():
        existing = joblib.load(out_path)
        if not existing.empty:
            cov_start = existing.index.min().normalize()
            cov_end = existing.index.max().normalize()
            need = []
            cur = start_d
            while cur <= end_d:
                if cur < cov_start or cur > cov_end:
                    need.append(cur)
                cur += timedelta(days=1)
            if not need:
                return existing
            log.info("  %s: extending (existing %s..%s, need %d new days)",
                     sym, cov_start.date(), cov_end.date(), len(need))
            dfs = [existing]
            for d in need:
                df = fetch_day(sym, d)
                if df is not None:
                    dfs.append(df)
                time.sleep(0.04)
            out = pd.concat(dfs).sort_index()
            out = out[~out.index.duplicated(keep="first")]
            joblib.dump(out, out_path)
            return out

    # Fresh download
    dfs = []
    cur = start_d
    fail = 0
    while cur <= end_d:
        df = fetch_day(sym, cur)
        if df is not None:
            dfs.append(df)
        else:
            fail += 1
        cur += timedelta(days=1)
        time.sleep(0.04)
    if not dfs:
        log.warning("  %s: NO data fetched (all %d days 404)", sym, fail)
        return pd.DataFrame()
    out = pd.concat(dfs).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    joblib.dump(out, out_path)
    return out


def main():
    log.info("loading %s", CSV)
    events_by_sym: dict[str, list[tuple[datetime, datetime]]] = {}
    with open(CSV) as f:
        for row in csv.DictReader(f):
            ann = datetime.fromisoformat(row["announce_ts"]).astimezone(timezone.utc)
            de = datetime.fromisoformat(row["delist_ts"]).astimezone(timezone.utc)
            events_by_sym.setdefault(row["symbol"], []).append((ann, de))
    log.info("symbols to backfill: %d", len(events_by_sym))

    total = len(events_by_sym)
    failed = []
    for i, (sym, rows) in enumerate(sorted(events_by_sym.items()), 1):
        # Span = min(announce)-1d .. max(delist)+1d   (per-sym usually only 1 event but cover all)
        min_a = min(r[0] for r in rows)
        max_d = max(r[1] for r in rows)
        start_d = (min_a - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_d = (max_d + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        n_days = (end_d - start_d).days + 1
        log.info("[%d/%d] %s: %s..%s (%d days)", i, total, sym, start_d.date(), end_d.date(), n_days)
        try:
            df = backfill_symbol(sym, start_d, end_d)
            if df.empty:
                failed.append(sym)
                log.warning("  -> EMPTY")
            else:
                log.info("  -> %d rows (%s..%s)", len(df), df.index.min(), df.index.max())
        except Exception as e:
            log.error("  -> ERROR: %s", e)
            failed.append(sym)
    log.info("done. %d/%d ok, %d failed", total - len(failed), total, len(failed))
    if failed:
        log.info("failed syms: %s", failed)


if __name__ == "__main__":
    main()
