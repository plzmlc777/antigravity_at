"""온체인 지표 테이블 생성 (2026-08-15).

모델: `app/models/onchain_metric.py`
수집: `scripts/collect_onchain.py`

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** CREATE 만 한다.
  · **멱등** — 이미 있으면 건너뛴다.
  · 기존 테이블을 건드리지 않으므로 pg_dump 는 생략한다(`ohlcv` 가 45GB 라
    전체 백업이 디스크를 채울 위험이 더 크다 — 2026-08-13 전례).

사용:
  python3 migrate_add_onchain_metric.py
  python3 migrate_add_onchain_metric.py --verify
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from app.models.onchain_metric import OnchainMetric  # noqa: F401

TABLE = "onchain_metric"


def verify() -> int:
    insp = inspect(engine)
    if TABLE not in set(insp.get_table_names()):
        print(f"  ✗ {TABLE} 없음")
        return 1
    cols = [c["name"] for c in insp.get_columns(TABLE)]
    with engine.connect() as c:
        n, s, d0, d1 = c.execute(text(
            f"SELECT count(*), count(distinct asset), min(date), max(date) "
            f"FROM {TABLE}")).one()
    print(f"  ✓ {TABLE} · 컬럼 {len(cols)} · {n:,}행 · 자산 {s} · {d0} ~ {d1}")
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
