#!/usr/bin/env python3
"""
us_rank_snapshot 테이블 생성 마이그레이션.

키움 미국주식 순위정보 API 는 조회 시점 스냅샷만 제공하고 과거 시계열이 없다.
고유 substrate(키움 거래상위 = 한국 개인 수급, 주간거래 괴리율 = Blue Ocean
세션 괴리)를 백테스트에 쓰려면 지금부터 매일 적재해야 한다.

멱등: 이미 있으면 아무것도 하지 않는다. DROP 없음.

실행: cd backend && python3 migrate_add_us_rank_snapshot.py
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402

TABLE = "us_rank_snapshot"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id             SERIAL PRIMARY KEY,
    business_date  DATE        NOT NULL,
    rank_type      VARCHAR     NOT NULL,
    api_id         VARCHAR     NOT NULL,
    rank           INTEGER,
    symbol         VARCHAR     NOT NULL,
    stex_tp        VARCHAR,
    name_kr        VARCHAR,
    price          DOUBLE PRECISION,
    change_pct     DOUBLE PRECISION,
    volume         BIGINT,
    trade_value    DOUBLE PRECISION,
    market_cap     DOUBLE PRECISION,
    extra          JSONB,
    collected_at   TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uix_us_rank_date_type_symbol UNIQUE (business_date, rank_type, symbol)
);
"""

INDEXES = [
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_business_date ON {TABLE} (business_date)",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_rank_type ON {TABLE} (rank_type)",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_symbol ON {TABLE} (symbol)",
    f"CREATE INDEX IF NOT EXISTS ix_us_rank_type_date ON {TABLE} (rank_type, business_date)",
]


def migrate() -> None:
    with engine.connect() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
        ), {"t": TABLE}).scalar()

        if exists:
            print(f"'{TABLE}' 이미 존재 — 인덱스만 확인")
        else:
            conn.execute(text(DDL))
            print(f"'{TABLE}' 생성 완료")

        for stmt in INDEXES:
            conn.execute(text(stmt))
        conn.commit()

        cols = conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :t ORDER BY ordinal_position"
        ), {"t": TABLE}).all()
        print(f"\n{TABLE} 컬럼 {len(cols)}개:")
        for name, dtype in cols:
            print(f"  {name:15} {dtype}")


if __name__ == "__main__":
    migrate()
