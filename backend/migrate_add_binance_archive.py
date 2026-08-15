"""바이낸스 공개 아카이브 집계 테이블 생성 (2026-08-15).

수집: `scripts/collect_binance_archive.py`
출처: `data.binance.vision` — 공식·무료·키 불필요

⚠ 이 데이터가 처음부터 있었다
    같은 날 오전에 "OI 는 4개월뿐이라 표본 밖 검증 불가", "호가는 6개월 기다려야
    한다"며 두 축을 닫았다. 둘 다 틀렸다 — 아카이브에 OI 는 **2020-09부터
    6년치**, 호가 깊이는 **2023-01부터 3.6년치**가 무료로 있었다.
    자체 수집기를 만들기 전에 **공개 아카이브부터 확인**하는 것이 순서다.

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** CREATE 만 한다. 멱등.

사용:
  python3 migrate_add_binance_archive.py
  python3 migrate_add_binance_archive.py --verify
"""
from __future__ import annotations

import sys

from sqlalchemy import (
    Column, Date, DateTime, Float, Index, Integer, String, UniqueConstraint,
    inspect, text,
)
from datetime import datetime

from app.db.base import Base
from app.db.session import engine


class BinanceArchiveMetrics(Base):
    """OI·포지셔닝 일별 집계 (원본 5분 간격).

    `toptrader_ls_*` 가 특히 값지다 — **상위 트레이더의 롱숏 비율**이고
    우리가 한 번도 제대로 못 써본 축이다.
    """

    __tablename__ = "binance_archive_metrics"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    n_samples = Column(Integer, nullable=True)
    oi_med = Column(Float, nullable=True)
    oi_last = Column(Float, nullable=True)
    oi_value_med = Column(Float, nullable=True)
    oi_range_pct = Column(Float, nullable=True)          # 하루 OI 변동폭
    toptrader_ls_med = Column(Float, nullable=True)      # 상위 트레이더 포지션 비율
    toptrader_ls_cnt_med = Column(Float, nullable=True)  # 상위 트레이더 계정 비율
    long_short_ratio_med = Column(Float, nullable=True)  # 전체 계정 비율
    taker_ls_med = Column(Float, nullable=True)          # 테이커 매수/매도 거래량

    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_bam_symbol_date"),
        Index("ix_bam_symbol_date", "symbol", "date"),
    )


class BinanceArchiveDepth(Base):
    """호가 깊이 일별 집계 (원본 1분 간격 × ±1~5% 구간).

    ±1% 구간 명목이 **실제로 밀어넣을 수 있는 크기**에 가장 가깝다.
    최우선호가 스프레드보다 우리 계좌 규모에 직결된다.
    """

    __tablename__ = "binance_archive_depth"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    n_samples = Column(Integer, nullable=True)
    depth1_bid_usd = Column(Float, nullable=True)
    depth1_ask_usd = Column(Float, nullable=True)
    depth1_usd = Column(Float, nullable=True)
    depth5_bid_usd = Column(Float, nullable=True)
    depth5_ask_usd = Column(Float, nullable=True)
    depth1_imbalance = Column(Float, nullable=True)      # (매수-매도)/(매수+매도)
    depth1_bid_cv = Column(Float, nullable=True)         # 깊이 변동계수

    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_bad_symbol_date"),
        Index("ix_bad_symbol_date", "symbol", "date"),
    )


TABLES = ["binance_archive_metrics", "binance_archive_depth"]


def verify() -> int:
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    ok = True
    for t in TABLES:
        if t not in existing:
            print(f"  ✗ {t} 없음")
            ok = False
            continue
        cols = [c["name"] for c in insp.get_columns(t)]
        with engine.connect() as c:
            n, s = c.execute(text(
                f"SELECT count(*), count(distinct symbol) FROM {t}")).one()
        print(f"  ✓ {t:<28} 컬럼 {len(cols):>2} · {n:>9,}행 · 종목 {s}")
    return 0 if ok else 1


def migrate() -> int:
    insp = inspect(engine)
    todo = [t for t in TABLES if t not in set(insp.get_table_names())]
    if not todo:
        print("모든 테이블이 이미 존재 — 건너뜀")
        return verify()
    print(f"생성 대상: {todo}")
    Base.metadata.create_all(
        bind=engine, tables=[Base.metadata.tables[t] for t in todo],
        checkfirst=True)
    print("생성 완료\n검증:")
    return verify()


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else migrate())
