"""일일 1군/2군 결과 리포트 → 텔레그램.

왜 (대표님 지시, 2026-08-13)
  3군 자동 디스패치를 정지하면서 매일 오던 텔레그램이 끊겼다. 그 자리에
  **1군(실거래) + 2군(리그)** 일일 리포트를 넣는다. 주간·월간 리포트와 같은
  아침 시간대(07:00~07:20 KST)에 같은 형식으로 보낸다.

무엇을 담나
  [1군] 실계좌 잔고·포지션·오늘 체결·정본 관문 결과
  [2군] 리그 좌석·유효 판정일까지 남은 일수·최근 라운드

무엇을 담지 않나
  · **무효 표시된 거래는 세지 않는다.** lifecycle 페이퍼 498거래가 전량 무효라
    (팬텀 익절·재진입·숏 수수료) 그대로 세면 리포트가 거짓말을 한다.
  · 수익률 "수준"을 단정하지 않는다. 유효 관측이 아직 거의 없다.

사용:
  python3 -m scripts.daily_tier_report --dry     # 출력만
  python3 -m scripts.daily_tier_report           # 텔레그램 발송
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

REAL_ACCOUNT_ID = 8
KST = timezone(timedelta(hours=9))
SESS = ROOT / "runs" / "paper_sessions"
LEAGUE_STATE = ROOT / "runs" / "tier_governor" / "state.json"
GATE_LOG = "/tmp/engine_gate_golden.log"
# 2군 최초 유효 판정일 — VALID_FROM_FLOOR(2026-08-09) + MIN_OBSERVATION_DAYS(14)
FIRST_VERDICT = date(2026, 8, 23)


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ─────────────────────────── 1군 ───────────────────────────

def tier1() -> list[str]:
    out = ["<b>[1군] 실거래</b>"]
    try:
        import asyncio

        from app.api.endpoints import create_adapter_from_account
        from app.db.session import SessionLocal
        from app.models.account import ExchangeAccount
        from app.models.user import User  # noqa: F401  mapper 해석용

        db = SessionLocal()
        try:
            acc = db.query(ExchangeAccount).filter(
                ExchangeAccount.id == REAL_ACCOUNT_ID).first()
            if acc is None:
                return out + ["  계좌를 찾을 수 없음"]
            ad = create_adapter_from_account(acc)
        finally:
            db.close()
        loop = asyncio.new_event_loop()
        try:
            data = loop.run_until_complete(ad._signed_get("/fapi/v2/account"))
        finally:
            loop.close()

        wallet = float(data.get("totalWalletBalance", 0))
        upnl = float(data.get("totalUnrealizedProfit", 0))
        avail = float(data.get("availableBalance", 0))
        pos = [p for p in data.get("positions", [])
               if abs(float(p.get("positionAmt", 0))) > 0]
        out.append(f"  지갑 ${wallet:,.2f} · 평가 {upnl:+,.2f} · 가용 ${avail:,.2f}")
        if pos:
            out.append(f"  포지션 {len(pos)}건")
            for p in pos:
                amt = float(p["positionAmt"])
                side = "숏" if amt < 0 else "롱"
                ep = float(p.get("entryPrice", 0))
                pu = float(p.get("unrealizedProfit", 0))
                pct = (pu / (abs(amt) * ep) * 100) if ep and amt else 0.0
                out.append(f"    {esc(p['symbol'])} {side} {abs(amt):,.4g} "
                           f"@{ep:.6g} → {pu:+,.2f} ({pct:+.2f}%)")
        else:
            out.append("  포지션 없음")
    except Exception as exc:
        out.append(f"  계좌 조회 실패: {esc(type(exc).__name__)}")

    # 오늘 체결
    try:
        from sqlalchemy import text

        from app.db.session import engine
        since = datetime.now(KST).replace(hour=0, minute=0, second=0,
                                          microsecond=0).astimezone(timezone.utc)
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT symbol, signal_type, executed_price, filled_quantity "
                "FROM live_trade_executions WHERE order_filled_at >= :s "
                "ORDER BY order_filled_at"), {"s": since.replace(tzinfo=None)}).fetchall()
        if rows:
            out.append(f"  오늘 체결 {len(rows)}건")
            for r in rows[:6]:
                out.append(f"    {esc(r[0])} {esc(r[1])} {float(r[2] or 0):.6g} "
                           f"x{float(r[3] or 0):,.4g}")
        else:
            out.append("  오늘 체결 없음")
    except Exception as exc:
        out.append(f"  체결 조회 실패: {esc(type(exc).__name__)}")

    # 정본 관문
    try:
        if os.path.exists(GATE_LOG):
            body = open(GATE_LOG).read()
            hit = [l for l in body.splitlines() if "일치" in l and "불일치" in l]
            mtime = datetime.fromtimestamp(os.path.getmtime(GATE_LOG), KST)
            mark = "통과" if hit and "불일치 0" in hit[-1] else "**확인 필요**"
            out.append(f"  정본 관문 {mark} ({mtime:%m-%d %H:%M})")
        else:
            out.append("  정본 관문 기록 없음")
    except Exception:
        pass
    return out


# ─────────────────────────── 2군 ───────────────────────────

def _league_session_ids() -> set[str]:
    """현재 리그 좌석에 앉아 있는 세션.

    `tier_governor.is_governed` 를 그대로 쓴다 — "무엇이 리그 세션인가"의 정의가
    두 곳에 있으면 갈린다. 상태 파일의 `sessions` 는 쓰지 않는다(위 주석 참조).
    """
    import glob as _g
    try:
        from tier_governor import SESS_DIR, is_governed
    except Exception:
        return set()
    out = set()
    for sdir in _g.glob(os.path.join(SESS_DIR, "*")):
        sj = os.path.join(sdir, "session.json")
        if not os.path.exists(sj):
            continue
        try:
            meta = json.load(open(sj))
        except Exception:
            continue
        if is_governed(meta, "binance") and meta.get("status") == "active":
            out.add(meta["session_id"])
    return out


def tier2() -> list[str]:
    out = ["", "<b>[2군] 리그</b>"]
    try:
        st = json.loads(LEAGUE_STATE.read_text())
        seats = st.get("seats", {})
        # ⚠ `state["sessions"]` 를 좌석 수로 쓰면 안 된다. 그건 Day-30 체크포인트
        # 추적용 dict 이고 `setdefault` 로 **추가만** 된다 — 강등된 세션이 남고,
        # 아직 체크포인트에 도달 못 한 현役 좌석은 빠진다.
        # 실측(2026-08-13): sessions 13 = terminated 7 + 누락 5, 실제 좌석은 11.
        out.append(f"  좌석 {seats.get('used','?')}/{seats.get('max','?')} · "
                   f"큐 {seats.get('queue','?')}")
        rounds = (st.get("league") or {}).get("rounds") or []
        if rounds:
            r = rounds[-1]
            out.append(f"  최근 라운드 {str(r.get('at'))[:10]} ({esc(r.get('type'))}) "
                       f"강등 {len(r.get('demoted') or [])}")
    except Exception as exc:
        out.append(f"  리그 상태 읽기 실패: {esc(type(exc).__name__)}")

    # 유효 거래 (무효 표시 제외) — **리그 세션만** 센다.
    # 전 세션을 세면 2군과 무관한 것까지 섞여 리포트가 부풀려진다.
    try:
        from app.composer_framework.paper_session import load_trades
        today = datetime.now(KST).date()
        league_ids = _league_session_ids()
        n_valid = n_today = 0
        for sid in league_ids:
            tf = SESS / sid / "trades.jsonl"
            if not tf.exists():
                continue
            for t in load_trades(tf):
                n_valid += 1
                if str(t.get("exit_ts", ""))[:10] == str(today):
                    n_today += 1
        out.append(f"  유효 거래 누적 {n_valid} · 오늘 청산 {n_today} "
                   f"(좌석 {len(league_ids)}세션)")
        out.append("  <i>무효 표시 거래는 제외 (INVALID_TRADES.json)</i>")
    except Exception as exc:
        out.append(f"  거래 집계 실패: {esc(type(exc).__name__)}")

    left = (FIRST_VERDICT - datetime.now(KST).date()).days
    out.append(f"  최초 유효 판정 {FIRST_VERDICT} "
               + (f"(D-{left})" if left > 0 else "(도래)"))
    return out


def build() -> str:
    now = datetime.now(KST)
    head = [f"📊 <b>일일 리포트</b> {now:%Y-%m-%d (%a)}", ""]
    tail = ["", "<i>3군 디스패치 정지(2026-08-13) 대체 리포트</i>"]
    return "\n".join(head + tier1() + tier2() + tail)


def main() -> int:
    ap = argparse.ArgumentParser(description="일일 1군/2군 리포트")
    ap.add_argument("--dry", action="store_true", help="출력만, 발송 안 함")
    args = ap.parse_args()

    msg = build()
    print(msg.replace("<b>", "").replace("</b>", "")
             .replace("<i>", "").replace("</i>", ""))
    if args.dry:
        print("\n[DRY] 발송하지 않음")
        return 0
    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
    except Exception:
        sys.path.insert(0, str(ROOT / "scripts" / "binance"))
        from lifecycle_live_signal_driver import _telegram_notify  # type: ignore
    try:
        _telegram_notify(REAL_ACCOUNT_ID, msg)
        print("[SENT] telegram dispatched")
    except Exception as exc:
        print(f"[FAIL] telegram send: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
