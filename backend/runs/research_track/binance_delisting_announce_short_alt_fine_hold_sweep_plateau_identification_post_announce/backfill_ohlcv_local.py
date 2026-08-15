"""Backfill 1m OHLCV for delisted USDS-M perp symbols from data.binance.vision.

This rebuilds the paradigm-87 ohlcv cache locally (pandas 2.3 compatible).
The original Mint-built cache uses StringDtype that breaks on local pandas 2.3.
Required window per event: announce_ts - 1d .. announce_ts + 48h + 1d
(short hold-sweep horizon 1h-48h post-announce, so 48h+buffer suffices vs delist+1d)
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
EVENTS_CSV = DIR.parent / "binance_delisting_announce_short_alt" / "delisting_events.csv"
CACHE = DIR / "ohlcv_cache_local"
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
    except Exception:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            csv_name = z.namelist()[0]
            with z.open(csv_name) as f:
                content = f.read()
                # Check first line is header
                first_line = content.split(b"\n")[0]
                try:
                    first_val = first_line.split(b",")[0]
                    has_header = not first_val.isdigit()
                except Exception:
                    has_header = False
                df = pd.read_csv(
                    io.BytesIO(content),
                    header=0 if has_header else None,
                    names=None if has_header else KLINE_COLS,
                )
                if "open_time" not in df.columns:
                    df.columns = KLINE_COLS[: len(df.columns)]
        ot = df["open_time"]
        if pd.api.types.is_numeric_dtype(ot):
            if ot.iloc[0] > 1e14:
                df["ts"] = pd.to_datetime(ot, unit="us", utc=True)
            else:
                df["ts"] = pd.to_datetime(ot, unit="ms", utc=True)
        else:
            df["ts"] = pd.to_datetime(ot, utc=True)
        df = df[["ts", "open", "high", "low", "close", "volume"]].astype(
            {"open": "float64", "high": "float64", "low": "float64", "close": "float64", "volume": "float64"}
        )
        # FORCE column dtype to object string (NOT StringDtype) to avoid cross-version pickle issues
        df.columns = list(df.columns)
        df = df.set_index("ts").sort_index()
        return df
    except Exception as e:
        log.warning("parse %s %s failed: %s", sym, ds, e)
        return None


def backfill_symbol(sym: str, ann_date: datetime, delist_date: datetime) -> int:
    """Window = ann_date - 1d .. min(ann_date + 3d, delist_date + 1d) per paradigm 190.
    Short hold-sweep 1h..48h post-announce needs only ~3d post-announce."""
    out_path = CACHE / f"{sym}.joblib"
    if out_path.exists():
        return 0  # already backfilled
    # Window: 1d pre-announce to 3d post-announce, OR to delist+1d if delist <3d
    start_d = (ann_date - timedelta(days=1)).date()
    end_target = ann_date + timedelta(days=3)
    end_alt = delist_date + timedelta(days=1)
    end_d = max(end_target, end_alt).date()  # take broader window to be safe

    cur = start_d
    days = []
    while cur <= end_d:
        days.append(cur)
        cur += timedelta(days=1)

    frames = []
    n_ok = 0
    for d in days:
        df = fetch_day(sym, datetime.combine(d, datetime.min.time()))
        if df is not None and not df.empty:
            frames.append(df)
            n_ok += 1
        time.sleep(0.03)  # rate limit
    if not frames:
        log.warning("no frames for %s", sym)
        return 0
    full = pd.concat(frames).sort_index()
    full = full[~full.index.duplicated(keep="first")]
    joblib.dump(full, out_path)
    log.info("backfill %s: %d days ok, %d bars saved", sym, n_ok, len(full))
    return n_ok


def main():
    events = []
    with open(EVENTS_CSV) as f:
        for r in csv.DictReader(f):
            ann = pd.Timestamp(r["announce_ts"]).to_pydatetime()
            de = pd.Timestamp(r["delist_ts"]).to_pydatetime()
            events.append((r["symbol"], ann, de))
    log.info("backfilling %d events", len(events))
    total_ok = 0
    for i, (sym, ann, de) in enumerate(events, 1):
        n = backfill_symbol(sym, ann, de)
        total_ok += n
        if i % 5 == 0:
            log.info("[%d/%d] cumulative days=%d", i, len(events), total_ok)
    log.info("DONE: %d events processed, %d total day-files", len(events), total_ok)


if __name__ == "__main__":
    main()
