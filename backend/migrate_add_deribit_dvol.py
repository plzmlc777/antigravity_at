"""Deribit DVOL(내재변동성 지수) 일별 테이블 (2026-08-15).

왜 이 기질인가
    지금까지 쓴 기질은 전부 **현물·선물 파생**이었다 — OHLCV, 펀딩, OI,
    호가 깊이, 온체인, 포지셔닝. 전부 **과거를 요약한 값**이다.
    옵션은 다르다: **미래 변동성에 대한 가격**이고 **참여자 집단이 다르다**.

    VRP(변동성 위험 프리미엄) = 내재변동성 - 실현변동성
    금융 전체에서 가장 견고한 이상현상 중 하나다. 그리고 예측이 아니라
    **위험을 떠안는 대가**라 우리가 아홉 번 실패한 것과 종류가 다르다.
    (같은 계열: [[project-funding-carry-paradigm]] — 우리 유일한 R-5 시드)

⚠ 직접 수확은 못 한다
    VRP 를 직접 먹으려면 **옵션을 팔아야** 한다. $720 계좌로 무한 꼬리위험을
    지는 건 안 된다. 그래서 **국면 조건 신호**로 쓴다 — BTC·ETH 옵션이 보는
    미래로 알트 유니버스 거래를 조건화한다.

출처: `www.deribit.com/api/v2/public/get_volatility_index_data`
      **키 불필요 · 무료 · 5.4년**(2021-03-24~). 옵션은 BTC·ETH 만 있다.

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** CREATE 만 한다. 멱등.

사용:
  python3 migrate_add_deribit_dvol.py
  python3 migrate_add_deribit_dvol.py --verify
"""
from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import (
    Column, Date, DateTime, Float, Index, Integer, String, UniqueConstraint,
    inspect, text,
)

from app.db.base import Base
from app.db.session import engine


class DeribitDvol(Base):
    """DVOL — Deribit 내재변동성 지수 (BTC·ETH, 일별 OHLC)."""

    __tablename__ = "deribit_dvol"

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(String, nullable=False, index=True)   # BTC / ETH
    date = Column(Date, nullable=False, index=True)

    dvol_open = Column(Float, nullable=True)
    dvol_high = Column(Float, nullable=True)
    dvol_low = Column(Float, nullable=True)
    dvol_close = Column(Float, nullable=True)

    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("currency", "date", name="uq_dvol_cur_date"),
        Index("ix_dvol_cur_date", "currency", "date"),
    )


TABLES = ["deribit_dvol"]


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
                f"SELECT count(*), count(distinct currency) FROM {t}")).one()
        print(f"  ✓ {t:<20} 컬럼 {len(cols):>2} · {n:>7,}행 · 통화 {s}")
    return 0 if ok else 1


def migrate() -> int:
    insp = inspect(engine)
    todo = [t for t in TABLES if t not in set(insp.get_table_names())]
    if not todo:
        print("이미 존재 — 건너뜀")
        return verify()
    print(f"생성 대상: {todo}")
    Base.metadata.create_all(
        bind=engine, tables=[Base.metadata.tables[t] for t in todo],
        checkfirst=True)
    print("생성 완료\n검증:")
    return verify()


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else migrate())
