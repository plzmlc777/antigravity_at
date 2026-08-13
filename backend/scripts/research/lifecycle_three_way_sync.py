"""신상저격수 — **백테스트 / 페이퍼 / 실계좌 3자 동기화 검증**.

왜 필요한가 (대표님 지적, 2026-08-12)
  "실계좌 모드와 페이퍼 모드, 그리고 백테스트 결과 동기화 여부를 검토하는 것도
  중요한 이슈다."

  옳다. 그리고 오늘 그게 왜 중요한지 실물로 드러났다:
    · 백테스트는 순수 Day-1 숏 → Day-30, **한 번만** 거래한다 (원래 옳았다).
    · 페이퍼/실계좌는 소스가 -1.0 을 영원히 내보내 **익절 뒤 즉시 재진입**했다.
      DATAIPUSDT 는 30일에 4회, REUSDT 실계좌는 8회 진입했다.
    · 그래서 3개월 실계좌 실적(+$202.25)은 **백테스트가 검증한 전략의 것이 아니다.**

  세 층이 벌어져 있으면 어느 수치도 다른 층의 근거가 못 된다. 이 도구는
  **상장 사건별로 세 층을 나란히 놓고 벌어진 곳을 짚는다.**

무엇을 비교하는가
  상장 사건 하나 = 행 하나. 열은 셋:
    BT   백테스트   — 순수 규칙 (Day-1 종가 숏 → Day-30 종가, SL +50%)
    PAP  System-2   — runs/paper_sessions 의 lifecycle 세션 실제 거래
    REAL 실계좌     — live_trade_executions (account 8, is_paper=false)

  각 층에서 재는 것:
    n_trades  진입 횟수 — **1 이 아니면 재진입이다** (가장 중요한 지표)
    ret       수익률 (BT/PAP) 또는 실현손익 $ (REAL)
    entry     최초 진입일 — 층 간 어긋나면 신호 전달 지연이다

판정
  · **거래 횟수 불일치**가 최우선 경보다. 규칙이 다르다는 뜻이므로 수익률 비교는
    무의미해진다.
  · 진입일 차이 > 2일 → 신호 전달 경로 점검.
  · 세 층 모두 1회 진입이고 진입일이 맞으면, 그때 비로소 수익률을 비교한다.

사용:
  python3 scripts/research/lifecycle_three_way_sync.py
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lc_3way")

LISTINGS = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
REAL_ACCOUNT = 8
PAPER_ACCOUNT = 12      # System-1 페이퍼 — 실거래와 **동일 조건**(수량만 다름)
HOLD_DAYS = 30
SL_PCT = 0.50
FRIC_BP = 10.0


def bt_trade(conn, sym: str, ld: date):
    """백테스트 층 — 순수 규칙 한 번."""
    from sqlalchemy import text
    r = conn.execute(text(
        "SELECT timestamp, high, close FROM ohlcv WHERE symbol=:s AND time_frame='1m' "
        "AND timestamp >= :a AND timestamp < :b ORDER BY timestamp"),
        {"s": sym, "a": ld, "b": ld + timedelta(days=HOLD_DAYS + 5)}).fetchall()
    if not r:
        return None
    df = pd.DataFrame(r, columns=["ts", "high", "close"])
    df["ts"] = pd.to_datetime(df["ts"])
    d = df.set_index("ts").astype(float)
    daily = pd.DataFrame({"high": d["high"].resample("1D").max(),
                          "close": d["close"].resample("1D").last()}).dropna()
    if len(daily) < 3:
        return None
    entry = float(daily["close"].iloc[0])
    stop = entry * (1 + SL_PCT)
    end = min(HOLD_DAYS, len(daily) - 1)
    for k in range(1, end + 1):
        if float(daily["high"].iloc[k]) >= stop:
            return {"n": 1, "ret": -SL_PCT * 100 - FRIC_BP / 100,
                    "entry": str(daily.index[0].date()), "reason": "sl"}
    return {"n": 1, "ret": (entry / float(daily["close"].iloc[end]) - 1) * 100 - FRIC_BP / 100,
            "entry": str(daily.index[0].date()), "reason": "time"}


def paper_layer() -> dict:
    """System-2 층 — 상장 사건별 base 변형의 실제 거래."""
    out = {}
    for d in sorted(glob.glob(str(ROOT / "runs" / "paper_sessions" / "*"))):
        f = os.path.join(d, "session.json")
        if not os.path.exists(f):
            continue
        j = json.load(open(f))
        n = j.get("name", "")
        m = re.match(r"lifecycle_(.+?)_(\d{4}-\d{2}-\d{2})$", n)
        if not m or any(v in n for v in ("h21", "earlyexit", "bearskip")):
            continue      # base 변형만 (백테스트 규칙과 같은 것)
        sym, ld = m.group(1), m.group(2)
        tf = os.path.join(d, "trades.jsonl")
        tr = ([t for t in (json.loads(x) for x in open(tf)) if not t.get("invalid")]
              if os.path.exists(tf) else [])          # 무효 표시 제외
        out[(sym, ld)] = {
            "n": len(tr),
            "ret": sum(t["return_pct"] for t in tr) * 100 if tr else 0.0,
            "entry": tr[0]["entry_ts"][:10] if tr else "—",
            "open": j.get("side") != "flat",
        }
    return out


def account_layer(conn, account_id: int, is_paper: bool) -> dict:
    """계좌 층 — 실제 체결 기록(System-1).

    실거래(8)와 페이퍼(12)가 **같은 드라이버·같은 시각·같은 가격**으로 체결된다.
    다른 것은 수량뿐이다(페이퍼 고정 $200 / 실거래 지갑 20%). 그래서 이 둘을
    나란히 놓으면 **사이징만의 효과**가 분리되고, System-2(정본)와 비교하면
    **체결 지연의 효과**가 분리된다.
    """
    from sqlalchemy import text
    ids = [r[0] for r in conn.execute(text(
        "select id from live_bot_sessions where account_id=:a"), {"a": account_id})]
    if not ids:
        return {}
    q = ",".join("'" + str(i) + "'" for i in ids)
    rows = conn.execute(text(
        f"select symbol, signal_type, order_filled_at, realized_pnl, executed_price "
        f"from live_trade_executions where session_id in ({q}) "
        f"and coalesce(is_paper,false)=:ip order by order_filled_at"),
        {"ip": is_paper}).fetchall()
    out = {}
    for sym, sig, ts, pnl, px in rows:
        e = out.setdefault(sym, {"n": 0, "pnl": 0.0, "entry": None,
                                 "entry_px": None, "fills": []})
        e["n"] += 1
        e["pnl"] += float(pnl or 0)
        if e["entry"] is None:
            e["entry"] = str(ts)[:10]
            e["entry_px"] = float(px or 0)
        e["fills"].append(str(ts)[:10])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="신상저격수 3자 동기화 검증")
    p.add_argument("--since", default="2026-05-01", help="이 날짜 이후 상장만")
    p.add_argument("--out", default=str(ROOT / "runs" / "research_track" /
                                        "lifecycle_three_way_sync.json"))
    args = p.parse_args()

    listings = json.load(open(LISTINGS)) if LISTINGS.exists() else {}
    pap = paper_layer()
    from app.db.session import engine
    rows = []
    with engine.connect() as conn:
        real = account_layer(conn, REAL_ACCOUNT, is_paper=False)
        pacct = account_layer(conn, PAPER_ACCOUNT, is_paper=True)
        keys = sorted(pap.keys(), key=lambda k: k[1])
        for sym, ld in keys:
            if ld < args.since:
                continue
            bt = bt_trade(conn, sym, date.fromisoformat(ld))
            rows.append({
                "symbol": sym, "listing": ld,
                "bt_n": bt["n"] if bt else None,
                "bt_ret": bt["ret"] if bt else None,
                "bt_entry": bt["entry"] if bt else "—",
                "pap_n": pap[(sym, ld)]["n"],
                "pap_ret": pap[(sym, ld)]["ret"],
                "pap_entry": pap[(sym, ld)]["entry"],
                "pap_open": pap[(sym, ld)]["open"],
                "real_n": real.get(sym, {}).get("n", 0),
                "real_pnl": real.get(sym, {}).get("pnl", 0.0),
                "real_entry": real.get(sym, {}).get("entry", "—"),
                "real_px": real.get(sym, {}).get("entry_px"),
                # System-1 페이퍼(계좌 12) — 실거래와 **동일 조건**, 수량만 다름
                "pa_n": pacct.get(sym, {}).get("n", 0),
                "pa_entry": pacct.get(sym, {}).get("entry", "—"),
                "pa_px": pacct.get(sym, {}).get("entry_px"),
            })

    D = pd.DataFrame(rows)
    print("\n" + "=" * 108)
    print(f"신상저격수 4자 동기화 — 상장 {args.since} 이후 {len(D)}건")
    print("=" * 108)
    print("  BT=백테스트(순수규칙)  CANON=System-2 정본(바 시가 체결)")
    print("  PA=System-1 페이퍼(계좌12)  REAL=실계좌(계좌8)")
    print("  ** PA 와 REAL 은 같은 드라이버·같은 시각·같은 가격. 다른 건 수량뿐 **")
    print("  ** 따라서 CANON↔PA 차이 = 체결 지연,  PA↔REAL 차이 = 사이징 **")
    print("  ** 거래 횟수가 1 이 아니면 재진입 — 규칙이 다르므로 수익률 비교 무의미 **")
    print("  ** CAN n=0 은 '거래 없음'이 아니라 **무효 처리됨**일 수 있다 "
          "(2026-08-13 lifecycle 498건 전량 무효) **")
    print("-" * 108)
    print(f"{'종목':<13}{'상장':<12}{'BT n':>5}{'BT %':>9}{'CAN n':>6}"
          f"{'PA n':>6}{'REAL n':>7}{'REAL $':>10}   {'진입일 (BT/CANON/PA/REAL)'}")
    print("-" * 108)
    for _, r in D.iterrows():
        flag = ""
        if r.pap_n and r.pap_n != 1:
            flag += " ⚠재진입(PAP)"
        if r.real_n and r.real_n > 2:
            flag += " ⚠재진입(REAL)"
        btr = f"{r.bt_ret:+9.2f}" if r.bt_ret is not None else f"{'—':>9}"
        print(f"{r.symbol:<13}{r.listing:<12}{str(r.bt_n or '—'):>5}{btr}"
              f"{r.pap_n:>6}{r.pa_n:>6}{r.real_n:>7}{r.real_pnl:>+10.2f}"
              f"   {r.bt_entry}/{r.pap_entry}/{r.pa_entry}/{r.real_entry}{flag}")
    print("-" * 108)
    n_re_pap = int(((D.pap_n != 1) & (D.pap_n > 0)).sum())
    n_re_pa = int((D.pa_n > 2).sum())
    n_re_real = int((D.real_n > 2).sum())
    print(f"  ** 재진입 감지 — CANON {n_re_pap}/{len(D)}  "
          f"PA(페이퍼계좌) {n_re_pa}/{len(D)}  REAL {n_re_real}/{len(D)} **")

    # 네 층이 모두 1회인 사건만이 진짜 비교 대상이다.
    clean = D[(D.bt_n == 1) & (D.pa_n == 1) & (D.real_n == 1)]
    print(f"  ** BT·PA·REAL 이 모두 1회 진입인 사건: {len(clean)}건 "
          f"{list(clean.symbol) if len(clean) else ''} **")
    for _, r in clean.iterrows():
        gap = ""
        if r.bt_entry != "—" and r.real_entry != "—":
            from datetime import date as _d
            try:
                d1 = _d.fromisoformat(str(r.bt_entry)); d2 = _d.fromisoformat(str(r.real_entry))
                gap = f"  진입 지연 {(d2 - d1).days}일"
            except Exception:
                pass
        px = ""
        if r.pa_px and r.real_px:
            px = f"  체결가 PA {r.pa_px:.6g} / REAL {r.real_px:.6g}"
            if abs(r.pa_px - r.real_px) < 1e-12:
                px += " (동일)"
        print(f"     {r.symbol}: BT {r.bt_ret:+.2f}%{gap}{px}")
    ok = D[(D.pap_n == 1) & (D.bt_n == 1)]
    if len(ok):
        d = (ok.pap_ret - ok.bt_ret)
        print(f"  1회 진입으로 일치한 {len(ok)}건 — BT vs PAP 수익률 차이 "
              f"평균 {d.mean():+.2f}%p / 최대 {d.abs().max():.2f}%p")
    else:
        print("  ** 세 층이 모두 1회 진입인 사건이 없다 — 아직 동기화 검증 불가 **")
    print("=" * 108 + "\n")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"since": args.since, "rows": rows,
                   "reentry_paper": n_re_pap, "reentry_real": n_re_real},
                  fh, indent=2, ensure_ascii=False, default=str)
    log.info("저장: %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
