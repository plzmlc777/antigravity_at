"""Download 12-col monthly kline archives from data.binance.vision and write
joblib cache (separate from existing 5-col DB cache).

Used for paradigm 142-v2 and any future paradigm requiring taker_buy_quote_volume
or quote_asset_volume axes.

Schema preserved: open_time, open, high, low, close, volume (base),
                  close_time, quote_volume, count,
                  taker_buy_volume, taker_buy_quote_volume, ignore

URL pattern:
  https://data.binance.vision/data/futures/um/monthly/klines/{SYM}USDT/{TF}/{SYM}USDT-{TF}-YYYY-MM.zip

Output: backend/runs/ohlcv_cache_12col/{SYM}USDT_{TF}.joblib  (DataFrame indexed by open_time)

Usage:
  python3 -m scripts.binance.backfill_12col_klines \\
      --symbols BTC,ETH,SOL,XRP,DOGE,ADA,AVAX,BNB,LINK,BCH,FIL,LTC,NEAR,WIF \\
      --timeframe 4h --start 2024-02 --end 2026-05 --parallel 8
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_12col_klines")

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]
CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"


def _archive_url(symbol_pair: str, tf: str, year: int, month: int) -> str:
    return f"{ARCHIVE_BASE}/{symbol_pair}/{tf}/{symbol_pair}-{tf}-{year:04d}-{month:02d}.zip"


def _parse_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            data = fh.read()
            head_text = data[:200].decode("utf-8", errors="replace").lower()
            has_header = "open_time" in head_text
            df = pd.read_csv(
                io.BytesIO(data),
                names=KLINE_COLUMNS,
                header=0 if has_header else None,
            )
    if df.empty:
        return df
    return df


def _fetch_one(symbol_pair: str, tf: str, year: int, month: int,
               session: requests.Session, retries: int = 2) -> pd.DataFrame | None:
    url = _archive_url(symbol_pair, tf, year, month)
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return _parse_zip(r.content)
        except Exception as e:
            if attempt == retries:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def _month_iter(start_ym: tuple[int, int], end_ym: tuple[int, int]):
    y, m = start_ym
    ey, em = end_ym
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def download_symbol(symbol_pair: str, tf: str, start_ym, end_ym,
                    parallel: int = 8) -> pd.DataFrame:
    months = list(_month_iter(start_ym, end_ym))
    log.info("[%s/%s] downloading %d months", symbol_pair, tf, len(months))
    frames = []
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {
            ex.submit(_fetch_one, symbol_pair, tf, y, m, session): (y, m)
            for (y, m) in months
        }
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_values("open_time").drop_duplicates("open_time")
    return out


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["open_time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms")
    for c in ("open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_volume", "taker_buy_quote_volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").astype("Int64")
    df = df.set_index("open_time").sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def cache_path(symbol_pair: str, tf: str) -> Path:
    return CACHE_DIR / f"{symbol_pair}_{tf}.joblib"


def load_12col_cached(symbol_pair: str, tf: str = "4h") -> pd.DataFrame:
    path = cache_path(symbol_pair, tf)
    if not path.exists():
        raise FileNotFoundError(f"12-col cache missing: {path}")
    df = joblib.load(path)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _parse_ym(s: str) -> tuple[int, int]:
    parts = s.split("-")
    return int(parts[0]), int(parts[1])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True,
                   help="Comma-separated bare symbol list (e.g., BTC,ETH,SOL) — USDT pair auto-appended")
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--start", required=True, help="YYYY-MM start month inclusive")
    p.add_argument("--end", required=True, help="YYYY-MM end month inclusive")
    p.add_argument("--parallel", type=int, default=8)
    args = p.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    start_ym = _parse_ym(args.start)
    end_ym = _parse_ym(args.end)
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    syms_pair = [s + "USDT" if not s.endswith("USDT") else s for s in syms]

    log.info("Backfill 12-col klines: %d syms × tf=%s × %s..%s",
             len(syms_pair), args.timeframe, args.start, args.end)

    summary = []
    t_total = time.time()
    for sym_pair in syms_pair:
        t0 = time.time()
        df_raw = download_symbol(sym_pair, args.timeframe, start_ym, end_ym, parallel=args.parallel)
        dl_s = time.time() - t0

        if df_raw.empty:
            log.warning("[%s] empty download — skip", sym_pair)
            summary.append({"symbol": sym_pair, "status": "empty", "n_rows": 0, "dl_s": dl_s})
            continue

        df = normalize_df(df_raw)
        path = cache_path(sym_pair, args.timeframe)
        joblib.dump(df, path, compress=3)
        size_mb = path.stat().st_size / (1024 * 1024)
        log.info("[%s] cached %d rows %s..%s -> %.2fMB in %.1fs",
                 sym_pair, len(df), df.index.min(), df.index.max(), size_mb, dl_s)
        summary.append({
            "symbol": sym_pair,
            "status": "cached",
            "n_rows": len(df),
            "min_ts": str(df.index.min()),
            "max_ts": str(df.index.max()),
            "dl_s": round(dl_s, 1),
            "file_mb": round(size_mb, 2),
        })

    total_s = time.time() - t_total
    log.info("done in %.1fs", total_s)
    for s in summary:
        log.info("  %s", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
