"""1군/2군 결과 저장소 테이블 생성 (2026-08-13).

설계: `.claude/plans/tier1_result_store_schema.md`
모델: `app/models/tier_result.py`

원칙 (`.claude/references/protocols.md`)
  · **DROP/RESET 절대 금지.** 이 스크립트는 CREATE 만 한다.
  · **멱등** — 이미 있으면 건너뛴다. 몇 번 돌려도 안전하다.
  · 실행 전 `pg_dump` 백업. 아래 사용법 참조.

이 테이블들은 **읽기 모델**이다. 정본 엔진은 계속 파일에 쓰고, 적재 잡이
파일 → DB 로 옮긴다. 엔진이 DB 에 의존하지 않으므로 **실자금 경로에 실패 모드를
추가하지 않는다.**

사용:
  # 1) 백업 (필수)
  pg_dump -h localhost -U antigravity_user antigravity_db \
      > backups/db_backup_$(date +%Y%m%d_%H%M%S).sql
  # 2) 생성
  python3 migrate_add_tier1_result_store.py
  # 3) 검증
  python3 migrate_add_tier1_result_store.py --verify
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import engine

# 모델을 import 해야 Base.metadata 에 등록된다
from app.models.tier_result import (  # noqa: F401
    EngineGateRun, PaperTrade, ResearchResult, Tier1LayerObservation,
)

TABLES = ["paper_trade", "research_result", "tier1_layer_observation",
          "engine_gate_run"]


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
        idx = [i["name"] for i in insp.get_indexes(t)]
        with engine.connect() as c:
            n = c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        print(f"  ✓ {t:<28} 컬럼 {len(cols):>2} · 인덱스 {len(idx):>2} · {n:>7}행")
    return 0 if ok else 1


def migrate() -> int:
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    todo = [t for t in TABLES if t not in existing]
    if not todo:
        print("모든 테이블이 이미 존재한다 — 할 일 없음")
        return verify()

    print(f"생성 대상: {todo}")
    # 대상 테이블만 생성한다. checkfirst=True 라 기존 테이블은 건드리지 않는다.
    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables[t] for t in todo],
        checkfirst=True,
    )
    print("생성 완료\n검증:")
    return verify()


if __name__ == "__main__":
    if "--verify" in sys.argv:
        sys.exit(verify())
    sys.exit(migrate())
