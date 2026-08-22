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
