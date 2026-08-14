"""Paradigm 160: Bybit V5 4h klines backfill with volume column.

Substrate
---------
Bybit V5 REST /v5/market/kline   interval=240  (4h)
  item schema: [ts_ms, open, high, low, close, volume, turnover(=quote_volume)]

Output joblib: backend/runs/ohlcv_cache/bybit_klines_4h/{SYM}_4h.joblib
  columns: ['open_time', 'open', 'high', 'low', 'close', 'volume', 'quote_volume']

Scope: deep-7 universe (paradigm 103/104/148 verified), 2024-01-01 .. 2026-04-30
       to align with binance 12-col 4h cache (2024-02-01 .. 2026-04-30 = 819 days)
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p160_backfill_bybit_4h")

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]

START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)

CACHE_DIR = ROOT / "runs" / "ohlcv_cache" / "bybit_klines_4h"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _bybit_kline_paged(symbol: str, interval: str = "240") -> pd.DataFrame:
    """Bybit V5 kline. Walk backwards from END_DATE using `end` cursor."""
    start_ms = int(START_DATE.timestamp() * 1000)
    end_ms = int(END_DATE.timestamp() * 1000)

    rows = []
    cur_end_ms = end_ms
    page = 0
    seen_oldest = end_ms
    while True:
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": 1000,
            "end": cur_end_ms,
        }
        try:
            r = requests.get("https://api.bybit.com/v5/market/kline",
                             params=params, timeout=15)
            j = r.json()
        except Exception as e:
            log.error("[%s] page %d HTTP fail: %s", symbol, page, e)
            time.sleep(1.5)
            continue

        if j.get("retCode") != 0:
            log.warning("[%s] page %d retCode=%s msg=%s", symbol, page,
                        j.get("retCode"), j.get("retMsg"))
            break

        lst = j.get("result", {}).get("list", [])
        if not lst:
            log.info("[%s] empty page at %d", symbol, page)
            break

        for item in lst:
            # V5 4h kline item: [ts_ms, open, high, low, close, volume, turnover]
            ts_ms = int(item[0])
            o = float(item[1]); h = float(item[2]); l = float(item[3])
            c = float(item[4])
            v = float(item[5])
            qv = float(item[6])
            rows.append((ts_ms, o, h, l, c, v, qv))

        oldest_ts = int(lst[-1][0])
        if oldest_ts <= start_ms:
            log.info("[%s] reached start at page %d (oldest=%s)", symbol, page,
                     datetime.fromtimestamp(oldest_ts/1000, tz=timezone.utc).isoformat())
            break
        if oldest_ts >= seen_oldest:
            log.warning("[%s] cursor not advancing at page %d", symbol, page)
            break
        seen_oldest = oldest_ts
        cur_end_ms = oldest_ts - 1
        page += 1
        time.sleep(0.1)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["ts_ms", "open", "high", "low", "close",
                                     "volume", "quote_volume"])
    df["open_time"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_localize(None)
    df = df.drop_duplicates(subset=["ts_ms"]).sort_values("ts_ms").reset_index(drop=True)
    df = df[(df["open_time"] >= pd.Timestamp(START_DATE.replace(tzinfo=None))) &
            (df["open_time"] <= pd.Timestamp(END_DATE.replace(tzinfo=None)))]
    df = df[["open_time", "open", "high", "low", "close", "volume", "quote_volume"]]
    return df.reset_index(drop=True)


def main():
    t_start = time.time()
    log.info("Bybit 4h klines backfill — universe=%d syms, window=%s..%s",
             len(UNIVERSE), START_DATE.date(), END_DATE.date())

    for sym in UNIVERSE:
        cache_path = CACHE_DIR / f"{sym}_4h.joblib"
        if cache_path.exists():
            existing = joblib.load(cache_path)
            log.info("[%s] cache exists rows=%d range=%s..%s — SKIP",
                     sym, len(existing), existing["open_time"].min(),
                     existing["open_time"].max())
            continue

        t0 = time.time()
        df = _bybit_kline_paged(sym, interval="240")
        if df.empty:
            log.warning("[%s] no data fetched — SKIP", sym)
            continue
        joblib.dump(df, cache_path)
        log.info("[%s] saved n=%d range=%s..%s wall=%.1fs",
                 sym, len(df), df["open_time"].min(), df["open_time"].max(),
                 time.time() - t0)

    log.info("ALL DONE wall=%.1fs", time.time() - t_start)


if __name__ == "__main__":
    main()
