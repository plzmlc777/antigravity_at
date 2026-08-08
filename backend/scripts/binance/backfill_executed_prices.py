#!/usr/bin/env python3
"""이론가로 대체 기록된 체결가를 거래소 주문조회로 복원한다.

배경 (2026-08-08):
  live_context 의 `p.executed_price = res.get("price") or p.theoretical_price`
  가 어댑터 avgPrice=0(주문이 아직 NEW)일 때 조용히 이론가로 대체했다.
  이론가는 드라이버가 보낸 System-2 바 종가라 tick 배수로 딱 떨어진다.
  실계좌 39건 중 23건이 이렇게 기록됐고, 거래소 원장 대비 실현손익이
  +0.715 USDT(0.30%) 커졌다. 발생원은 커밋 b2ae21be 에서 차단했다.

  userTrades 는 7/27 이전을 돌려주지 않지만 GET /fapi/v1/order 는 orderId 로
  과거 주문도 돌려준다 — 23건 전부 exchange_order_no 를 갖고 있어 복원된다.

무엇을 고치나:
  - 모든 대상 행: executed_price ← 주문의 실제 avgPrice
  - 청산 행(BUY+short): realized_pnl ← 거래소 income 원장의 해당 청산 이벤트
    (원장이 진실이다. 체결가만 고치고 손익을 그대로 두면 서로 안 맞는다.)
  - theoretical_price 는 건드리지 않는다 — 그 값 자체는 '의도가'로서 유효하고,
    슬리피지(executed - theoretical) 계산의 기준이 된다.

안전장치:
  - 기본 드라이런. --apply 없으면 아무것도 쓰지 않는다.
  - 적용 전 원본 JSON 백업.
  - 주문의 executedQty 가 DB filled_quantity 와 다르면 해당 행 건너뜀.
  - avgPrice 가 0이면 건너뜀 (지어내지 않는다).
  - trade_metadata 에 보정 이력과 원본 값 보존.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
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
SELECT id, session_id, symbol, signal_type,
       COALESCE(trade_metadata->>'position_side', lower(position_side)) ps,
       filled_quantity fq, executed_price ep, theoretical_price tp,
       realized_pnl pnl, exchange_order_no oid, signal_timestamp ts, trade_metadata md
FROM live_trade_executions
WHERE is_paper = false
  AND status = 'FILLED'
  AND session_id LIKE 'lifecycle-real-%'
  AND executed_price = theoretical_price
  AND COALESCE(trade_metadata->>'driver', '') <> 'lifecycle_direct_close'
  AND COALESCE(trade_metadata->>'backfill', '') = ''
  AND exchange_order_no IS NOT NULL AND exchange_order_no <> ''
ORDER BY symbol, signal_timestamp
"""

ALL_ROWS_SQL = """
SELECT symbol, signal_type,
       COALESCE(trade_metadata->>'position_side', lower(position_side)) ps,
       id, signal_timestamp ts
FROM live_trade_executions
WHERE is_paper = false AND status = 'FILLED' AND session_id LIKE 'lifecycle-real-%'
ORDER BY symbol, signal_timestamp
"""


async def build_adapter(db):
    acc = db.query(ExchangeAccount).filter(ExchangeAccount.id == ACCOUNT_ID).first()
    from app.adapters.binance_futures import BinanceFuturesAdapter
    ad = BinanceFuturesAdapter(
        api_key=security.decrypt_key(acc.encrypted_access_key or ""),
        secret_key=security.decrypt_key(acc.encrypted_secret_key or ""),
        api_url=acc.api_url or "https://fapi.binance.com",
        account_name=acc.account_name or "", is_testnet=False)
    await ad._ensure_time_sync()
    return ad


