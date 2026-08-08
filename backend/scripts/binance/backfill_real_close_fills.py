#!/usr/bin/env python3
"""실계좌 lifecycle 청산 기록 소급 보정 (executed_price=0 / realized_pnl 누락).

배경 (2026-08-08):
  드라이버 _real_direct_close가 close_position() 반환값에만 의존해
  executed_price에 0을 기록했고, income 엔드포인트 반영 지연 때문에
  GRAMUSDT 청산은 realized_pnl까지 0으로 남았다(거래소 원장 +19.38).
  executed_price=0은 세션 현금 재구성에서 margin=0을 만들어 진입 증거금이
  반환되지 않는다. 발생원은 커밋 5f81583d에서 차단했고, 본 스크립트는
  이미 기록된 행을 거래소 체결내역(userTrades)으로 되돌린다.

대상: is_paper=false AND status='FILLED' AND lifecycle-real 세션
      AND 청산(BUY + position_side short) AND executed_price = 0
      → 각 행의 signal_timestamp ±20분 구간 userTrades와 대조.

안전장치:
  - 기본 드라이런. --apply 없으면 아무것도 쓰지 않는다.
  - 적용 전 대상 행 원본을 JSON 백업 파일로 저장한다.
  - 수량이 일치하는 체결만 채택한다(불일치 시 해당 행 건너뜀).
  - trade_metadata에 보정 이력과 원본 값을 남긴다.

사용:
  python scripts/binance/backfill_real_close_fills.py            # 드라이런
  python scripts/binance/backfill_real_close_fills.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]  # scripts/binance/ → backend/
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR.parent / ".env")

from sqlalchemy import text  # noqa: E402

from app.core import security  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402,F401
from app.models.account import ExchangeAccount  # noqa: E402

KST = timezone(timedelta(hours=9))
ACCOUNT_ID = 8
QTY_TOL = 1e-6

TARGETS_SQL = """
SELECT id, session_id, symbol, signal_type, position_side, requested_quantity,
       filled_quantity, executed_price, theoretical_price, realized_pnl,
       signal_timestamp, trade_metadata
FROM live_trade_executions
WHERE is_paper = false
  AND status = 'FILLED'
  AND session_id LIKE 'lifecycle-real-%'
  AND signal_type = 'BUY'
  AND lower(COALESCE(trade_metadata->>'position_side', position_side)) = 'short'
  AND executed_price = 0
