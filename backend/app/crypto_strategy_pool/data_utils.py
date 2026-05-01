"""
Crypto 백테스트용 데이터 유틸 — Binance USDT-M 1분봉.

KR 버전과 차이:
  - 24/7 시장이라 between_time 필터 없음 (오전/오후/야간 모두 valid).
  - 1D resample은 calendar day 기준 (UTC). Binance 캔들 timestamp는 이미 UTC.
  - 거래일 분할 개념 없음 (연속 시장).
"""
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text


def fetch_1m_feed(
    engine,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """DB ohlcv 테이블에서 1m feed fetch. timestamp는 ISO string으로 반환."""
    q = """
    SELECT timestamp, open, high, low, close, volume
    FROM ohlcv WHERE symbol=:s AND time_frame='1m'
    """
    params = {"s": symbol}
    if start_date:
        q += " AND timestamp >= :start"
        params["start"] = start_date
    if end_date:
        q += " AND timestamp <= :end"
        params["end"] = end_date
    q += " ORDER BY timestamp"

    with engine.connect() as conn:
        rows = conn.execute(text(q), params).fetchall()
    out = []
    for r in rows:
        ts = r[0]
        out.append(
            {
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),  # crypto는 float 거래량 (BTC 단위 등)
            }
        )
    return out


def resample_ohlcv(
    feed_1m: List[Dict[str, Any]],
    freq: str,
) -> List[Dict[str, Any]]:
    """
    1m → 5min/15min/30min/60min/1D resample. 24/7 — 휴장 필터 없음.
    """
    if not feed_1m:
        return []
    df = pd.DataFrame(feed_1m)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("ts")

    if freq.upper() == "1D":
        df["d"] = df.index.normalize()
        out = (
            df.groupby("d")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .reset_index()
            .rename(columns={"d": "ts"})
        )
    else:
        out = (
            df.resample(freq)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna(subset=["open"])
            .reset_index()
            .rename(columns={"ts": "ts"})
        )

    out_records = []
    for _, r in out.iterrows():
        out_records.append(
            {
                "timestamp": r["ts"].isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r["volume"]),
            }
        )
    return out_records


def split_train_test(
    feed: List[Dict[str, Any]], train_ratio: float = 0.6
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    n = len(feed)
    cut = int(n * train_ratio)
    return feed[:cut], feed[cut:]


def walk_forward_windows(
    feed: List[Dict[str, Any]],
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
) -> List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    step = step or test_size
    windows = []
    i = 0
    while i + train_size + test_size <= len(feed):
        train = feed[i : i + train_size]
        test = feed[i + train_size : i + train_size + test_size]
        windows.append((train, test))
        i += step
    return windows