async def ledger_close_events(ad, days: int = 93) -> dict:
    """심볼별 청산 이벤트(5분 이내 fill 묶음) 시간순 목록."""
    import time as _time
    now_ms = int(_time.time() * 1000)
    start = now_ms - days * 86400_000
    rows = []
    cur = start
    while cur < now_ms:
        nxt = min(cur + 7 * 86400_000, now_ms)
        batch = await ad._signed_get("/fapi/v1/income", {
            "incomeType": "REALIZED_PNL", "startTime": cur, "endTime": nxt, "limit": 1000})
        rows.extend(batch or [])
        cur = nxt
        await asyncio.sleep(0.2)
    by = defaultdict(list)
    for r in rows:
        by[r["symbol"]].append((r["time"], float(r["income"])))
    out = {}
    for s, xs in by.items():
        xs.sort()
        ev, cur_g = [], [xs[0]]
        for x in xs[1:]:
            if x[0] - cur_g[-1][0] <= 300_000:
                cur_g.append(x)
            else:
                ev.append(cur_g); cur_g = [x]
        ev.append(cur_g)
        out[s] = [sum(v for _, v in g) for g in ev]
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        targets = [dict(r._mapping) for r in db.execute(text(TARGETS_SQL)).fetchall()]
        all_rows = [dict(r._mapping) for r in db.execute(text(ALL_ROWS_SQL)).fetchall()]
        print(f"보정 대상 {len(targets)}건 (executed_price == theoretical_price)\n")
        if not targets:
            return 0

        ad = await build_adapter(db)
        events = await ledger_close_events(ad)

        # 심볼별 청산 서수 → 원장 이벤트 인덱스 매핑
        close_ord = {}
        counter = defaultdict(int)
        for r in all_rows:
            is_close = not ((r["signal_type"] == "SELL" and (r["ps"] or "") == "short")
                            or (r["signal_type"] == "BUY" and (r["ps"] or "") in ("long", "")))
            if is_close:
                close_ord[str(r["id"])] = (r["symbol"], counter[r["symbol"]])
                counter[r["symbol"]] += 1

        plan, skipped = [], []
        for r in targets:
            try:
                o = await ad._signed_get("/fapi/v1/order",
                                         {"symbol": r["symbol"], "orderId": str(r["oid"])})
            except Exception as exc:
                skipped.append((r, f"주문조회 실패: {exc}")); continue
            px = float(o.get("avgPrice") or 0)
            eq = float(o.get("executedQty") or 0)
            db_qty = float(r["fq"] or 0)
            if px <= 0:
                skipped.append((r, "avgPrice=0 (복원 불가)")); continue
            if abs(eq - db_qty) > QTY_TOL:
                skipped.append((r, f"수량 불일치 DB={db_qty} 거래소={eq}")); continue

            new_pnl = None
            key = close_ord.get(str(r["id"]))
            if key:
                sym, k = key
                evs = events.get(sym, [])
                if k < len(evs):
                    new_pnl = evs[k]
            plan.append({"row": r, "px": px, "pnl": new_pnl})
            await asyncio.sleep(0.15)

        print(f"{'심볼':<12}{'시각':<13}{'신호':<5}{'DB체결가':>13}{'실제체결가':>14}"
              f"{'DB손익':>10}{'원장손익':>10}")
        d_pnl = 0.0
        for p in plan:
            r = p["row"]; ts = r["ts"]
            old_pnl = float(r["pnl"] or 0)
            pn = p["pnl"]
            if pn is not None:
                d_pnl += pn - old_pnl
            print(f"{r['symbol']:<12}{ts:%m-%d %H:%M}  {r['signal_type']:<5}"
                  f"{float(r['ep']):>13.8f}{p['px']:>14.8f}"
                  f"{old_pnl:>10.4f}{(f'{pn:.4f}' if pn is not None else '—'):>10}")
        for r, why in skipped:
            print(f"  SKIP {r['symbol']:<12}{r['ts']:%m-%d %H:%M} — {why}")

        print(f"\n적용 가능 {len(plan)}건 / 건너뜀 {len(skipped)}건 "
              f"| 실현손익 순변화 {d_pnl:+.4f} USDT")
        if not args.apply:
            print("\n[DRY-RUN] --apply 를 붙이면 실제로 씁니다.")
            return 0

        stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        bdir = BACKEND_DIR / "backups"; bdir.mkdir(parents=True, exist_ok=True)
        bpath = bdir / f"executed_prices_backup_{stamp}.json"
        bpath.write_text(json.dumps({
            "generated_at_kst": stamp,
            "rows": [{k: (str(v) if isinstance(v, (datetime,)) else v)
                      for k, v in p["row"].items()} for p in plan],
            "skipped": [{"id": str(r["id"]), "symbol": r["symbol"], "reason": w}
                        for r, w in skipped],
        }, indent=2, ensure_ascii=False, default=str))
        print(f"백업 저장: {bpath}")

        n = 0
        for p in plan:
            r = p["row"]
            md = dict(r["md"] or {})
            md["backfill"] = {
                "at_kst": stamp, "by": "backfill_executed_prices.py",
                "source": "binance GET /fapi/v1/order (avgPrice)",
                "prev_executed_price": float(r["ep"] or 0),
                "prev_realized_pnl": float(r["pnl"] or 0),
            }
            params = {"px": p["px"], "md": json.dumps(md), "id": r["id"]}
            if p["pnl"] is not None:
                db.execute(text("UPDATE live_trade_executions SET executed_price=:px, "
                                "realized_pnl=:pnl, trade_metadata=CAST(:md AS JSONB) "
                                "WHERE id=:id"), {**params, "pnl": p["pnl"]})
            else:
                db.execute(text("UPDATE live_trade_executions SET executed_price=:px, "
                                "trade_metadata=CAST(:md AS JSONB) WHERE id=:id"), params)
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