ORDER BY signal_timestamp
"""


async def build_adapter(db):
    acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == ACCOUNT_ID).first()
    if not acc:
        raise RuntimeError(f"account {ACCOUNT_ID} not found")
    from app.adapters.binance_futures import BinanceFuturesAdapter
    ad = BinanceFuturesAdapter(
        api_key=security.decrypt_key(acc.encrypted_access_key or ""),
        secret_key=security.decrypt_key(acc.encrypted_secret_key or ""),
        api_url=acc.api_url or "https://fapi.binance.com",
        account_name=acc.account_name or "", is_testnet=False)
    await ad._ensure_time_sync()
    return ad


async def resolve(ad, row: dict) -> dict | None:
    """행에 대응하는 거래소 체결을 찾아 (vwap, realized, qty) 산출."""
    ts = row["signal_timestamp"].replace(tzinfo=timezone.utc)
    lo = int((ts - timedelta(minutes=20)).timestamp() * 1000)
    hi = int((ts + timedelta(minutes=20)).timestamp() * 1000)
    try:
        fills = await ad._signed_get("/fapi/v1/userTrades", {
            "symbol": row["symbol"], "startTime": lo, "endTime": hi, "limit": 500})
    except Exception as exc:
        return {"error": f"userTrades 조회 실패: {exc}"}
    if not fills:
        return {"error": "해당 구간 체결 없음 (거래소 조회 범위 밖일 수 있음)"}
    buys = [f for f in fills if f.get("side") == "BUY"]
    if not buys:
        return {"error": "구간 내 BUY 체결 없음"}
    qty = sum(float(f["qty"]) for f in buys)
    notional = sum(float(f["qty"]) * float(f["price"]) for f in buys)
    realized = sum(float(f.get("realizedPnl") or 0) for f in buys)
    db_qty = float(row["filled_quantity"] or row["requested_quantity"] or 0)
    if abs(qty - db_qty) > QTY_TOL:
        return {"error": f"수량 불일치 DB={db_qty} 거래소={qty} — 건너뜀"}
    return {"vwap": notional / qty, "realized": realized, "qty": qty, "n_fills": len(buys)}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup-dir", default=str(BACKEND_DIR / "backups"))
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = [dict(r._mapping) for r in db.execute(text(TARGETS_SQL)).fetchall()]
        print(f"보정 대상 {len(rows)}건 (청산 + executed_price=0)\n")
        if not rows:
            return 0

        ad = await build_adapter(db)
        plan, skipped = [], []
        for r in rows:
            got = await resolve(ad, r)
            ts = r["signal_timestamp"].replace(tzinfo=timezone.utc).astimezone(KST)
            if got is None or "error" in got:
                print(f"  SKIP {r['symbol']:<12} {ts:%m-%d %H:%M} — {got['error']}")
                skipped.append({"id": str(r["id"]), "symbol": r["symbol"],
                                "reason": got["error"]})
                continue
            pnl_old = float(r["realized_pnl"] or 0)
            pnl_new = got["realized"]
            print(f"  {r['symbol']:<12} {ts:%m-%d %H:%M}  "
                  f"executed_price {float(r['executed_price'] or 0):.8f} → {got['vwap']:.8f}  |  "
                  f"realized_pnl {pnl_old:+.5f} → {pnl_new:+.5f}"
                  f"{'   ← 손익 보정' if abs(pnl_old - pnl_new) > 1e-6 else ''}"
                  f"   (체결 {got['n_fills']}건, qty {got['qty']:g})")
            plan.append({"row": r, "fix": got})
            await asyncio.sleep(0.2)

        print(f"\n적용 가능 {len(plan)}건 / 건너뜀 {len(skipped)}건")
        if not args.apply:
            print("\n[DRY-RUN] --apply 를 붙이면 실제로 씁니다.")
            return 0
        if not plan:
            print("적용할 행이 없습니다.")
            return 0

        # ── 백업 ──
        bdir = Path(args.backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        bpath = bdir / f"real_close_fills_backup_{stamp}.json"
        bpath.write_text(json.dumps({
            "generated_at_kst": stamp,
            "note": "backfill_real_close_fills.py 적용 전 원본",
            "rows": [{k: (str(v) if not isinstance(v, (int, float, type(None), dict, list)) else v)
                      for k, v in p["row"].items()} for p in plan],
            "skipped": skipped,
        }, indent=2, ensure_ascii=False))
        print(f"백업 저장: {bpath}")

        # ── 적용 ──
        n = 0
        for p in plan:
            r, fix = p["row"], p["fix"]
            md = dict(r["trade_metadata"] or {})
            md["backfill"] = {
                "at_kst": stamp,
                "by": "backfill_real_close_fills.py",
                "source": "binance userTrades",
                "prev_executed_price": float(r["executed_price"] or 0),
                "prev_theoretical_price": float(r["theoretical_price"] or 0),
                "prev_realized_pnl": float(r["realized_pnl"] or 0),
            }
            md.setdefault("position_side", "short")
            db.execute(text("""
                UPDATE live_trade_executions
                   SET executed_price = :px,
                       theoretical_price = :px,
                       realized_pnl = :pnl,
                       trade_metadata = CAST(:md AS JSONB)
                 WHERE id = :id
            """), {"px": fix["vwap"], "pnl": fix["realized"],
                   "md": json.dumps(md), "id": r["id"]})
            n += 1
        db.commit()
        print(f"[APPLIED] {n}건 보정 완료")
        try:
            await ad.close()
        except Exception:
            pass
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
