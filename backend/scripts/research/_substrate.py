#!/usr/bin/env python3
"""연구 substrate 공용 로더 — 가격은 **DB 만** 읽는다.

왜 이 모듈이 존재하는가 (2026-08-09):
  3군 R-1 스크립트들이 `runs/ohlcv_cache/{sym}_1m.joblib` 를 읽어 왔는데 이
  캐시가 14종목 / 2026-05-12 종료로 **89일간 정지**해 있었다. 같은 DB 의
  `ohlcv` 테이블은 214종목 / 오늘까지 살아 있다. `binance-joblib-refresh` cron
  은 microstructure(OI/LSR/taker) 만 갱신하고 가격 캐시는 손대지 않는다.

  결과는 판정 오염이었다. tier3_gate G1 의 `recent_edge`·`decay_ratio` 는
  최신성에 100% 의존하는데 "최근 1/3" 이 실제로는 2026-03~05 였다. 신호는
  최신인데 가격이 없어 트리거가 조용히 버려졌고(`price.get()` → None →
  continue), paradigm 251 은 그 때문에 GRAVEYARD 처리됐다가 재판정에서
  decay_ratio 0.138 → 0.481 로 뒤집혔다.

  같은 결함이 두 번째다 — live/paper 쪽은 2026-07-11 에 고쳤으나(vb 127/128
  substrate stall) 연구 쪽 저장소는 손대지 않았다. 그래서 저장소를 하나로
  합치고, 최신성을 **로더가 직접 검사**한다. "모르니까 통과" 를 없애는 것이
  tier3_redesign 의 원칙이고, 그 원칙을 데이터 입구에도 적용한다.

원칙
  1. 가격은 DB `ohlcv` 만. joblib 캐시 사용 금지.
  2. 로더가 최신성을 검사한다 — 기본 7일. 초과하면 SubstrateStale 예외.
  3. 조용한 결손 금지 — 트리거가 가격 없어 버려지면 세지고 보고한다.

사용
    from scripts.research._substrate import (
        daily_ohlcv, daily_ohlcv_many, universe_symbols, assert_fresh,
    )
    px = daily_ohlcv(db, "BNBUSDT")            # 최신성 검사 포함
    book = daily_ohlcv_many(db, ["BNBUSDT", "XRPUSDT"])
    syms = universe_symbols(db, min_days=400, min_median_quote_vol=5_000_000)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import text

# 가격 substrate 가 오늘로부터 이만큼 이상 낡으면 차단한다.
MAX_STALENESS_DAYS = 7
TIME_FRAME = "1m"


class SubstrateStale(RuntimeError):
    """substrate 가 낡았다. 판정을 진행하면 위조 결과가 나온다."""


@dataclass
class Coverage:
    symbol: str
    start: date
    end: date
    days: int
    median_quote_vol_usd: float

    @property
    def staleness_days(self) -> int:
        return (datetime.utcnow().date() - self.end).days


def assert_fresh(end: date, label: str = "", max_days: int = MAX_STALENESS_DAYS) -> None:
    """substrate 종료일이 허용 범위 안인지 확인한다. 낡으면 예외."""
    stale = (datetime.utcnow().date() - end).days
    if stale > max_days:
        raise SubstrateStale(
            f"{label or 'substrate'} 가 {stale}일 낡았다 (종료 {end}, 허용 {max_days}일). "
            f"판정을 중단한다 — recent_edge/decay_ratio 가 위조된다."
        )


def _rollup(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "quote_vol"])
    df = pd.DataFrame(rows, columns=["d", "open", "high", "low", "close", "quote_vol"])
    for c in ("open", "high", "low", "close", "quote_vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["d"] = pd.to_datetime(df["d"])
    return df.dropna(subset=["open", "close"]).set_index("d").sort_index()


_DAILY_ONE = """
WITH b AS (
  SELECT timestamp::date AS d, min(timestamp) AS t0, max(timestamp) AS t1,
         max(high) AS high, min(low) AS low, sum(close*volume) AS quote_vol
  FROM ohlcv WHERE symbol=:s AND time_frame=:tf
  GROUP BY timestamp::date
)
SELECT b.d, o.open, b.high, b.low, c.close, b.quote_vol
FROM b
JOIN ohlcv o ON o.symbol=:s AND o.time_frame=:tf AND o.timestamp=b.t0
JOIN ohlcv c ON c.symbol=:s AND c.time_frame=:tf AND c.timestamp=b.t1
ORDER BY b.d
"""


def daily_ohlcv(db, symbol: str, check_fresh: bool = True,
                max_staleness_days: int = MAX_STALENESS_DAYS) -> pd.DataFrame:
    """일봉(UTC) — 시가=당일 첫 1m 시가, 종가=마지막 1m 종가.

    반환 컬럼: open / high / low / close / quote_vol (index=일자)
    """
    rows = db.execute(text(_DAILY_ONE), {"s": symbol, "tf": TIME_FRAME}).fetchall()
    df = _rollup(rows)
    if check_fresh and not df.empty:
        assert_fresh(df.index.max().date(), f"{symbol} 일봉", max_staleness_days)
    return df


def daily_ohlcv_many(db, symbols: list[str], check_fresh: bool = True,
                     max_staleness_days: int = MAX_STALENESS_DAYS) -> dict:
    out = {}
    for s in symbols:
        df = daily_ohlcv(db, s, check_fresh=check_fresh,
                         max_staleness_days=max_staleness_days)
        if not df.empty:
            out[s] = df
    return out


_COVERAGE = """
SELECT symbol, min(timestamp)::date AS start, max(timestamp)::date AS end,
       count(DISTINCT timestamp::date) AS days
FROM ohlcv WHERE time_frame=:tf
GROUP BY symbol
"""

_LIQUIDITY = """
SELECT symbol, percentile_cont(0.5) WITHIN GROUP (ORDER BY qv) AS med_qv
FROM (
  SELECT symbol, timestamp::date AS d, sum(close*volume) AS qv
  FROM ohlcv WHERE time_frame=:tf GROUP BY symbol, timestamp::date
) t GROUP BY symbol
"""


def coverage(db) -> dict:
    """종목별 커버리지 + 유동성. 유니버스 구성과 최신성 감사에 쓴다."""
    cov = {r.symbol: r for r in db.execute(text(_COVERAGE), {"tf": TIME_FRAME})}
    liq = {r.symbol: float(r.med_qv or 0.0)
           for r in db.execute(text(_LIQUIDITY), {"tf": TIME_FRAME})}
    return {s: Coverage(symbol=s, start=r.start, end=r.end, days=int(r.days),
                        median_quote_vol_usd=liq.get(s, 0.0))
            for s, r in cov.items()}


def universe_symbols(db, min_days: int = 0, min_median_quote_vol: float = 0.0,
                     max_staleness_days: int = MAX_STALENESS_DAYS) -> list[str]:
    """조건을 만족하는 종목 목록.

    Lesson #78 — 자동구성 유니버스는 유동성 필터가 필수다. 실측으로 필터 유무가
    부호를 뒤집은 사례가 있으므로 `min_median_quote_vol` 을 반드시 넘겨라.
    """
    out = []
    for s, c in coverage(db).items():
        if c.days < min_days:
            continue
        if c.median_quote_vol_usd < min_median_quote_vol:
            continue
        if c.staleness_days > max_staleness_days:
            continue
        out.append(s)
    return sorted(out)
