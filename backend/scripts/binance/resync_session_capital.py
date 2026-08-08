#!/usr/bin/env python3
"""live_bot_sessions.current_capital 을 체결 기록으로부터 재동기화한다.

current_capital 은 파생값(`initial_capital + Σ realized_pnl`)이고 엔진이
체결 시점마다 갱신한다(live_context.py). 그런데 엔진을 우회하는 경로 —
lifecycle 드라이버의 거래소 직접청산, 그리고 execution 행을 나중에 고치는
소급 보정 — 에서는 갱신이 돌지 않아 값이 낡는다. 2026-08-08 확인 시 실계좌
11개 세션 합계 137 USDT가 어긋나 있었다(대시보드·API 표시가 그만큼 과소).

파생값 재계산이므로 언제 몇 번을 돌려도 결과가 같다(멱등). 정기 점검용으로
드라이런만 돌려서 어긋남을 감지하는 용도로도 쓸 수 있다.

사용:
  python scripts/binance/resync_session_capital.py                  # 드라이런(실계좌)
  python scripts/binance/resync_session_capital.py --apply
  python scripts/binance/resync_session_capital.py --all            # 페이퍼 포함
  python scripts/binance/resync_session_capital.py --pattern 'lifecycle-real-%'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import text  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

KST = timezone(timedelta(hours=9))
TOL = 0.005  # 이보다 작은 어긋남은 표시하지 않음 (부동소수 잔차)

SQL = """
SELECT b.id AS sid,
       b.initial_capital AS ic,
       b.current_capital AS cc,
       COALESCE(s.pnl, 0) AS pnl,
       COALESCE(s.n, 0) AS n_fills
FROM live_bot_sessions b
LEFT JOIN (
    SELECT session_id, SUM(realized_pnl) AS pnl, COUNT(*) AS n
    FROM live_trade_executions
    WHERE status = 'FILLED'
    GROUP BY session_id
) s ON s.session_id = b.id
WHERE b.id LIKE :pat
ORDER BY b.id
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pattern", default="lifecycle-real-%")
    ap.add_argument("--all", action="store_true", help="모든 세션 (--pattern 무시)")
    args = ap.parse_args()
    pat = "%" if args.all else args.pattern

    db = SessionLocal()
    try:
        rows = [dict(r._mapping) for r in db.execute(text(SQL), {"pat": pat}).fetchall()]
        drift = []
        for r in rows:
            ic = float(r["ic"] or 0)
            cc = float(r["cc"] or 0)
            should = ic + float(r["pnl"] or 0)
            if abs(should - cc) > TOL:
                drift.append({**r, "should": should, "delta": should - cc})

        print(f"대상 {len(rows)}개 세션 (pattern={pat}) | 어긋남 {len(drift)}개\n")
        if drift:
            print(f"{'세션':<34}{'초기':>10}{'현재표시':>10}{'정확값':>10}{'차이':>9}{'체결':>6}")
            tot = 0.0
            for d in drift:
                tot += d["delta"]
                print(f"{d['sid']:<34}{float(d['ic'] or 0):>10.2f}{float(d['cc'] or 0):>10.2f}"
                      f"{d['should']:>10.2f}{d['delta']:>+9.2f}{int(d['n_fills']):>6}")
            print(f"{'합계':<34}{'':>30}{tot:>+9.2f}")
        else:
            print("모든 세션이 일치합니다.")
            return 0

        if not args.apply:
            print("\n[DRY-RUN] --apply 를 붙이면 실제로 씁니다.")
            return 0

        stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        bdir = BACKEND_DIR / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        bpath = bdir / f"session_capital_backup_{stamp}.json"
        bpath.write_text(json.dumps(
            {"generated_at_kst": stamp, "pattern": pat,
             "rows": [{k: (float(v) if isinstance(v, (int, float)) else str(v))
                       for k, v in d.items()} for d in drift]},
            indent=2, ensure_ascii=False))
        print(f"백업 저장: {bpath}")

        for d in drift:
            db.execute(text("UPDATE live_bot_sessions SET current_capital = :cc WHERE id = :id"),
                       {"cc": d["should"], "id": d["sid"]})
        db.commit()
        print(f"[APPLIED] {len(drift)}개 세션 재동기화 완료")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
