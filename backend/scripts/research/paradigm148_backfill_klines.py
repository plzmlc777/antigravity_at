"""Paradigm 148: Cross-exchange PRICE klines backfill (Bybit V5 + Binance archive).

Substrate
---------
Bybit V5 REST /v5/market/kline   interval=15  (15min)
Binance data.binance.vision  futures/um/daily/klines  15m

Output joblib: backend/runs/ohlcv_cache_15m/{venue}_klines/{SYM}_15m.joblib
  columns: ['ts', 'close']  (close = close price)

Scope: deep-7 universe (paradigm 103/104 verified), 2024-01-01 .. 2026-05-19 (~870 days)
"""
from __future__ import annotations

import io
import json
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
log = logging.getLogger("paradigm148_backfill")

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]

START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 5, 19, tzinfo=timezone.utc)

CACHE_BINANCE = ROOT / "runs" / "ohlcv_cache_15m" / "binance_klines"
CACHE_BYBIT = ROOT / "runs" / "ohlcv_cache_15m" / "bybit_klines"
DAILY_CACHE_BINANCE = ROOT / "runs" / "ohlcv_cache_15m" / "binance_klines_daily"

CACHE_BINANCE.mkdir(parents=True, exist_ok=True)
CACHE_BYBIT.mkdir(parents=True, exist_ok=True)
DAILY_CACHE_BINANCE.mkdir(parents=True, exist_ok=True)

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/klines"


# --------------------- Binance 15m archive ---------------------
def _bn_archive_url(symbol: str, date: datetime) -> str:
    ds = date.strftime("%Y-%m-%d")
    return f"{ARCHIVE_BASE}/{symbol}/15m/{symbol}-15m-{ds}.zip"


def _parse_klines_zip(zip_bytes: bytes) -> pd.DataFrame:
    """Binance kline archive columns: openTime,open,high,low,close,volume,closeTime,
    quoteAssetVolume,numberOfTrades,takerBuyBaseAssetVolume,takerBuyQuoteAssetVolume,ignore"""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            df = pd.read_csv(fh, header=None)
    if df.empty:
        return df
    # Newer archives may have header row; detect by checking row[0,0]
    if isinstance(df.iloc[0, 0], str) and not df.iloc[0, 0].isdigit():
        df = df.iloc[1:].reset_index(drop=True)
    # ms epoch
    df["ts"] = pd.to_datetime(pd.to_numeric(df[0], errors="coerce"), unit="ms", utc=True).dt.tz_localize(None)
    df["close"] = pd.to_numeric(df[4], errors="coerce")
    out = df[["ts", "close"]].dropna()
    return out


def _bn_fetch_one_day(symbol: str, date: datetime, session: requests.Session) -> pd.DataFrame | None:
    cache_path = DAILY_CACHE_BINANCE / f"{symbol}__{date.strftime('%Y-%m-%d')}.joblib"
    if cache_path.exists():
        try:
            return joblib.load(cache_path)
        except Exception:
            pass

    url = _bn_archive_url(symbol, date)
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                joblib.dump(pd.DataFrame(), cache_path, compress=3)
                return pd.DataFrame()
            r.raise_for_status()
            df = _parse_klines_zip(r.content)
            joblib.dump(df, cache_path, compress=3)
            return df
        except Exception as e:
            if attempt == 2:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def backfill_binance_klines(symbol: str) -> dict:
    out_path = CACHE_BINANCE / f"{symbol}_15m.joblib"
    if out_path.exists():
        df = joblib.load(out_path)
        return {"status": "cached", "n": len(df),
                "min_ts": str(df["ts"].min()), "max_ts": str(df["ts"].max())}

    days = (END_DATE.date() - START_DATE.date()).days + 1
    target_days = [START_DATE + timedelta(days=i) for i in range(days)]

    log.info("[%s] binance 15m archive: %d days to fetch", symbol, days)
    session = requests.Session()
    frames = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_bn_fetch_one_day, symbol, d, session): d for d in target_days}
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

    full = pd.concat(frames).sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
    joblib.dump(full, out_path, compress=3)
    elapsed = time.time() - t0
    log.info("[%s] binance 15m cached: n=%d range=%s..%s in %.1fs",
             symbol, len(full), full["ts"].min(), full["ts"].max(), elapsed)
    return {"status": "ok", "n": len(full),
            "min_ts": str(full["ts"].min()),
            "max_ts": str(full["ts"].max()),
            "elapsed_s": round(elapsed, 1)}


# --------------------- Bybit V5 klines 15min ---------------------
def backfill_bybit_klines(symbol: str) -> dict:
    out_path = CACHE_BYBIT / f"{symbol}_15m.joblib"
    if out_path.exists():
        df = joblib.load(out_path)
        return {"status": "cached", "n": len(df),
                "min_ts": str(df["ts"].min()), "max_ts": str(df["ts"].max())}

    log.info("[%s] bybit 15m kline: paginating...", symbol)
    t0 = time.time()
    rows = []
    end_ms = int(END_DATE.timestamp() * 1000)
    start_ms = int(START_DATE.timestamp() * 1000)

    # Bybit returns DESC, so we paginate by setting end= older each batch
    cur_end_ms = end_ms
    for page in range(2000):
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": "15",
            "limit": 1000,
            "end": cur_end_ms,
        }
        j = {"retCode": -1}
        for attempt in range(3):
            try:
                r = requests.get("https://api.bybit.com/v5/market/kline",
                                 params=params, timeout=15)
                j = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    log.error("[%s] page %d HTTP fail: %s", symbol, page, e)
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
            ts = int(item[0])
            close = float(item[4])
            rows.append((ts, close))

        oldest_ts = int(lst[-1][0])
        if oldest_ts <= start_ms:
            log.info("[%s] reached start at page %d (oldest=%s)", symbol, page,
                     datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).isoformat())
            break

        # advance pagination: next end = oldest_ts - 1
        cur_end_ms = oldest_ts - 1
        time.sleep(0.1)

    if not rows:
        return {"status": "no_data"}

    df = pd.DataFrame(rows, columns=["ts_ms", "close"])
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_localize(None)
    df = df[["ts", "close"]].drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df = df[(df["ts"] >= START_DATE.replace(tzinfo=None)) & (df["ts"] <= END_DATE.replace(tzinfo=None))].reset_index(drop=True)

    joblib.dump(df, out_path, compress=3)
    elapsed = time.time() - t0
    log.info("[%s] bybit 15m cached: n=%d range=%s..%s in %.1fs pages=%d",
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

    log.info("=== paradigm 148 klines backfill: %s ===", UNIVERSE)
    log.info("Window: %s .. %s", START_DATE.isoformat(), END_DATE.isoformat())

    for sym in UNIVERSE:
        summary["binance"][sym] = backfill_binance_klines(sym)
        summary["bybit"][sym] = backfill_bybit_klines(sym)

    total = time.time() - t_start
    log.info("=== backfill done in %.1fs ===", total)
    for sym in UNIVERSE:
        bn = summary["binance"][sym]
        bb = summary["bybit"][sym]
        log.info("[%s] BN n=%s range=%s..%s | BB n=%s range=%s..%s",
                 sym,
                 bn.get("n"), bn.get("min_ts"), bn.get("max_ts"),
                 bb.get("n"), bb.get("min_ts"), bb.get("max_ts"))

    out_path = CACHE_BINANCE.parent / "p148_backfill_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info("summary -> %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
