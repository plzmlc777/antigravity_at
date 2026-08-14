"""숏 규약 결함으로 무효가 된 `research_result` 행에 표시 (2026-08-14).

무엇이 잘못됐나
    숏 수익률을 `진입/청산 − 1` 로 쟀다. 이 값은 **상한이 없다** — 90% 폭락한
    코인을 숏 치면 +900% 로 기록되지만 실제로는 명목의 90% 를 번 것이라 +90% 가
    최대다. 커널 `close()` 는 처음부터 `(진입−청산)/진입` 이었다.

    · 251 코호트: 평균 43.41% → **5.15%**, t 5.73 → **1.74**
    · x_sizing 시뮬: 부풀린 수익률로 **복리를 돌렸다**(계산 결함)

⚠ 행을 지우지 않는다
    지우면 "그때 우리가 무엇을 믿고 있었는가"가 사라진다. 그 수치로 내린 판단이
    기록에 남아 있는데 근거만 없어지면 나중에 재구성할 수 없다. 대신 `params` 에
    표시를 달아 조회에서 걸러낼 수 있게 한다.

    스키마 변경도 하지 않는다 — `params` 는 이미 JSONB 다.

사용:
  python3 -m scripts.supersede_research_rows --dry
  python3 -m scripts.supersede_research_rows
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.tier_result import ResearchResult  # noqa: E402

# 역비율 규약으로 산출된 파일들
BAD_SOURCES = [
    "runs/research_track/lifecycle_variant_backtest.json",
    "runs/research_track/lifecycle_phase/variant_x_sizing__metrics.json",
]
REASON = ("short_return_convention_inverse_ratio: 숏 수익률을 진입/청산-1 로 계산해 "
          "이익 거래가 부풀려졌다. 커널 규약 (진입-청산)/진입 로 재산출함 (2026-08-14)")


def main() -> int:
    ap = argparse.ArgumentParser(description="규약 결함 행 무효 표시")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--cutoff", default="2026-08-14",
                    help="이 날짜 **이전** 생성분만 표시 (재산출분은 건드리지 않는다)")
    a = ap.parse_args()

    db = SessionLocal()
    try:
        from datetime import datetime
        cutoff = datetime.fromisoformat(a.cutoff)
        rows = (db.query(ResearchResult)
                .filter(ResearchResult.source_file.in_(BAD_SOURCES),
                        ResearchResult.created_at < cutoff).all())
        print(f"대상 {len(rows)}행 (생성 < {a.cutoff})")
        n = 0
        for r in rows:
            p = dict(r.params or {})
            if p.get("superseded"):
                continue
            p["superseded"] = True
            p["superseded_reason"] = REASON
            n += 1
            print(f"  {r.id:>4} {r.kind}/{r.strategy}/{r.variant} "
                  f"({str(r.created_at)[:16]})")
            if not a.dry:
                r.params = p
                flag_modified(r, "params")   # JSONB 는 제자리 변경을 감지 못 한다
        if not a.dry:
            db.commit()
        print(f"{'[DRY] ' if a.dry else ''}표시 {n}행")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
