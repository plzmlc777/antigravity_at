"""실거래 계좌의 **시작 → 현재** 잔고. 정기 보고의 맨 앞줄.

왜 따로 두나
    전략 원장의 `자본 1.0372(+3.72%)` 는 **지수**다 — 이체·펀딩·수수료가
    섞인 실제 지갑과 다르다. 대표님이 보는 것은 "얼마 넣어서 얼마가 됐나"
    이므로, 거래소 지갑을 직접 읽어 시작액과 나란히 놓는다.

⚠ 시작액은 **입금·이체 이력에서 나온 사실**이지 추정이 아니다. 근거를
  각 항목 주석에 적어 둔다. 못 읽으면 모른다고 말한다(교훈#106).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAPI = "https://fapi.binance.com"

# 계좌 → (이름, 시작 잔고, 시작 시점, 근거)
#
# 계좌 8 — RSI 실거래 승격(2026-08-22) 시점 지갑.
#   검산: 현재 396.7393 + 이체 400.00 − 실현 45.6973 = 751.042 ✔
#   2026-09-05 에 400 을 계좌 15 로 내부이체했으므로 **현재 잔고만 보면
#   손실처럼 보인다.** 이체를 되더해야 성적이 된다.
# 계좌 15 — 속도저울 서브계정(atglive2) 개설 입금.
#   2026-09-05 마스터(계좌 8)에서 내부이체 400 USDT.
SEEDS = {
    8: ("RSI 극단 (1군)", 751.04, "2026-08-22", -400.00),
    # 갈래가 두 번 바뀌었다. 계좌는 그대로이므로 시작액 400 은 안 바뀐다.
    #   2026-09-07 22:03 속도저울(s2both) → 탄성저울(imp3s)
    #   2026-09-08 22:xx 탄성저울 → **균형저울**(bal6 = kine/6슬롯/240분)
    #     탄성저울은 승격 근거(한 주 전진)가 139주 아카이브에서 무너져 중단.
    #     구간 성적: 09-05~09-08 자본 +3.51%(현금 414.06 으로 확정).
    15: ("균형저울 (1군)", 400.00, "2026-09-05", 0.0),
}


def _keys(account_id: int):
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import text

    from app.core.security import decrypt_key
    from app.db.session import engine
    with engine.connect() as c:
        r = c.execute(text("select encrypted_access_key, encrypted_secret_key "
                           "from exchange_accounts where id=:i"),
                      {"i": account_id}).fetchone()
    if not r:
        raise RuntimeError(f"계좌 {account_id} 없음")
    return decrypt_key(r[0]), decrypt_key(r[1])


def wallet(account_id: int):
    """(지갑, 미실현, 순자산). 못 읽으면 None — **0 으로 뭉개지 않는다.**"""
    try:
        ak, sk = _keys(account_id)
        p = {"timestamp": int(time.time() * 1000), "recvWindow": 10000}
        qs = urllib.parse.urlencode(p)
        sig = hmac.new(sk.encode(), qs.encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(f"{FAPI}/fapi/v2/account?{qs}&signature={sig}",
                                     headers={"X-MBX-APIKEY": ak})
        with urllib.request.urlopen(req, timeout=20) as r:
            a = json.load(r)
        return (float(a["totalWalletBalance"]),
                float(a["totalUnrealizedProfit"]),
                float(a["totalMarginBalance"]))
    except Exception as exc:                                  # noqa: BLE001
        print(f"  ⚠ 계좌 {account_id} 조회 실패 — **모른다**: {str(exc)[:120]}")
        return None


def render(only: int | None = None) -> None:
    rows = []
    for aid, (name, seed, since, moved) in SEEDS.items():
        if only is not None and aid != only:
            continue
        w = wallet(aid)
        if w is None:
            rows.append([str(aid), name, f"{seed:.2f}", "조회실패", "—", "—"])
            continue
        bal, _unreal, equity = w
        # 이체를 되더해야 성적이 된다 — 옮긴 돈은 잃은 돈이 아니다
        adj = equity - moved
        pnl = adj - seed
        rows.append([str(aid), name, f"{seed:.2f}", f"{equity:.2f}",
                     (f"{moved:+.2f}" if moved else "—"),
                     f"{pnl:+.2f} ({pnl / seed * 100:+.2f}%)"])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from report_box import render as box
    print(box(["계좌", "트랙", "시작", "현재(순자산)", "이체", "손익"], rows))
    if any(r[4] != "—" for r in rows):
        print("  ※ 이체가 있는 계좌는 옮긴 돈을 되더해 손익을 냈다 — "
              "현재 잔고만 보면 손실로 보인다.")


if __name__ == "__main__":
    render(int(sys.argv[1]) if len(sys.argv) > 1 else None)
