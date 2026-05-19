"""Backfill cross-exchange OI for paradigm 104.

Binance: 5min archive (data.binance.vision) → resample to 1h
Bybit: V5 REST openInterest intervalTime=1h with cursor pagination

Output: joblib caches at backend/runs/ohlcv_cache/{venue}_oi/{SYM}_1h.joblib
  columns: ['ts', 'oi']  (oi = open_interest in coins)

Scope: deep-7 universe, 2024-01-01 .. 2026-05-19 (~870 days)
"""
from __future__ import annotations

import io
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p104_backfill")

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]

START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 5, 19, tzinfo=timezone.utc)

CACHE_BINANCE = ROOT / "runs" / "ohlcv_cache" / "binance_oi"
CACHE_BYBIT = ROOT / "runs" / "ohlcv_cache" / "bybit_oi"
DAILY_CACHE_BINANCE = ROOT / "runs" / "ohlcv_cache" / "binance_metrics_daily"

CACHE_BINANCE.mkdir(parents=True, exist_ok=True)
CACHE_BYBIT.mkdir(parents=True, exist_ok=True)
DAILY_CACHE_BINANCE.mkdir(parents=True, exist_ok=True)

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/metrics"


# --------------------- Binance archive (5m → 1h) ---------------------
def _archive_url(symbol: str, date: datetime) -> str:
    ds = date.strftime("%Y-%m-%d")
    return f"{ARCHIVE_BASE}/{symbol}/{symbol}-metrics-{ds}.zip"


def _parse_metrics_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            df = pd.read_csv(fh)
    if df.empty:
        return df
    df["create_time"] = pd.to_datetime(df["create_time"])
    df = df.rename(columns={"sum_open_interest": "open_interest"})
    df = df[["create_time", "open_interest"]]
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df = df.set_index("create_time").sort_index()
    return df


def _fetch_one_day(symbol: str, date: datetime, session: requests.Session) -> pd.DataFrame | None:
    """Fetch one day; cache locally as joblib."""
    cache_path = DAILY_CACHE_BINANCE / f"{symbol}__{date.strftime('%Y-%m-%d')}.joblib"
    if cache_path.exists():
        try:
            return joblib.load(cache_path)
        except Exception:
            pass

    url = _archive_url(symbol, date)
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                # save empty marker
                joblib.dump(pd.DataFrame(), cache_path, compress=3)
                return pd.DataFrame()
            r.raise_for_status()
            df = _parse_metrics_zip(r.content)
            joblib.dump(df, cache_path, compress=3)
            return df
        except Exception as e:
            if attempt == 2:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def backfill_binance_oi(symbol: str) -> dict:
    """Download all daily archives, concat, resample to 1h.

    Resample method: take the LAST 5min sample within each hour bucket
    (close-aligned 1h OI). This matches Bybit V5 1h intervalTime semantics.
    """
    out_path = CACHE_BINANCE / f"{symbol}_1h.joblib"
    days = (END_DATE.date() - START_DATE.date()).days + 1
    target_days = [START_DATE + timedelta(days=i) for i in range(days)]

    log.info("[%s] binance archive: %d days to fetch", symbol, days)
    session = requests.Session()
    frames = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_one_day, symbol, d, session): d for d in target_days}
        n_done = 0
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                frames.append(df)
            n_done += 1
            if n_done % 100 == 0:
                log.info("[%s] %d/%d days fetched", symbol, n_done, days)

    if not frames:
        log.error("[%s] no frames", symbol)
        return {"status": "no_data"}

    full = pd.concat(frames).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    # naive UTC
    if full.index.tz is not None:
        full.index = full.index.tz_localize(None)
    # Resample to 1h: take last 5min sample in each hour (close-aligned)
    hourly = full["open_interest"].resample("1h").last().dropna()
    hourly_df = pd.DataFrame({"ts": hourly.index, "oi": hourly.values}).reset_index(drop=True)

    joblib.dump(hourly_df, out_path, compress=3)
    elapsed = time.time() - t0
    log.info("[%s] binance 1h cached: n=%d range=%s..%s in %.1fs",
             symbol, len(hourly_df), hourly_df["ts"].min(), hourly_df["ts"].max(), elapsed)
    return {"status": "ok", "n": len(hourly_df),
            "min_ts": str(hourly_df["ts"].min()),
            "max_ts": str(hourly_df["ts"].max()),
            "elapsed_s": round(elapsed, 1)}


