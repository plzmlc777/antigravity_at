"""Download + parse data.binance.vision daily metric archives.

The metrics CSV contains 5-min snapshots of:
    sum_open_interest                  (in coins)
    sum_open_interest_value            (in USDT)
    count_toptrader_long_short_ratio   (top trader account ratio = longs/shorts)
    sum_toptrader_long_short_ratio     (top trader position ratio)
    count_long_short_ratio             (global account ratio)
    sum_taker_long_short_vol_ratio     (taker buy vol / taker sell vol)

URL pattern:
  https://data.binance.vision/data/futures/um/daily/metrics/{SYMBOL}/{SYMBOL}-metrics-YYYY-MM-DD.zip
"""
from __future__ import annotations

import io
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/metrics"


def _archive_url(symbol: str, date: datetime) -> str:
    ds = date.strftime("%Y-%m-%d")
    return f"{ARCHIVE_BASE}/{symbol}/{symbol}-metrics-{ds}.zip"


def parse_metrics_csv(zip_bytes: bytes) -> pd.DataFrame:
    """Parse one daily metrics zip into a DataFrame indexed by create_time."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            df = pd.read_csv(fh)
    if df.empty:
        return df
    # Standardize columns
    df["create_time"] = pd.to_datetime(df["create_time"])
    df = df.rename(columns={
        "sum_open_interest": "open_interest",
        "sum_open_interest_value": "open_interest_value_usdt",
        "count_toptrader_long_short_ratio": "toptrader_account_ls_ratio",
        "sum_toptrader_long_short_ratio": "toptrader_position_ls_ratio",
        "count_long_short_ratio": "global_account_ls_ratio",
        "sum_taker_long_short_vol_ratio": "taker_buy_sell_ratio",
    })
    df = df.set_index("create_time").sort_index()
    return df.drop(columns=[c for c in ["symbol"] if c in df.columns])


def _fetch_one(symbol: str, date: datetime, session: requests.Session, retries: int = 2) -> Optional[pd.DataFrame]:
    url = _archive_url(symbol, date)
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None  # weekend / not yet uploaded
            r.raise_for_status()
            return parse_metrics_csv(r.content)
        except Exception as e:
            if attempt == retries:
                logger.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def download_metrics_range(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    *,
    cache_dir: Path | str | None = None,
    parallel: int = 8,
) -> pd.DataFrame:
    """Download daily metric archives for [start_date, end_date], concatenate.

    cache_dir: if provided, store each daily DataFrame as joblib for re-use.
    Returns: single DataFrame indexed by 5-min create_time.
    """
    days = (end_date.date() - start_date.date()).days + 1
    if days <= 0:
        return pd.DataFrame()

    target_days = [start_date.date() + timedelta(days=i) for i in range(days)]
    logger.info("Downloading %s metrics for %d days", symbol, days)

    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    def _load_or_fetch(d, session):
        if cache:
            cache_path = cache / f"{symbol}__{d.isoformat()}.joblib"
            if cache_path.exists():
                import joblib
                try:
                    df = joblib.load(cache_path)
                    return df
                except Exception:
                    pass
        df = _fetch_one(symbol, datetime(d.year, d.month, d.day), session)
        if df is not None and cache:
            import joblib
            joblib.dump(df, cache / f"{symbol}__{d.isoformat()}.joblib", compress=3)
        return df

    session = requests.Session()
    frames = []
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(_load_or_fetch, d, session): d for d in target_days}
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                frames.append(df)

    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    # Convert numeric columns
    for c in out.columns:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out
