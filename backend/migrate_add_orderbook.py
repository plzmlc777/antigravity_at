"""호가 스냅샷·일별 집계 테이블 생성 (2026-08-15).

모델: `app/models/orderbook_snapshot.py`
수집: `scripts/collect_orderbook.py`

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** CREATE 만 한다.
  · **멱등** — 이미 있으면 건너뛴다.
  · 기존 테이블을 건드리지 않는다.

사용:
  python3 migrate_add_orderbook.py
  python3 migrate_add_orderbook.py --verify
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine
from app.models.orderbook_snapshot import (  # noqa: F401
    OrderbookDaily, OrderbookSnapshot,
)

TABLES = ["orderbook_snapshot", "orderbook_daily"]


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
            n = c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        print(f"  ✓ {t:<22} 컬럼 {len(cols):>2} · {n:>10,}행")
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
