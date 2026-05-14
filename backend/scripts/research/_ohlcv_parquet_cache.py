"""One-shot OHLCV 1m joblib cache builder for Research Track R-3+ scripts.

Motivation
----------
On 2026-05-14 the paradigm-69 R-3 long-horizon re-run hit a 15-min foreground
wall-clock limit because loading 14 alts × 1.24M-row OHLCV tables from
PostgreSQL via ORDER BY scan took ~13-15 min. Once cached as joblib, the
same load drops to ~3-5 sec.

(File name kept as `_ohlcv_parquet_cache.py` for historical reasons — the
actual on-disk format is joblib because pyarrow/fastparquet are not installed
in the Mint venv. The existing microstructure / premium_index joblib caches
use the same pattern.)

Usage
-----
  python3 -m scripts.research._ohlcv_parquet_cache \\
      --symbols BTCUSDT,ETHUSDT,SOLUSDT,...

The cache is written to `backend/runs/ohlcv_cache/{SYM}_1m.joblib`. Research
scripts can read via `load_ohlcv_1m_cached(sym)` which auto-falls-back to DB
if cache missing.

Idempotent: re-running rewrites cache (full overwrite). If you want
incremental, drop the joblib first.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ohlcv_cache")

CACHE_DIR = ROOT / "runs" / "ohlcv_cache"


def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol}_1m.joblib"


def load_from_db(sym: str) -> pd.DataFrame:
    """Pull all 1m ohlcv rows for `sym` from PostgreSQL."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
            ),
            {"s": sym},
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[~df.index.duplicated(keep="first")]
    return df


def build_cache(symbols: list[str]) -> dict:
    """Build parquet cache for the given symbols. Returns per-sym status dict."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for sym in symbols:
        t0 = time.time()
        df = load_from_db(sym)
        load_s = time.time() - t0
        if df.empty:
            log.warning("[%s] no rows in DB, skipping cache write", sym)
            out[sym] = {"status": "no_rows", "load_s": load_s}
            continue

        path = cache_path(sym)
        t1 = time.time()
        joblib.dump(df, path, compress=3)
        write_s = time.time() - t1

        out[sym] = {
            "status": "cached",
            "n_rows": len(df),
            "min_ts": str(df.index.min()),
            "max_ts": str(df.index.max()),
            "load_s": round(load_s, 1),
            "write_s": round(write_s, 1),
            "cache_bytes": path.stat().st_size,
            "path": str(path),
        }
        log.info(
            "[%s] cached %s rows in %.1fs load + %.1fs write -> %s (%.1fMB)",
            sym, f"{len(df):,}", load_s, write_s, path.name,
            path.stat().st_size / (1024 * 1024),
        )
    return out


def load_ohlcv_1m_cached(symbol: str) -> pd.DataFrame:
    """Public helper for R-x scripts.

    Returns cached joblib if present (fast ~3-5s), else falls back to
    direct DB load (slow ~30-60s for 1.2M rows).
    """
    path = cache_path(symbol)
    if path.exists():
        df = joblib.load(path)
        # ensure index dtype + sort
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    log.warning("ohlcv cache miss for %s — falling back to DB", symbol)
    return load_from_db(symbol)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--symbols",
        default="BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,AVAXUSDT,LINKUSDT,ADAUSDT,BCHUSDT,"
                "BNBUSDT,FILUSDT,LTCUSDT,NEARUSDT,WIFUSDT,XRPUSDT",
        help="Comma-separated symbol list",
    )
    args = p.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    log.info("building parquet cache for %d symbols at %s", len(syms), CACHE_DIR)

    t0 = time.time()
    results = build_cache(syms)
    total_s = time.time() - t0
    log.info("done in %.1f s", total_s)

    for sym, info in results.items():
        if info["status"] == "cached":
            print(f"  {sym}: {info['n_rows']:>9,} rows ({info['min_ts']} → {info['max_ts']}) "
                  f"load {info['load_s']}s write {info['write_s']}s "
                  f"file {info['cache_bytes']/1024/1024:.1f}MB")
        else:
            print(f"  {sym}: {info['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
