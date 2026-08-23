#!/usr/bin/env bash
# RSI 트랙 한 화면 점검 — 실거래(1군) · 그림자(2군) · 백테스트.
#
# 30분마다 사람이 읽는 용도다. 그래서 **판정에 필요한 것만** 찍는다.
#   ① 3자 비교 (rsi_three_way) — 총손익·익절비중·청산 slip·포착
#   ② 세션 계정 — 거절 사유 4종·탭 결손·보유 슬롯
#   ③ 살아 있는가 — 프로세스·비상정지 플래그·거래소 포지션 수
#
# ⚠ 여기서 숫자를 **해석하지 않는다.** 표본 30건 미만이면 어떤 차이도
#   잡음이라는 것은 판독기가 이미 찍는다. 이 파일은 모으기만 한다.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1          # backend/
export PYTHONPATH=.

echo "=== RSI 트랙 점검 · $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S KST') ==="
echo

venv/bin/python3 -m scripts.binance.rsi_three_way 2>&1

echo
echo "=== 세션 계정 ==="
venv/bin/python3 - <<'PY'
import json
from pathlib import Path
ROOT = Path("runs/paper_sessions/rsi_extreme")
KEYS = [("n_signal", "신호"), ("n_fill", "체결"), ("n_skip", "슬롯포화"),
        ("n_pricefail", "시세실패"), ("n_reject_order", "주문거절"),
        ("n_reject_tp", "익절거절"), ("n_kernelfail", "커널실패"),
        ("n_slipreject", "괴리거부"), ("n_tapmiss", "탭결손")]
rows = [("실거래", "5m_rsi10_cb_nosl_LIVE"), ("그림자", "5m_rsi10_cb_nosl_SHADOW"),
        ("구규약", "5m_rsi10")]
print("%-8s %6s %6s %8s %8s %8s %8s %8s %8s %7s %6s" %
      ("세션", "신호", "체결", "슬롯포화", "시세실패", "주문거절",
       "익절거절", "커널실패", "괴리거부", "탭결손", "보유"))
for label, name in rows:
    f = ROOT / name / "state.json"
    if not f.exists():
        print("%-8s  (상태 파일 없음 — %s)" % (label, name)); continue
    d = json.loads(f.read_text())
    print("%-8s %6d %6d %8d %8d %8d %8d %8d %8d %7d %6d" % (
        label, *[int(d.get(k, 0)) for k, _ in KEYS], len(d.get("pos", []))))
PY

echo
# ⚠ 보유 포지션과 **중간 손익** (2026-08-23 대표님 지시)
#   손절이 없으므로 미실현은 익절(+5%)이나 24시간 상한까지 확정되지 않는다.
#   그래서 실현만 보면 진행 중인 위험이 안 보인다 — 둘을 같이 찍는다.
#   실거래는 우리 장부와 **거래소 원본**을 나란히 놓는다. 어긋나면 그
#   자체가 사건이다(2026-07-27 고아 포지션 사고).
venv/bin/python3 - <<'PY'
import json, sys, logging, urllib.request
from datetime import datetime, timezone
from pathlib import Path

logging.disable(logging.INFO)
ROOT = Path("runs/paper_sessions/rsi_extreme")
SESS = [("실거래", "5m_rsi10_cb_nosl_LIVE"), ("그림자", "5m_rsi10_cb_nosl_SHADOW"),
        ("구규약", "5m_rsi10")]

px = {d["symbol"]: float(d["price"]) for d in json.load(
    urllib.request.urlopen("https://fapi.binance.com/fapi/v1/ticker/price", timeout=20))}
now = datetime.now(timezone.utc)

print("=== 보유 포지션 · 중간 손익 ===")
any_pos = False
for label, name in SESS:
    f = ROOT / name / "state.json"
    if not f.exists():
        continue
    st = json.loads(f.read_text())
    pos, realized = st.get("pos", []), float(st.get("equity", 0.0))
    unreal = 0.0
    if pos:
        any_pos = True
        print("  [%s]" % label)
        for p in pos:
            cur = px.get(p["symbol"], 0.0)
            ent, qty = float(p["entry_price"]), float(p["qty"])
            ret = (cur / ent - 1) if ent else 0.0
            pnl = qty * (cur - ent)
            unreal += pnl
            held = (now - datetime.fromisoformat(p["entry_ts"])).total_seconds() / 3600
            tp = float(p.get("tp_price") or 0)
            print("    %-12s 진입 %-10.8g 현재 %-10.8g 평가 %+6.2f%% (%+.4f$) "
                  "· 익절까지 %+5.2f%% · 보유 %4.1f/24.0h"
                  % (p["symbol"], ent, cur, 100 * ret, pnl,
                     100 * (tp / cur - 1) if (tp and cur) else 0.0, held))
    print("  %-6s 실현 %+8.4f$ · 미실현 %+8.4f$ · 합계 %+8.4f$   (보유 %d)"
          % (label, realized, unreal, realized + unreal, len(pos)))
if not any_pos:
    print("  (보유 없음 — 미실현 0)")

# ── 거래소 원본 대조 (실거래만) ────────────────────────────────────
print()
print("=== 거래소 원본 (계좌 8) ===")
try:
    sys.path.insert(0, "scripts/binance")
    from rsi_live_broker import LiveBroker, _run
    from app.adapters.binance_futures import FAPI_V2
    b = LiveBroker(account_id=8, notional_usd=9.4, dry_run=True)
    b.connect()
    rows = _run(b._adapter._signed_get(f"{FAPI_V2}/positionRisk", {}))
    ex = {r["symbol"]: r for r in (rows or [])
          if abs(float(r.get("positionAmt", 0) or 0)) > 0}
    if not ex:
        print("  포지션 없음")
    for s, r in ex.items():
        print("  %-12s 수량 %.6f · 진입 %.8g · 마크 %.8g · 평가 %+.4f USDT · %sx"
              % (s, float(r["positionAmt"]), float(r["entryPrice"]),
                 float(r["markPrice"]), float(r["unRealizedProfit"]), r.get("leverage")))
    oo = b.open_orders()
    print("  미체결 익절 지정가: %s" % ({k: [round(o.price, 8) for o in v]
                                        for k, v in oo.items()} or "없음"))
    # 장부 ↔ 거래소
    book = {p["symbol"] for p in json.loads(
        (ROOT / "5m_rsi10_cb_nosl_LIVE" / "state.json").read_text()).get("pos", [])}
    if book != set(ex):
        print("  ⚠ **불일치** — 장부 %s / 거래소 %s" % (sorted(book), sorted(ex)))
    else:
        print("  ✔ 장부와 일치")
except Exception as exc:                                        # noqa: BLE001
    print("  조회 실패: %s" % exc)
PY

echo "=== 살아 있는가 ==="
pm2 jlist 2>/dev/null | venv/bin/python3 -c "
import json, sys
for p in json.load(sys.stdin):
    if p['name'].startswith('rsi-5m'):
        e = p['pm2_env']
        up = int((__import__('time').time()*1000 - e.get('pm_uptime', 0)) / 60000)
        print('  %-22s %-9s 재기동 %s · %d분 가동' %
              (p['name'], e['status'], e.get('restart_time'), up))
"
PGPASSWORD=antigravity_password psql -U antigravity_user -h localhost \
  -d antigravity_db -P pager=off -t -A -F' · ' -c \
  "select '  비상정지 플래그 orders_enabled=' || orders_enabled ||
          ' · status=' || status
     from live_bot_sessions where id = '5m_rsi10_cb_nosl_LIVE';" 2>/dev/null
