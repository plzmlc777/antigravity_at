#!/usr/bin/env python3
"""
Data Fetcher - PostgreSQL에서 OHLCV 데이터를 직접 조회하고 캔들을 집계한다.
기존 BacktestEngine과 동일한 데이터 소스를 사용하여 결과 비교가 가능하다.

Usage:
    from fetch_data import load_ohlcv
    df = load_ohlcv("005930", interval="1d", days=365)
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

try:
    import psycopg2
except ImportError:
    print("psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)


def get_db_connection():
    """Create PostgreSQL connection using .env settings."""
    # Try loading from .env files
    env_paths = [
        os.path.join(os.path.dirname(__file__), "../../../../.env"),
        os.path.join(os.path.dirname(__file__), "../../../../backend/.env"),
    ]

    db_config = {
        "host": os.environ.get("POSTGRES_SERVER", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "user": os.environ.get("POSTGRES_USER", "antigravity_user"),
        "password": os.environ.get("POSTGRES_PASSWORD", "antigravity_password"),
        "dbname": os.environ.get("POSTGRES_DB", "antigravity_db"),
    }

    for env_path in env_paths:
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key == "POSTGRES_SERVER":
                            db_config["host"] = val
                        elif key == "POSTGRES_PORT":
                            db_config["port"] = val
                        elif key == "POSTGRES_USER":
                            db_config["user"] = val
                        elif key == "POSTGRES_PASSWORD":
                            db_config["password"] = val
                        elif key == "POSTGRES_DB":
                            db_config["dbname"] = val
            break

    return psycopg2.connect(**db_config)


def load_ohlcv_raw(
    symbol: str,
    time_frame: str = "1m",
    days: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    PostgreSQL에서 OHLCV 원본 데이터를 조회한다.

    Args:
        symbol: 종목 코드 (e.g., "005930", "BTCUSDT")
        time_frame: DB에 저장된 time_frame (보통 "1m")
        days: 최근 N일
        from_date: 시작일 (YYYY-MM-DD)
        to_date: 종료일 (YYYY-MM-DD)

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    conn = get_db_connection()
    try:
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = %s AND time_frame = %s
        """
        params = [symbol, time_frame]

        if from_date:
            query += " AND timestamp >= %s"
            params.append(from_date)
        elif days:
            # API 엔진과 동일: midnight 기준 (당일 자정 - N일)
            end_ref = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_ref - timedelta(days=days)
            query += " AND timestamp >= %s"
            params.append(start_date)

        if to_date:
            query += " AND timestamp <= %s"
            params.append(to_date)

        query += " ORDER BY timestamp ASC"

        df = pd.read_sql(query, conn, params=params)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    finally:
        conn.close()


def aggregate_candles(df: pd.DataFrame, target_interval: str) -> pd.DataFrame:
    """
    1m 캔들을 상위 인터벌로 집계한다.
    기존 BacktestEngine의 _aggregate_candles와 동일한 로직.

    Args:
        df: 1m OHLCV DataFrame
        target_interval: "3m", "5m", "15m", "30m", "1h", "4h", "1d"

    Returns:
        Aggregated DataFrame
    """
    if df.empty:
        return df

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    if target_interval == "1d":
        return _aggregate_to_daily(df)

    # Parse interval to minutes
    minutes = _interval_to_minutes(target_interval)
    if minutes <= 0:
        return df

    # Align to grid
    df["bucket"] = df["timestamp"].apply(
        lambda dt: dt.replace(
            minute=(dt.minute // minutes) * minutes, second=0, microsecond=0
        )
        if minutes < 60
        else dt.replace(
            hour=(dt.hour // (minutes // 60)) * (minutes // 60),
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    agg = (
        df.groupby("bucket")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    agg = agg.rename(columns={"bucket": "timestamp"})
    return agg


def _aggregate_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """1m 캔들을 일봉으로 집계 (날짜 기준)."""
    df = df.copy()
    df["date"] = df["timestamp"].dt.date

    agg = (
        df.groupby("date")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    agg["timestamp"] = pd.to_datetime(agg["date"])
    agg = agg.drop(columns=["date"])
    return agg


def _interval_to_minutes(interval: str) -> int:
    """인터벌 문자열을 분 단위로 변환."""
    mapping = {
        "1m": 1, "3m": 3, "5m": 5, "10m": 10,
        "15m": 15, "30m": 30, "60m": 60, "1h": 60,
        "4h": 240, "8h": 480, "12h": 720,
    }
    return mapping.get(interval, 0)


def load_ohlcv(
    symbol: str,
    interval: str = "1d",
    days: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    OHLCV 데이터를 로드하고 필요시 집계한다.
    기존 BacktestEngine과 동일한 데이터를 반환.

    Args:
        symbol: 종목 코드
        interval: 캔들 인터벌 ("1m", "5m", "1h", "1d" 등)
        days: 최근 N일
        from_date: 시작일
        to_date: 종료일

    Returns:
        DataFrame with: timestamp, open, high, low, close, volume
    """
    if interval == "1m":
        return load_ohlcv_raw(symbol, "1m", days=days, from_date=from_date, to_date=to_date)

    # DB에는 1m만 저장 → 집계 필요
    # 상위 인터벌은 더 많은 1m 데이터가 필요
    extra_days = 5 if days else 0
    raw = load_ohlcv_raw(
        symbol, "1m",
        days=(days + extra_days) if days else None,
        from_date=from_date,
        to_date=to_date,
    )

    if raw.empty:
        print(f"Warning: No 1m data found for {symbol}")
        return raw

    aggregated = aggregate_candles(raw, interval)

    # days 필터 적용 (집계 후, API 동일 midnight 기준)
    if days and not aggregated.empty:
        end_ref = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = end_ref - timedelta(days=days)
        aggregated = aggregated[aggregated["timestamp"] >= cutoff].reset_index(drop=True)

    return aggregated


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load OHLCV data from PostgreSQL")
    parser.add_argument("symbol", help="Symbol (e.g., 005930, BTCUSDT)")
    parser.add_argument("--interval", default="1d", help="Candle interval (default: 1d)")
    parser.add_argument("--days", type=int, default=30, help="Days of data (default: 30)")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")

    args = parser.parse_args()
    df = load_ohlcv(args.symbol, args.interval, args.days, args.from_date, args.to_date)
    print(f"Loaded {len(df)} candles for {args.symbol} ({args.interval})")
    if not df.empty:
        print(f"  Period: {df['timestamp'].iloc[0]} ~ {df['timestamp'].iloc[-1]}")
        print(df.tail(5).to_string(index=False))
