"""Backfill 15m OHLCV for Binance Futures USDS perp listings — paradigm 189.

For each listing event (sym, onboard_ts):
  - download window = onboard_date .. onboard_date+2 (covers +0h to +48h hold)
  - data.binance.vision/data/futures/um/daily/klines/{SYM}/15m/{SYM}-15m-{DATE}.zip
  - persist to ohlcv_cache/{SYM}.joblib

Bandwidth estimate: 468 events × 3 days × ~5KB ≈ 7MB total. ETA 5-10 min.

Per paradigm-architect rules:
  - data.binance.vision archive (T+1 availability), not REST
  - sequential rate-limited (sleep 0.2s/file)
  - skip-if-exists for joblib resumability
"""
from __future__ import annotations
import io
import json
import logging
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger("p189_backfill")

DIR = Path(__file__).resolve().parent
LISTING_JSON = DIR.parent / "lifecycle_phase" / "listing_dates.json"
EVENTS_CSV = DIR / "listing_events.csv"
CACHE = DIR / "ohlcv_cache"
CACHE.mkdir(exist_ok=True)

BASE = "https://data.binance.vision/data/futures/um/daily/klines"
TIMEFRAME = "15m"

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "n_trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]

WINDOW_START = "2023-01-01"
WINDOW_END = "2026-05-20"  # accommodate 48h hold for events through 2026-05-22


def build_events_csv() -> pd.DataFrame:
    """Build listing_events.csv from listing_dates.json."""
    with open(LISTING_JSON) as f:
        listings = json.load(f)
    rows = []
    for sym, meta in listings.items():
        if meta.get("contract_type") != "PERPETUAL":
            continue
        od = meta["onboard_date"]
        if od < WINDOW_START or od > WINDOW_END:
            continue
        rows.append({
            "symbol": sym,
            "onboard_date": od,
            "onboard_ts_ms": meta.get("onboard_ts_ms", 0),
        })
    df = pd.DataFrame(rows).sort_values("onboard_date").reset_index(drop=True)
    df.to_csv(EVENTS_CSV, index=False)
    log.info("Built listing_events.csv: %d events (window %s ~ %s)",
             len(df), WINDOW_START, WINDOW_END)
    return df


def fetch_day(sym: str, date: datetime) -> pd.DataFrame | None:
    ds = date.strftime("%Y-%m-%d")
    url = f"{BASE}/{sym}/{TIMEFRAME}/{sym}-{TIMEFRAME}-{ds}.zip"
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
                head = f.read(20)
                f_reset = io.BytesIO(head + f.read())
                try:
                    first_val = head.split(b",")[0]
                    has_header = not first_val.isdigit()
                except Exception:
                    has_header = False
                f_reset.seek(0)
                df = pd.read_csv(
                    f_reset,
                    header=0 if has_header else None,
                    names=None if has_header else KLINE_COLS,
                )
        ot = df["open_time"]
        if pd.api.types.is_numeric_dtype(ot):
            if ot.iloc[0] > 1e14:
                df["ts"] = pd.to_datetime(ot, unit="us", utc=True)
            else:
                df["ts"] = pd.to_datetime(ot, unit="ms", utc=True)
        else:
            df["ts"] = pd.to_datetime(ot, utc=True)
        df = df[["ts", "open", "high", "low", "close", "volume"]].copy()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    except Exception as e:
        log.warning("parse fail %s %s: %s", sym, ds, e)
        return None


def backfill_sym(sym: str, onboard_date: str) -> int:
    """Fetch +0d, +1d, +2d (3 days) for symbol. Skip if joblib exists."""
    out_path = CACHE / f"{sym}.joblib"
    if out_path.exists():
        return 0  # skip resumable
    start = datetime.strptime(onboard_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    frames = []
    for offset in range(3):  # 0, 1, 2 -> 3 days (covers 48h hold)
        d = start + timedelta(days=offset)
        df = fetch_day(sym, d)
        time.sleep(0.2)
        if df is not None and len(df) > 0:
            frames.append(df)
    if not frames:
        return -1
    full = pd.concat(frames, ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    joblib.dump(full, out_path)
    return len(full)


def main() -> int:
    if EVENTS_CSV.exists():
        events = pd.read_csv(EVENTS_CSV)
        log.info("Loaded existing listing_events.csv: %d events", len(events))
    else:
        events = build_events_csv()
    n_done = 0
    n_fail = 0
    n_skip = 0
    t0 = time.time()
    for i, row in events.iterrows():
        sym = row["symbol"]
        od = row["onboard_date"]
        out_path = CACHE / f"{sym}.joblib"
        if out_path.exists():
            n_skip += 1
            continue
        n = backfill_sym(sym, od)
        if n < 0:
            n_fail += 1
            log.warning("[%d/%d] FAIL %s onboard=%s", i + 1, len(events), sym, od)
        else:
            n_done += 1
            if n_done % 25 == 0:
                elapsed = time.time() - t0
                rate = n_done / max(elapsed, 1)
                eta = (len(events) - i - 1) / max(rate, 0.01)
                log.info(
                    "[%d/%d] %s done=%d skip=%d fail=%d elapsed=%.0fs ETA=%.0fs",
                    i + 1, len(events), sym, n_done, n_skip, n_fail, elapsed, eta,
                )
    log.info(
        "DONE n_events=%d done=%d skip=%d fail=%d elapsed=%.0fs",
        len(events), n_done, n_skip, n_fail, time.time() - t0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
