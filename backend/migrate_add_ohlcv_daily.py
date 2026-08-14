"""일봉 캐시 테이블 생성 (2026-08-14).

모델: `app/models/ohlcv_daily.py`
적재: `scripts/build_ohlcv_daily.py`

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** 이 스크립트는 CREATE 만 한다.
  · **멱등** — 이미 있으면 건너뛴다.
  · `ohlcv` 는 **읽기만** 한다. 원본은 손대지 않는다.

백업이 필요한가
    이 마이그레이션은 새 테이블 하나를 만들 뿐 기존 데이터를 건드리지 않는다.
    `ohlcv` 가 45GB 라 pg_dump 는 디스크를 채울 위험이 더 크다(2026-08-13 에
    19GB 까지 갔다가 중단한 전례). 스키마 백업만 남긴다.

사용:
  python3 migrate_add_ohlcv_daily.py
  python3 migrate_add_ohlcv_daily.py --verify
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from app.models.ohlcv_daily import OhlcvDaily  # noqa: F401

TABLE = "ohlcv_daily"


def verify() -> int:
    insp = inspect(engine)
    if TABLE not in set(insp.get_table_names()):
        print(f"  ✗ {TABLE} 없음")
        return 1
    cols = [c["name"] for c in insp.get_columns(TABLE)]
    idx = [i["name"] for i in insp.get_indexes(TABLE)]
    with engine.connect() as c:
        n = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
        syms = c.execute(text(f"SELECT count(distinct symbol) FROM {TABLE}")).scalar()
        rng = c.execute(text(f"SELECT min(date), max(date) FROM {TABLE}")).one()
    print(f"  ✓ {TABLE} · 컬럼 {len(cols)} · 인덱스 {len(idx)} · {n:,}행 · "
          f"종목 {syms} · {rng[0]} ~ {rng[1]}")
    return 0


def migrate() -> int:
    insp = inspect(engine)
    if TABLE in set(insp.get_table_names()):
        print(f"{TABLE} 이미 존재 — 건너뜀")
        return verify()
    print(f"생성: {TABLE}")
    Base.metadata.create_all(bind=engine,
                             tables=[Base.metadata.tables[TABLE]],
                             checkfirst=True)
    print("생성 완료\n검증:")
    return verify()


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else migrate())