# --------------------- Bybit V5 REST (1h native) ---------------------
def backfill_bybit_oi(symbol: str) -> dict:
    """Bybit V5 openInterest 1h with cursor pagination, paginate from now backwards
    until reaching START_DATE.
    """
    out_path = CACHE_BYBIT / f"{symbol}_1h.joblib"
    log.info("[%s] bybit oi: paginating...", symbol)
    t0 = time.time()
    rows = []
    cursor = None
    page = 0
    end_ms = int(END_DATE.timestamp() * 1000)
    start_ms = int(START_DATE.timestamp() * 1000)

    for page in range(2000):
        params = {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": "1h",
            "limit": 200,
            "endTime": end_ms,
        }
        if cursor:
            params["cursor"] = cursor
        for attempt in range(3):
            try:
                r = requests.get("https://api.bybit.com/v5/market/open-interest",
                                 params=params, timeout=15)
                j = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    log.error("[%s] page %d HTTP fail: %s", symbol, page, e)
                    j = {"retCode": -1}
                else:
                    time.sleep(1.0 * (attempt + 1))

        if j.get("retCode") != 0:
            log.warning("[%s] page %d retCode=%s msg=%s", symbol, page, j.get("retCode"), j.get("retMsg"))
            break
        lst = j.get("result", {}).get("list", [])
        if not lst:
            log.info("[%s] empty page at %d", symbol, page)
            break

        for item in lst:
            ts = int(item["timestamp"])
            oi = float(item["openInterest"])
            rows.append((ts, oi))

        # last ts in this page (Bybit returns DESC order, so list[-1] is oldest)
        oldest_ts = int(lst[-1]["timestamp"])
        if oldest_ts <= start_ms:
            log.info("[%s] reached start at page %d (oldest=%s)", symbol, page,
                     datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).isoformat())
            break

        cursor = j.get("result", {}).get("nextPageCursor")
        if not cursor:
            log.info("[%s] no cursor at page %d", symbol, page)
            break
        time.sleep(0.1)

    if not rows:
        return {"status": "no_data"}

    df = pd.DataFrame(rows, columns=["ts_ms", "oi"])
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_localize(None)
    df = df[["ts", "oi"]].drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    # filter to window
    df = df[(df["ts"] >= START_DATE.replace(tzinfo=None)) & (df["ts"] <= END_DATE.replace(tzinfo=None))].reset_index(drop=True)

    joblib.dump(df, out_path, compress=3)
    elapsed = time.time() - t0
    log.info("[%s] bybit 1h cached: n=%d range=%s..%s in %.1fs pages=%d",
             symbol, len(df), df["ts"].min(), df["ts"].max(), elapsed, page + 1)
    return {"status": "ok", "n": len(df),
            "min_ts": str(df["ts"].min()),
            "max_ts": str(df["ts"].max()),
            "elapsed_s": round(elapsed, 1),
            "pages": page + 1}


# --------------------- Main ---------------------
def main() -> int:
    summary = {"binance": {}, "bybit": {}}
    t_start = time.time()

    log.info("=== paradigm 104 backfill: %s ===", UNIVERSE)
    log.info("Window: %s .. %s", START_DATE.isoformat(), END_DATE.isoformat())

    for sym in UNIVERSE:
        bn_path = CACHE_BINANCE / f"{sym}_1h.joblib"
        if bn_path.exists():
            df = joblib.load(bn_path)
            log.info("[%s] binance cache HIT n=%d", sym, len(df))
            summary["binance"][sym] = {"status": "cached", "n": len(df),
                                       "min_ts": str(df["ts"].min()),
                                       "max_ts": str(df["ts"].max())}
        else:
            summary["binance"][sym] = backfill_binance_oi(sym)

        bb_path = CACHE_BYBIT / f"{sym}_1h.joblib"
        if bb_path.exists():
            df = joblib.load(bb_path)
            log.info("[%s] bybit cache HIT n=%d", sym, len(df))
            summary["bybit"][sym] = {"status": "cached", "n": len(df),
                                     "min_ts": str(df["ts"].min()),
                                     "max_ts": str(df["ts"].max())}
        else:
            summary["bybit"][sym] = backfill_bybit_oi(sym)

    total = time.time() - t_start
    log.info("=== backfill done in %.1fs ===", total)
    for sym in UNIVERSE:
        bn = summary["binance"][sym]
        bb = summary["bybit"][sym]
        log.info("[%s] BN n=%s range=%s..%s | BB n=%s range=%s..%s",
                 sym,
                 bn.get("n"), bn.get("min_ts"), bn.get("max_ts"),
                 bb.get("n"), bb.get("min_ts"), bb.get("max_ts"))

    import json
    with open(CACHE_BINANCE.parent / "p104_backfill_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
