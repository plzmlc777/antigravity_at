"""Naver KR equity helper (Track 3 Sub-task 3B).

KOSPI200/KOSDAQ150 proxy via Naver market-cap ranking + per-stock historical
OHLCV via siseJson.naver.

Why proxy: official KRX index membership requires KRX login (pykrx fails 2026
without KRX_ID/KRX_PW). Top-N by market cap is a clean proxy — KOSPI200
itself is defined by market-cap + liquidity, so the overlap is >90%.

Per memory [[feedback_kr_market_naver_priority]]: Naver is the 1순위 source
for KR equity data. siseJson is the documented public endpoint that powers
naver finance charts.

Cache: OHLCV parquet under backend/runs/dart_track/ohlcv_cache/{code}.parquet.
"""
from __future__ import annotations

import ast
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

import joblib
import pandas as pd

log = logging.getLogger(__name__)

NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; antigravity-research)",
    "Referer": "https://m.stock.naver.com/",
}
SISE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; antigravity-research)",
    "Referer": "https://finance.naver.com/",
}

MARKET_CAP_URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}"
SISE_URL = "https://api.finance.naver.com/siseJson.naver"

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "backend" / "runs" / "dart_track" / "ohlcv_cache"
UNIVERSE_DIR = ROOT / "backend" / "runs" / "dart_track"


def _http_get(url: str, headers: dict, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_top_market_cap(market: str, top_n: int) -> list[dict]:
    """Fetch top-N stocks by market cap for KOSPI or KOSDAQ.
    Returns list of {itemCode, stockName, marketValueRaw} dicts."""
    assert market in ("KOSPI", "KOSDAQ"), market
    out: list[dict] = []
    page = 1
    page_size = 20  # Naver fixed
    while len(out) < top_n:
        url = MARKET_CAP_URL.format(market=market) + f"?page={page}"
        data = json.loads(_http_get(url, NAVER_HEADERS))
        stocks = data.get("stocks", [])
        if not stocks:
            break
        for s in stocks:
            out.append({
                "itemCode": s["itemCode"],
                "stockName": s["stockName"],
                "marketValueRaw": s.get("marketValueRaw"),
                "market": market,
            })
            if len(out) >= top_n:
                break
        if len(stocks) < page_size:
            break
        page += 1
        time.sleep(0.15)  # gentle rate
    return out[:top_n]


def build_universe(top_kospi: int = 200, top_kosdaq: int = 150,
                   force_refresh: bool = False) -> pd.DataFrame:
    """Top-N KOSPI + top-N KOSDAQ universe. Cached to disk."""
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = UNIVERSE_DIR / f"universe_kospi{top_kospi}_kosdaq{top_kosdaq}.joblib"
    if cache_path.exists() and not force_refresh:
        return joblib.load(cache_path)

    rows = fetch_top_market_cap("KOSPI", top_kospi)
    rows += fetch_top_market_cap("KOSDAQ", top_kosdaq)
    df = pd.DataFrame(rows)
    joblib.dump(df, cache_path)
    log.info("universe: KOSPI %d + KOSDAQ %d cached -> %s",
             top_kospi, top_kosdaq, cache_path)
    return df


def _parse_sise_response(raw: bytes) -> pd.DataFrame:
    """Parse the Python-literal siseJson response into a tidy DataFrame.
    Format: [[headers...], [row1...], [row2...], ...] with whitespace/tabs."""
    text = raw.decode("utf-8")
    text = re.sub(r"[\n\t\r]", "", text)
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError) as e:
        log.warning("sise parse failure: %s", e)
        return pd.DataFrame()
    if not parsed or len(parsed) < 2:
        return pd.DataFrame()
    rows = parsed[1:]
    cols = ["date", "open", "high", "low", "close", "volume", "foreign_ratio"]
    df = pd.DataFrame(rows, columns=cols[: len(rows[0])])
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)


def fetch_ohlcv(code: str, bgn: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV for a stock code via siseJson.naver.
    bgn/end: YYYYMMDD. Returns DataFrame indexed by date with O/H/L/C/V."""
    params = {
        "symbol": code,
        "requestType": "1",
        "startTime": bgn,
        "endTime": end,
        "timeframe": "day",
    }
    url = SISE_URL + "?" + urllib.parse.urlencode(params)
    raw = _http_get(url, SISE_HEADERS, timeout=20)
    return _parse_sise_response(raw)


def get_ohlcv_cached(code: str, bgn: str, end: str,
                     force_refresh: bool = False) -> pd.DataFrame:
    """Cached OHLCV fetch. Re-fetches if cache window does not cover [bgn, end]."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{code}.joblib"
    bgn_dt = pd.to_datetime(bgn, format="%Y%m%d")
    end_dt = pd.to_datetime(end, format="%Y%m%d")

    if cache_path.exists() and not force_refresh:
        df = joblib.load(cache_path)
        if not df.empty and df["date"].min() <= bgn_dt and df["date"].max() >= end_dt:
            return df[(df["date"] >= bgn_dt) & (df["date"] <= end_dt)].reset_index(drop=True)

    df = fetch_ohlcv(code, bgn, end)
    if not df.empty:
        joblib.dump(df, cache_path)
    return df


def warm_cache(codes: list[str], bgn: str, end: str,
               sleep_s: float = 0.10) -> dict[str, int]:
    """Bulk-fetch OHLCV for many codes, cache to disk, return per-code row counts."""
    out: dict[str, int] = {}
    total = len(codes)
    for i, code in enumerate(codes, 1):
        try:
            df = get_ohlcv_cached(code, bgn, end)
            out[code] = len(df)
        except Exception as e:
            log.warning("ohlcv %s FAIL: %s", code, e)
            out[code] = 0
        if i % 25 == 0:
            log.info("warm_cache %d/%d (last=%s rows=%d)", i, total, code, out[code])
        time.sleep(sleep_s)
    return out
