"""정본(Canon) 관문 실행 기록 → DB.

왜
    관문 결과가 `/tmp` 로그뿐이라 재부팅하면 사라진다. **"관문이 언제 주문을
    막았는가"** 는 사후 감사에서 가장 먼저 묻는 질문인데 답할 방법이 없었다.

⚠ 이 스크립트는 **관문 판정을 바꾸지 않는다**
    관문은 주문 앞에 선다. DB 쓰기가 실패했다고 주문을 막거나 통과시키면
    안 된다. 호출부는 `|| true` 로 부르고, 여기서도 예외를 삼켜 항상 0 으로
    끝난다. 기록은 부수 효과일 뿐이다.

값의 출처
    셸이 이미 뽑아 둔 요약을 인자로 받는다. 로그를 다시 파싱하지 않는다 —
    파싱이 두 곳에 있으면 갈린다(오늘 하루에만 같은 병으로 세 번 물렸다).

사용:
  python3 -m scripts.record_gate_run --mode fast --verdict pass \
      --unit 58/58 --golden 67/0 --context cycle
  python3 -m scripts.record_gate_run --mode full --verdict fail \
      --unit 88/88 --golden 110/2 --parity 136/0/18 --context cycle
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _pair(s: str, n: int) -> list[int | None]:
    """'67/0' → [67, 0].  값이 없거나 깨졌으면 None 으로 채운다."""
    if not s:
        return [None] * n
    parts = s.split("/")
    out: list[int | None] = []
    for i in range(n):
        try:
            out.append(int(parts[i]))
        except (IndexError, ValueError):
            out.append(None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="정본 관문 실행 기록")
    ap.add_argument("--mode", default="fast", choices=["fast", "full"])
    ap.add_argument("--verdict", required=True, choices=["pass", "fail"])
    ap.add_argument("--unit", default="", help="통과/전체 (예: 88/88)")
    ap.add_argument("--golden", default="", help="일치/불일치 (예: 67/0)")
    ap.add_argument("--parity", default="", help="PASS/FAIL/SKIP (예: 136/0/18)")
    ap.add_argument("--context", default="manual", choices=["cycle", "manual"],
                    help="cycle = 거래 사이클 중. 실패 시 주문이 실제로 막힌다")
    ap.add_argument("--detail", default="", help="불일치 요약 등 자유 텍스트")
    a = ap.parse_args()

    try:
        from app.db.session import SessionLocal
        from app.models.tier_result import EngineGateRun

        up, ut = _pair(a.unit, 2)
        gm, gx = _pair(a.golden, 2)
        pp, pf, ps = _pair(a.parity, 3)
        # 주문이 **실제로** 막혔는가. 수동 실행은 막을 주문이 없다.
        blocked = (a.verdict == "fail" and a.context == "cycle")

        db = SessionLocal()
        try:
            db.add(EngineGateRun(
                mode=a.mode, verdict=a.verdict,
                unit_passed=up, unit_total=ut,
                golden_matched=gm, golden_mismatched=gx,
                parity_pass=pp, parity_fail=pf, parity_skip=ps,
                orders_blocked=blocked,
                detail={"context": a.context, "note": a.detail} if (a.context or a.detail) else None,
            ))
            db.commit()
        finally:
            db.close()
        print(f"[gate-record] 기록됨 mode={a.mode} verdict={a.verdict} "
              f"blocked={blocked}")
    except Exception as exc:
        # 기록 실패가 관문 판정을 바꾸면 안 된다
        print(f"[gate-record] 기록 실패(무시): {type(exc).__name__}: {exc}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
