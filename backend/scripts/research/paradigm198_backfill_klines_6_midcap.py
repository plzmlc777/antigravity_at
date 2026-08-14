"""Paradigm 198: 4h OHLCV cache backfill for 6 mid-cap syms (universe expansion 14->20).

Hypothesis (paradigm 198):
    paradigm 195 RV-ratio formulation identical, universe expansion 14 -> 20.
    Concentration ratio 14-sym universe-size-bound vs statistic-form-bound verify.

Backfill candidates (paradigm 22 R-5 expansion universes pool):
    deep_10 \ existing_14 = {DOT}
    midcap_10 \ existing_14 = {LDO, UNI, ETC, WLD, JUP, PYTH}
    -> 7 candidates, take first 6 by 2.25yr availability.

Source: data.binance.vision futures/um/daily/klines 4h archive
Output: backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib (12-column schema
        matching existing cache: open_time index + 11 cols).

Existing 14-sym cache range: 2024-02-01 -> 2026-04-30 (~819 days, 4920 4h bars).
Match this range strictly.
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("paradigm198_backfill")

# 7 candidates -> select first 6 (drop 1 if all backfill OK)
CANDIDATES = ["DOTUSDT", "LDOUSDT", "UNIUSDT", "ETCUSDT", "WLDUSDT", "JUPUSDT", "PYTHUSDT"]

# Match existing 14-sym cache range exactly
START_DATE = datetime(2024, 2, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 4, 30, tzinfo=timezone.utc)

CACHE_DIR = ROOT / "runs" / "ohlcv_cache_12col"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/klines"

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def _archive_url(symbol: str, date: datetime) -> str:
    ds = date.strftime("%Y-%m-%d")
    return f"{ARCHIVE_BASE}/{symbol}/4h/{symbol}-4h-{ds}.zip"


def _parse_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            data = fh.read()
    if not data:
        return pd.DataFrame()
    head_text = data[:200].decode("utf-8", errors="replace").lower()
    has_header = "open_time" in head_text or "open" in head_text.split(",")[0]
    df = pd.read_csv(
        io.BytesIO(data),
        names=KLINE_COLUMNS,
        header=0 if has_header else None,
    )
    if df.empty:
        return df
    # open_time -> datetime index
    df["open_time"] = pd.to_datetime(
        pd.to_numeric(df["open_time"], errors="coerce"),
        unit="ms", utc=True,
    ).dt.tz_localize(None)
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["close_time"] = pd.to_numeric(df["close_time"], errors="coerce")
    df = df.dropna(subset=["open_time", "close"]).set_index("open_time")
    return df


def _fetch_one_day(symbol: str, date: datetime, session: requests.Session,
                   retries: int = 2) -> pd.DataFrame | None:
    url = _archive_url(symbol, date)
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None  # symbol not listed on this date
            r.raise_for_status()
            return _parse_zip(r.content)
        except Exception as e:
            if attempt == retries:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def backfill_sym(symbol: str, parallel: int = 16) -> tuple[str, pd.DataFrame, int, int]:
    """Backfill 4h klines for symbol. Returns (sym, df, n_found, n_missing)."""
    cache_path = CACHE_DIR / f"{symbol}_4h.joblib"
    if cache_path.exists():
        try:
            df = joblib.load(cache_path)
            log.info("[%s] already cached: shape=%s range=%s..%s",
                     symbol, df.shape, df.index.min(), df.index.max())
            return symbol, df, len(df), 0
        except Exception:
            pass

    days = (END_DATE - START_DATE).days + 1
    target_dates = [START_DATE + timedelta(days=i) for i in range(days)]
    log.info("[%s] downloading %d days (4h archive)", symbol, days)

    session = requests.Session()
    frames: list[pd.DataFrame] = []
    n_missing = 0
    n_found = 0
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(_fetch_one_day, symbol, d, session): d for d in target_dates}
        for f in as_completed(futures):
            df = f.result()
            if df is None or df.empty:
                n_missing += 1
                continue
            frames.append(df)
            n_found += 1

    if not frames:
        log.warning("[%s] NO data found", symbol)
        return symbol, pd.DataFrame(), 0, n_missing

    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    log.info("[%s] backfilled shape=%s range=%s..%s n_days_found=%d n_missing=%d",
             symbol, out.shape, out.index.min(), out.index.max(), n_found, n_missing)

    if len(out) >= 4000:  # ≥1.8yr 4h bars threshold
        joblib.dump(out, cache_path, compress=3)
        log.info("[%s] saved to %s", symbol, cache_path)
    else:
        log.warning("[%s] only %d bars (<4000), NOT cached", symbol, len(out))

    return symbol, out, n_found, n_missing


def main() -> None:
    log.info("paradigm 198 backfill: %d candidates", len(CANDIDATES))
    t0 = time.time()
    summary = []
    for sym in CANDIDATES:
        ts_sym = time.time()
        s, df, found, missing = backfill_sym(sym, parallel=16)
        summary.append(dict(
            sym=s, n_bars=len(df), n_days_found=found, n_days_missing=missing,
            range_start=str(df.index.min()) if len(df) else None,
            range_end=str(df.index.max()) if len(df) else None,
            elapsed_s=time.time() - ts_sym,
            cached=(len(df) >= 4000),
        ))
    log.info("=== summary ===")
    for s in summary:
        log.info("%s: bars=%d cached=%s elapsed=%.1fs",
                 s["sym"], s["n_bars"], s["cached"], s["elapsed_s"])
    log.info("total elapsed %.1fs", time.time() - t0)


if __name__ == "__main__":
    main()
