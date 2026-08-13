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


def _fix_paper_trade_key(conn) -> None:
    """paper_trade 자연키를 row_idx 로 교정 (2026-08-13).

    처음엔 (session_id, entry_ts, exit_ts, side) 를 유일키로 잡았는데, 적재가
    UNIQUE 위반으로 통째로 실패했다 — 한 세션에 **진입·청산 시각이 완전히 같은
    거래가 2건** 있었다(같은 바 왕복 2회). 시각·방향만으로는 거래를 구분할 수 없다.

    ⚠ 여기서 DROP 하는 것은 **제약 조건**이지 테이블·데이터가 아니다. 이 테이블은
      같은 날 만들어졌고 이 시점에 0행이다(확인 후 진행).
    """
    cols = {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='paper_trade'"))}
    if "row_idx" not in cols:
        n = conn.execute(text("SELECT count(*) FROM paper_trade")).scalar()
        if n:
            raise SystemExit(
                f"paper_trade 에 {n}행이 있다 — row_idx 를 NOT NULL 로 추가할 수 없다. "
                "수동 확인 필요.")
        conn.execute(text("ALTER TABLE paper_trade ADD COLUMN row_idx INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE paper_trade ALTER COLUMN row_idx DROP DEFAULT"))
        print("  + paper_trade.row_idx 추가")
    cons = {r[0] for r in conn.execute(text(
        "SELECT constraint_name FROM information_schema.table_constraints "
        "WHERE table_name='paper_trade' AND constraint_type='UNIQUE'"))}
    if "uq_paper_trade_natural" in cons:
        conn.execute(text("ALTER TABLE paper_trade DROP CONSTRAINT uq_paper_trade_natural"))
        print("  - 옛 유일키(uq_paper_trade_natural) 제거")
    if "uq_paper_trade_session_row" not in cons:
        conn.execute(text("ALTER TABLE paper_trade ADD CONSTRAINT "
                          "uq_paper_trade_session_row UNIQUE (session_id, row_idx)"))
        print("  + 새 유일키(session_id, row_idx) 추가")
    conn.commit()


def migrate() -> int:
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    todo = [t for t in TABLES if t not in existing]
    if not todo:
        print("모든 테이블이 이미 존재한다 — 스키마 교정만 확인")
        with engine.connect() as conn:
            _fix_paper_trade_key(conn)
        return verify()

    print(f"생성 대상: {todo}")
    # 대상 테이블만 생성한다. checkfirst=True 라 기존 테이블은 건드리지 않는다.
    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables[t] for t in todo],
        checkfirst=True,
    )
    with engine.connect() as conn:
        _fix_paper_trade_key(conn)
    print("생성 완료\n검증:")
    return verify()


if __name__ == "__main__":
    if "--verify" in sys.argv:
        sys.exit(verify())
    sys.exit(migrate())
