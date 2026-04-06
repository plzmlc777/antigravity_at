#!/usr/bin/env python3
"""
Exchange OHLCV Fetcher — DB 의존 없이 거래소 REST API에서 직접 캔들 데이터 수집.

Supported:
  - Binance Spot/Futures (no auth required)

Usage:
    from fetch_exchange import load_ohlcv_exchange
    df = load_ohlcv_exchange("BTCUSDT", interval="1h", days=30)
    df = load_ohlcv_exchange("BTCUSDT", interval="1m", days=7,
                              from_date="2026-03-01", to_date="2026-03-07")
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict

import pandas as pd


# ─── Binance REST API ────────────────────────────────────────────────

BINANCE_SPOT_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUTURES_URL = "https://fapi.binance.com/fapi/v1/klines"

# Binance interval strings
_INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "60m": "1h", "1h": "1h", "4h": "4h", "8h": "8h", "12h": "12h",
    "1d": "1d", "1w": "1w", "1M": "1M",
}

# Max candles per Binance API call
_BINANCE_LIMIT = 1000


def _to_ms(dt: datetime) -> int:
    """Convert datetime to milliseconds since epoch."""
    return int(dt.timestamp() * 1000)


def _from_ms(ms: int) -> datetime:
    """Convert milliseconds to UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _fetch_binance_klines(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    futures: bool = False,
) -> List[List]:
    """
    Fetch klines from Binance API with pagination.
    Returns raw kline arrays.
    """
    url_base = BINANCE_FUTURES_URL if futures else BINANCE_SPOT_URL
    bi_interval = _INTERVAL_MAP.get(interval, interval)

    all_klines = []
    current_start = start_ms

    while current_start < end_ms:
        params = (
            f"?symbol={symbol}&interval={bi_interval}"
            f"&startTime={current_start}&endTime={end_ms}"
            f"&limit={_BINANCE_LIMIT}"
        )
        url = url_base + params

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2)
                continue
            raise

        if not data:
            break

        all_klines.extend(data)

        # Move start to after last kline's open time
        last_open_ms = data[-1][0]
        if last_open_ms <= current_start:
            break
        current_start = last_open_ms + 1

        # Rate limit courtesy
        if len(data) == _BINANCE_LIMIT:
            time.sleep(0.1)

    return all_klines


def _klines_to_df(klines: List[List]) -> pd.DataFrame:
    """Convert Binance kline arrays to DataFrame."""
    if not klines:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    rows = []
    for k in klines:
        rows.append({
            "timestamp": _from_ms(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def load_ohlcv_exchange(
    symbol: str,
    interval: str = "1h",
    days: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    futures: bool = False,
) -> pd.DataFrame:
    """
    거래소 API에서 OHLCV 데이터를 직접 로드.

    Args:
        symbol: 거래소 심볼 (e.g., "BTCUSDT", "ETHUSDT")
        interval: 캔들 인터벌 ("1m", "5m", "1h", "1d" 등)
        days: 최근 N일 (from_date 미지정 시 사용)
        from_date: 시작일 "YYYY-MM-DD"
        to_date: 종료일 "YYYY-MM-DD"
        futures: True면 USDM Futures API 사용

    Returns:
        DataFrame with: timestamp, open, high, low, close, volume
    """
    now = datetime.now(tz=timezone.utc)

    if from_date:
        start = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    elif days:
        start = now - timedelta(days=days)
    else:
        start = now - timedelta(days=30)

    if to_date:
        end = datetime.strptime(to_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    else:
        end = now

    start_ms = _to_ms(start)
    end_ms = _to_ms(end)

    klines = _fetch_binance_klines(symbol, interval, start_ms, end_ms, futures=futures)
    df = _klines_to_df(klines)

    return df


# ─── Dual-source loader (exchange first, DB fallback) ────────────────

def load_ohlcv_auto(
    symbol: str,
    interval: str = "1h",
    days: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    source: str = "auto",
    futures: bool = False,
) -> pd.DataFrame:
    """
    자동 소스 선택 로더.

    source:
      - "exchange": 거래소 API만
      - "db": PostgreSQL만 (fetch_data.load_ohlcv)
      - "auto": exchange 먼저 시도 → 실패 시 DB fallback
    """
    if source == "db":
        from fetch_data import load_ohlcv
        return load_ohlcv(symbol, interval, days, from_date, to_date)

    if source == "exchange":
        return load_ohlcv_exchange(symbol, interval, days, from_date, to_date, futures=futures)

    # auto: exchange first
    try:
        df = load_ohlcv_exchange(symbol, interval, days, from_date, to_date, futures=futures)
        if not df.empty:
            return df
    except Exception as e:
        print(f"Exchange fetch failed ({e}), falling back to DB...")

    try:
        from fetch_data import load_ohlcv
        return load_ohlcv(symbol, interval, days, from_date, to_date)
    except Exception as e:
        print(f"DB fetch also failed: {e}")
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch OHLCV from exchange API")
    parser.add_argument("symbol", help="Symbol (e.g., BTCUSDT)")
    parser.add_argument("--interval", default="1h", help="Candle interval (default: 1h)")
    parser.add_argument("--days", type=int, default=7, help="Days of data (default: 7)")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--futures", action="store_true", help="Use futures API")
    parser.add_argument("--source", default="exchange", choices=["exchange", "db", "auto"])

    args = parser.parse_args()

    if args.source == "exchange":
        df = load_ohlcv_exchange(
            args.symbol, args.interval, args.days,
            args.from_date, args.to_date, args.futures,
        )
    else:
        df = load_ohlcv_auto(
            args.symbol, args.interval, args.days,
            args.from_date, args.to_date, args.source, args.futures,
        )

    print(f"Loaded {len(df)} candles for {args.symbol} ({args.interval})")
    if not df.empty:
        print(f"  Period: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")
        print(df.tail(5).to_string(index=False))
