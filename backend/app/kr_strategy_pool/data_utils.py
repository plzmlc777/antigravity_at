"""
KR 백테스트용 데이터 유틸 — 1분봉 → 5분/15분/일봉 resample, 거래일 분할.

분봉 누락(거래량 0인 분봉이 ka10080에서 생략) 대응:
  - resample은 pandas의 OHLCV 표준 규칙 사용
  - 누락 분은 자연스럽게 5분/15분 봉에서 합산됨 → 별도 보간 불필요
  - 다만 "정규장 시작 09:00 ~ 마감 15:30" 범위 외 봉(15:35 동시호가)은
    별도 처리: keep_close_auction=True 옵션
"""
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text


def fetch_1m_feed(
    engine,
    symbol: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """DB에서 1분봉 fetch. timestamp는 ISO string으로 반환."""
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
                "volume": int(r[5]),
            }
        )
    return out


def resample_ohlcv(
    feed_1m: List[Dict[str, Any]],
    freq: str,
    keep_close_auction: bool = False,
) -> List[Dict[str, Any]]:
    """
    1분봉 → 임의 timeframe(5min, 15min, 30min, 60min, 1D)으로 resample.

    keep_close_auction:
      - False: 15:30 이후 봉(15:35 단일가) 제거.
      - True : 그대로 포함 (모든 봉 유지).
    """
    if not feed_1m:
        return []
    df = pd.DataFrame(feed_1m)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("ts")

    # 정규장 외(15:35 동시호가) 필터
    if not keep_close_auction:
        df = df.between_time("09:00", "15:30")

    if freq.upper() == "1D":
        # 일봉: 거래일 단위 그룹. timestamp는 09:00 시작 봉으로.
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
        # 분 단위 resample. 거래일 경계 넘지 않도록 origin='start_day'.
        out = (
            df.resample(freq, origin="start_day")
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
        # timestamp가 휴장시간에 만들어진 빈 빈 슬롯 제거 (between_time에서 필터됐어도
        # 5분 grid에 맞추다 보면 09:00 직전 등 None 값이 생길 수 있음 → dropna로 처리)

    out_records = []
    for _, r in out.iterrows():
        out_records.append(
            {
                "timestamp": r["ts"].isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["volume"]),
            }
        )
    return out_records


def split_train_test(
    feed: List[Dict[str, Any]], train_ratio: float = 0.6
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """봉 개수 기준 단순 split."""
    n = len(feed)
    cut = int(n * train_ratio)
    return feed[:cut], feed[cut:]


def walk_forward_windows(
    feed: List[Dict[str, Any]],
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
) -> List[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    """
    rolling walk-forward windows.
    step=None이면 test_size씩 전진(non-overlapping test set).
    """
    step = step or test_size
    windows = []
    i = 0
    while i + train_size + test_size <= len(feed):
        train = feed[i : i + train_size]
        test = feed[i + train_size : i + train_size + test_size]
        windows.append((train, test))
        i += step
    return windows
