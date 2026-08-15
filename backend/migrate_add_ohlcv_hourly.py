"""시간봉 캐시 `ohlcv_hourly` (2026-08-15).

왜 필요한가 — 일봉에서는 손절이 조용히 사라진다
    커널은 미래참조를 피하려고 **진입 바에서 손절·익절을 보지 않는다**(옳다).
    그런데 그 바의 상승폭이 손절보다 크면 **그 손절은 존재하지 않는다.**

    실측(상장 60건 · `lifecycle_resolution_study`):
        진입 바 상승폭   일봉 p50 **32.7%**  /  1h p50 **3.8%**
        손절 20% 무력화  일봉 **60.0%**      /  1h **3.3%**

    즉 지금 실거래에 넣은 손절 20% 조차 일봉 harness 에서는 60% 가 기록되지
    않는다. 1h 로 내려야 그 구간을 **처음으로 측정할 수 있다.**

⚠ `ohlcv`(1분봉, 45GB) 에 넣지 않는다
    거기 넣으면 45GB 테이블이 더 커지고 스캔이 느려진다. `ohlcv_daily` 와
    같은 **읽기 모델**로 따로 둔다. 원본에서 유도 가능하므로 지워도 정보가
    사라지지 않는다.

⚠ 원본 우선 규약도 같다
    아카이브에서 넣은 행과 1분봉에서 유도한 행이 섞일 수 있다. 수집기는
    `ON CONFLICT DO NOTHING` 으로 **기존 행을 덮지 않는다**.

출처: data.binance.vision/data/futures/um/{monthly,daily}/klines/<SYM>/1h/
      무료 · 키 불필요

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** CREATE 만 한다. 멱등.

사용:
  python3 migrate_add_ohlcv_hourly.py
  python3 migrate_add_ohlcv_hourly.py --verify
"""
from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, Index, Integer, String, UniqueConstraint,
    inspect, text,
)

from app.db.base import Base
from app.db.session import engine


class OhlcvHourly(Base):
    """시간봉 — UTC 정시 경계. 바이낸스 kline 과 같다."""

    __tablename__ = "ohlcv_hourly"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    ts = Column(DateTime, nullable=False, index=True)      # 봉 시작 시각(UTC)

    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    built_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "ts", name="uq_ohlcv_hourly_symbol_ts"),
        Index("ix_ohlcv_hourly_symbol_ts", "symbol", "ts"),
    )


TABLES = ["ohlcv_hourly"]


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
        print(f"  ✓ {t:<16} 컬럼 {len(cols):>2} · {n:>9,}행 · 종목 {s}")
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
