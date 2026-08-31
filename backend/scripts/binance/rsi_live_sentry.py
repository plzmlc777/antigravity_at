#!/usr/bin/env python3
"""RSI 1군 **자율 대조 감시**. 사람이 안 쳐도 스스로 본다.

왜 만들었나 (2026-08-31)
    08:30 에 고아 포지션이 생겨 익절·손절 없이 1.3시간 살아 있었고, 그 사이
    증거금이 막혀 다음 신호(+12.83$ 짜리)를 놓쳤다. **대표님이 텔레그램을
    보고 말씀하실 때까지 시스템은 몰랐다.**

    감시 도구(`rsi_watch.sh`)에는 장부↔거래소 대조가 이미 있었고 한 번만
    돌았으면 첫 줄에서 잡혔다. 문제는 그게 **대표님이 「정기 점검」을 칠 때만
    도는 것**이었다는 데 있다. 08-30 14:05 이후 19시간 35분 동안 한 번도
    안 돌았다.

    옛 1군(신상저격수)에는 `lifecycle-hourly-reconcile` 이 매시 :20 에 돌고
    있다. RSI 가 1군을 물려받을 때 **그 감시가 따라오지 않았다** —
    교훈 #102 「승격은 딸린 장치 전부의 이사」, 네 번째다.

무엇을 보는가 — 하나라도 걸리면 텔레그램으로 즉시 알린다
    1. 장부 ↔ 거래소 불일치 (고아 · 유령)
    2. 보호 장치 없는 포지션 (익절 지정가 또는 손절 조건부 결손)
    3. 거절·결함 계수기 증가 (주문거절 · 익절거절 · 손절거절 · 커널실패 · 묵은봉)
    4. 세션 정지 · 원장 정체 (30분봉인데 상태가 안 갱신됨)
    5. 실거래 ↔ 그림자 체결 짝 깨짐

⚠ **조회 실패는 「이상 없음」이 아니다** (교훈 #106). 거래소를 못 읽으면
  그 사실 자체를 알린다. 조용히 넘어가면 고아가 또 5시간 방치된다.

⚠ 이 감시는 **아무것도 고치지 않는다.** 주문도 청산도 하지 않는다. 보기만
  하고 알린다 — 자동 개입은 판단을 요구하고, 판단은 대표님 몫이다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "binance"))

SESS_ROOT = ROOT / "runs" / "paper_sessions" / "rsi_extreme"
LIVE = "30m_rsi12_LIVE"
SHADOW = "30m_rsi12_SHADOW"
STATE = ROOT / "runs" / "paper_sessions" / "rsi_extreme" / ".sentry_seen.json"

# 늘어나면 사건인 계수기 — 이름과 사람 말
COUNTERS = [("n_reject_order", "주문거절"), ("n_reject_tp", "익절거절"),
            ("n_reject_sl", "손절거절"), ("n_kernelfail", "커널실패"),
            ("n_stalebar", "묵은봉"), ("n_pricefail", "시세실패")]

log = logging.getLogger("rsi-sentry")


def _book(name: str) -> dict:
    f = SESS_ROOT / name / "state.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def _seen() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            return {}
    return {}


def _save_seen(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def check(account: int = 8) -> list:
    """이상 목록을 돌려준다. 빈 목록이면 정상."""
    alerts: list = []
    live = _book(LIVE)
    book = {p["symbol"] for p in live.get("pos", [])}

    # ── ① 거래소 원본 ─────────────────────────────────────────
    #    ⚠ 못 읽으면 그 자체가 사건이다. 빈 결과로 뭉개지 않는다.
    ex, oo, algo, read_ok = {}, {}, {}, True
    try:
        from rsi_live_broker import LiveBroker, _run
        from app.adapters.binance_futures import FAPI_V2
        b = LiveBroker(account_id=account, notional_usd=1.0, dry_run=True)
        b.connect()
        rows = _run(b._adapter._signed_get(f"{FAPI_V2}/positionRisk", {}))
        ex = {r["symbol"]: r for r in (rows or [])
              if abs(float(r.get("positionAmt", 0) or 0)) > 0}
        oo = b.open_orders()
        algo = b.open_algo_orders()
    except Exception as exc:                                 # noqa: BLE001
        read_ok = False
        alerts.append(("🚨", "거래소를 읽지 못했다",
                       f"{exc}\n포지션 상태를 **모른다** — 없다는 뜻이 아니다."))

    if read_ok:
        # ── ② 장부 ↔ 거래소 ───────────────────────────────────
        if book != set(ex):
            only_ex = sorted(set(ex) - book)
            only_bk = sorted(book - set(ex))
            msg = []
            if only_ex:
                msg.append(f"거래소에만: {', '.join(only_ex)} (고아 — 장부가 모른다)")
            if only_bk:
                msg.append(f"장부에만: {', '.join(only_bk)} (유령 — 거래소엔 없다)")
            alerts.append(("🚨", "장부와 거래소가 다르다", "\n".join(msg)))

        # ── ③ 보호 장치 결손 ──────────────────────────────────
        for sym, r in ex.items():
            miss = []
            if sym not in oo:
                miss.append("익절 지정가")
            if sym not in algo:
                miss.append("손절 조건부")
            if miss:
                alerts.append(("🚨", f"{sym} 보호 장치 결손",
                               f"없는 것: {' · '.join(miss)}\n"
                               f"평가 {float(r.get('unRealizedProfit', 0)):+.4f} USDT"))

    # ── ④ 계수기 증가 ─────────────────────────────────────────
    seen = _seen()
    now_c = {k: int(live.get(k, 0)) for k, _ in COUNTERS}
    grew = [(ko, now_c[k] - int(seen.get(k, now_c[k])))
            for k, ko in COUNTERS if now_c[k] > int(seen.get(k, now_c[k]))]
    if grew:
        alerts.append(("⚠️", "거절·결함 계수기가 늘었다",
                       " · ".join(f"{ko} +{d}" for ko, d in grew)))

    # ── ⑤ 원장 정체 ───────────────────────────────────────────
    #    30분봉이니 상태는 30분마다 갱신된다. 45분 넘으면 안 돌고 있다.
    ts = live.get("saved_at")
    if ts:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(ts)).total_seconds() / 60
        if age > 45:
            alerts.append(("🚨", "원장이 멈췄다",
                           f"마지막 갱신 {ts[:19]} — {age:.0f}분 전. "
                           f"세션이 죽었거나 사이클이 안 돈다."))
    else:
        alerts.append(("🚨", "원장을 읽지 못했다", f"{SESS_ROOT / LIVE}/state.json"))

    # ── ⑥ 짝 깨짐 ─────────────────────────────────────────────
    shadow = _book(SHADOW)
    if shadow:
        lf, sf = int(live.get("n_fill", 0)), int(shadow.get("n_fill", 0))
        if abs(lf - sf) >= 3:
            alerts.append(("⚠️", "실거래와 그림자의 체결 수가 벌어졌다",
                           f"실거래 {lf} · 그림자 {sf} (차이 {abs(lf - sf)})"))

    _save_seen(now_c)
    return alerts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true",
                    help="알림을 보내지 않고 화면에만 낸다")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    alerts = check(a.account)
    if not alerts:
        log.info("✔ 이상 없음 — 장부·거래소·보호장치·계수기·원장 전부 정상")
        return 0

    for mark, title, body in alerts:
        log.error("%s %s — %s", mark, title, body.replace("\n", " / "))

    text = ("🚨 <b>RSI 1군 감시 — 이상 %d건</b>\n"
            "<i>%s KST</i>\n\n" % (
                len(alerts),
                datetime.now(timezone.utc).astimezone().strftime("%m-%d %H:%M")))
    for mark, title, body in alerts:
        text += f"{mark} <b>{title}</b>\n{body}\n\n"
    text += "확인: <code>bash scripts/binance/rsi_watch.sh</code>"

    if a.dry_run:
        print(text)
        return 1
    try:
        from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
        _telegram_notify(a.account, text)
        log.info("텔레그램 발송 완료 — 계좌 %d", a.account)
    except Exception as exc:                                 # noqa: BLE001
        # 알림이 안 나가는 것 자체가 사건이다. 종료코드로 남긴다.
        log.critical("텔레그램 발송 실패 — 이상을 알리지 못했다: %s", exc)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
