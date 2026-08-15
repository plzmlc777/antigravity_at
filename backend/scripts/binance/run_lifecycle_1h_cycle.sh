#!/usr/bin/env bash
# 신상저격수 **1시간 사이클** — 페이퍼 전용 (2026-08-15 신설).
#
# ⚠ 실거래를 건드리지 않는다
#     이 스크립트는 `lifecycle_live_signal_driver.py` 를 **부르지 않는다.**
#     1h 세션은 아직 검증 전이므로 정본만 굴리고 실계좌 연결은 별도 단계다.
#     일봉 사이클(`run_binance_paper_cycle.sh`)이 실거래를 계속 담당한다.
#
# ⚠ 왜 별도 사이클인가
#     정본을 1h 로 평가하려면 **1시간마다** 돌아야 한다. 일봉 사이클(하루 1회)
#     로는 1h 세션이 하루 한 번만 전진해 해상도가 무의미해진다.
#
# 순서
#   1) 1h 봉 수집 (REST, 마감된 봉만)
#   2) 이름에 `_1h` 가 든 활성 세션만 골라 사이클 실행
#
# ⚠ 데이터가 없으면 세션을 돌리지 않는다 — 빈 eval 로 돌면 NaN 예측이
#   멀쩡한 상태를 덮어쓸 수 있다(2026-08-15 DOSUSDT 사례).
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1          # backend/
source venv/bin/activate
export PYTHONPATH=.

LOG_DIR="$(pwd)/runs/binance_paper/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_lifecycle_1h_cycle.log"

echo "[lifecycle-1h] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

# ── 1) 1h 봉 수집 ────────────────────────────────────────────────────
# 최근 72시간이면 결손·재시작을 넉넉히 메운다. 마감된 봉만 들어간다.
python3 -m scripts.collect_ohlcv_hourly --live 72 2>&1 | tee -a "$LOG_FILE"
COLLECT_RC=${PIPESTATUS[0]}
if [ "$COLLECT_RC" -ne 0 ]; then
  echo "[lifecycle-1h] 수집 실패(rc=$COLLECT_RC) — 세션 실행을 건너뛴다" \
    | tee -a "$LOG_FILE"
  exit 1
fi

# ── 2) `_1h` 활성 세션만 실행 ────────────────────────────────────────
IDS=$(python3 - <<'PY'
import glob, json, os
out = []
for f in glob.glob("runs/paper_sessions/*/session.json"):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if d.get("status") != "active":
        continue
    n = d.get("name") or ""
    if "lifecycle" in n and "_1h" in n:
        out.append(d["session_id"])
print(" ".join(sorted(out)))
PY
)

if [ -z "$IDS" ]; then
  echo "[lifecycle-1h] 실행할 1h 세션이 없다 — 정상 종료" | tee -a "$LOG_FILE"
  exit 0
fi

N=0
for ID in $IDS; do
  python3 -m scripts.paper_session_cli run --id "$ID" 2>&1 | tee -a "$LOG_FILE"
  N=$((N + 1))
done
echo "[lifecycle-1h] 세션 $N 개 실행 완료" | tee -a "$LOG_FILE"
exit 0
