"""운동학 1군 한 화면 점검 — 정기 보고의 자료원.

RSI 의 `rsi_watch.sh` 와 같은 자리다. 페이퍼(대조군)와 실거래를 나란히
놓고, **거래소 원본**으로 장부를 대조한다.

⚠ 거래소 조회는 asyncio 어댑터를 쓰지 않는다. 점검기가 실거래 프로세스와
  같은 전역 HTTP 클라이언트를 건드리면 `bound to a different event loop`
  로 죽는다(2026-09-05 실측). 서명 요청을 urllib 로 직접 만든다 —
  조회 전용이라 이 정도가 안전하다.

⚠ 못 읽으면 **모른다고 말한다.** 빈 결과로 뭉개면 살아 있는 포지션이
  없는 것처럼 보인다(교훈#106).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# ⚠ 갈래를 바꾸면 **여기도 바꿔야 한다.** 안 바꾸면 옛 경로를 읽어
#   "거래 0"으로 조용히 보고한다(교훈#102 — 보고는 없어져도 조용하다).
#   환경변수로 덮을 수 있게 두어 교체 때 코드 수정 없이 넘어간다.
TRACK = os.environ.get("KINE_TRACK", "imp3s")
# 사람이 읽는 이름. 갈래를 바꾸면 여기도 바뀌어야 보고가 안 헷갈린다.
NAMES = {"s2both": "속도저울", "imp3s": "탄성저울", "bal6": "균형저울",
         # imp3ns(버팀저울) = 무손절 판본. 2026-09-09 09:17~09:52 만 가동하고
         # 근거가 무너져 5% 손절 판본(=탄성저울)으로 되돌렸다.
         "imp3ns": "버팀저울"}
# 실거래 경로명과 페이퍼 경로명이 **다르다.** 균형저울의 대조군 페이퍼는
# `s6both_h240` 이다 — 여기를 안 채우면 페이퍼 칸이 조용히 빈다(교훈#102).
# ⚠ 버팀저울(imp3ns)의 대조군 페이퍼 s3short_imp 는 **5% 손절이 있다.**
#   실거래는 무손절이라 같은 규칙이 아니다 — 나란히 볼 때 그걸 기억하라.
PAPER_OF = {"bal6": "s6both_h240", "imp3ns": "s3short_imp",
            "imp3s": "s3short_imp"}
NAME = os.environ.get("KINE_NAME") or NAMES.get(TRACK, TRACK)
PAPER_TRACK = os.environ.get("KINE_PAPER_TRACK", PAPER_OF.get(TRACK, TRACK))
PAPER = ROOT / "runs" / "kinematics_paper" / PAPER_TRACK
LIVE = ROOT / "runs" / "kinematics_live" / TRACK
ACCOUNT = int(os.environ.get("KINE_ACCOUNT", "15"))
FAPI = "https://fapi.binance.com"


def _keys(account_id: int) -> tuple[str, str]:
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import text

    from app.core.security import decrypt_key
    from app.db.session import engine
    with engine.connect() as c:
        r = c.execute(text("select encrypted_access_key, encrypted_secret_key "
                           "from exchange_accounts where id=:i"),
                      {"i": account_id}).fetchone()
    if not r:
        raise SystemExit(f"계좌 {account_id} 없음")
    return decrypt_key(r[0]), decrypt_key(r[1])


def _get(ak: str, sk: str, path: str, params: dict | None = None):
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    p["recvWindow"] = 5000
    qs = urllib.parse.urlencode(p)
    sig = hmac.new(sk.encode(), qs.encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{FAPI}{path}?{qs}&signature={sig}",
                                 headers={"X-MBX-APIKEY": ak})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def _state(d: Path) -> dict | None:
    try:
        return json.loads((d / "state.json").read_text())
    except Exception:                                     # noqa: BLE001
        return None


def _ledger(d: Path):
    import pandas as pd
    f = d / "trades.csv"
    if not f.exists():
        return None
    try:
        return pd.read_csv(f)
    except Exception:                                     # noqa: BLE001
        return None


def main() -> int:
    # 계좌 잔고 — 전략 원장의 자본 지수와 다르다. 대표님이 보는 것은
    # "얼마 넣어서 얼마가 됐나"다.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from account_ledger import render as _acct
    _acct(ACCOUNT)
    print()
    print(f"=== {NAME}({TRACK}) · 페이퍼 대 실거래 ===")
    rows = []
    for lab, d in (("페이퍼", PAPER), ("실거래", LIVE)):
        st = _state(d)
        t = _ledger(d)
        if st is None:
            rows.append([lab, "—", "—", "—", "—", "상태파일 없음"])
            continue
        n = int(st.get("n_trades", 0))
        eq = float(st.get("equity", 1.0))
        per = f"{t.net_pct.mean():+.3f}%" if t is not None and len(t) else "—"
        note = "표본 30건 미만 — 어떤 차이도 잡음" if n < 30 else ""
        rows.append([lab, str(n), f"{eq:.6f}", f"{(eq - 1) * 100:+.2f}%",
                     per, note])
    # ⚠ 한글은 **두 칸**이다. len() 으로 맞추면 표가 깨진다 —
    #   report_box 가 이미 그 계산을 갖고 있으니 자체 구현하지 않는다.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report_box import render
    print(render(["", "거래", "자본", "수익률", "거래당", "비고"], rows,
                 wraps=[999] * 5 + [22], wrap_center=[5]))

    # ── 실거래 마찰 실측 (문서 §6)
    t = _ledger(LIVE)
    if t is not None and len(t):
        print("\n=== 실측 마찰 (문서 §6) ===")
        if "fee_pct" in t:
            print(f"  수수료   평균 {t.fee_pct.mean():.4f}%  "
                  f"(명세 가정 0.072%)")
        if "slip_bp" in t:
            print(f"  슬리피지 평균 {t.slip_bp.mean():+.2f}bp · "
                  f"중앙 {t.slip_bp.median():+.2f}bp")
        if "stopped" in t:
            print(f"  손절 발동 {int(t.stopped.fillna(False).astype(bool).sum())}"
                  f" / {len(t)}")

    # ── 보유 · 거래소 대조
    st = _state(LIVE)
    book = {p["symbol"]: p for p in (st or {}).get("positions") or []}
    print("\n=== 거래소 원본 (계좌 15) ===")
    try:
        ak, sk = _keys(ACCOUNT)
        a = _get(ak, sk, "/fapi/v2/account")
        algos = _get(ak, sk, "/fapi/v1/openAlgoOrders")
    except Exception as exc:                              # noqa: BLE001
        print(f"  ⚠ **조회 실패 — 모른다.** 장부만 보고 판단하지 마라: "
              f"{str(exc)[:160]}")
        return 1
    print(f"  지갑 {a['totalWalletBalance']} · 가용 {a['availableBalance']} "
          f"· 미실현 {a['totalUnrealizedProfit']}")
    ex = {}
    for p in a["positions"]:
        q = float(p.get("positionAmt", 0) or 0)
        if q:
            ex[p["symbol"]] = q
            b = book.get(p["symbol"])
            print(f"  {p['symbol']:<14}{q:+12.6g} @ {p['entryPrice']} · "
                  f"{p['leverage']}x · 미실현 {p['unrealizedProfit']}"
                  + (f" · 청산예정 {b['exit_ts']}" if b else " · ⚠ 장부에 없음"))
    prot = {o.get("symbol") for o in algos}
    for s in ex:
        if s not in prot:
            print(f"  🚨 {s} — **손절 주문이 없다. 보호 없는 포지션.**")
    if not ex:
        print("  포지션 없음")
    print(f"  조건부 주문(손절) {len(algos)}건: "
          f"{', '.join(sorted(prot)) if prot else '없음'}")
    if set(ex) == set(book):
        print("  ✔ 장부와 일치")
    else:
        print(f"  ⚠ **불일치** — 장부 {sorted(book)} / 거래소 {sorted(ex)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
