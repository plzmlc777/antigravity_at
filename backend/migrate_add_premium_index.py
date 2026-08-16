"""`binance_premium_index` 테이블 신설 — 일별 프리미엄(mark vs index).

멱등이다. `information_schema` 를 확인하고 없을 때만 만든다.

⚠ 프리미엄 정의는 **`(mark_close - index_close) / index_close`** 다.
   바이낸스가 직접 주는 `premiumIndexKlines` 는 impact bid/ask 기반의 **다른
   공식**이다(실측 -0.000383 vs -0.000412, 대략 7% 차이). 소비자
   `BinancePremiumIndexZScoreSource` 가 전자를 쓰므로 두 계열을 각각 저장하고
   프리미엄은 유도해 둔다 — 나중에 정의를 바꿔야 하면 원본이 남아 있어야 한다.

사용: python3 migrate_add_premium_index.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

from app.db.session import engine

DDL = [
    """CREATE TABLE IF NOT EXISTS binance_premium_index (
         id BIGSERIAL PRIMARY KEY,
         symbol VARCHAR(32) NOT NULL,
         date DATE NOT NULL,
         index_close DOUBLE PRECISION,
         mark_close DOUBLE PRECISION,
         premium DOUBLE PRECISION,
         built_at TIMESTAMP DEFAULT now()
       )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS binance_premium_index_sym_date_uniq
         ON binance_premium_index (symbol, date)""",
]


def main() -> int:
    with engine.connect() as c:
        exists = c.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='binance_premium_index'"
        )).scalar()
        if exists:
            n = c.execute(text("SELECT count(*) FROM binance_premium_index")).scalar()
            print(f"이미 존재 — {n:,}행. 아무 것도 하지 않는다.")
            return 0
        for stmt in DDL:
            c.execute(text(stmt))
        c.commit()
        print("binance_premium_index 생성 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
