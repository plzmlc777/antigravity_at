#!/usr/bin/env bash
# 신상저격수 **시간별 정합** — 청산 지연을 24시간 → 1시간으로 (2026-08-15).
#
# 왜
#     날짜 기반 청산(Day-30 시간청산 · Day-31 강제청산 · vol_cliff 조기청산)은
#     하루 1회 사이클에서만 실행돼 **트리거 후 최대 24시간** 방치됐다.
#     드라이버는 정본 없이도 `HARD_EXIT_DAYS = 31` 을 스스로 판정하므로
#     (`_session_age_days`), 매시간 돌리면 그 지연이 1시간으로 줄어든다.
#
# ⚠ 전략을 바꾸지 않는다
#     "정본이 이미 내린 결론을 더 빨리 집행"할 뿐이다. 정본 평가 주기는
#     그대로 하루 1회다. 정본 상태가 안 바뀌면 매 실행이 `in sync` 무동작이다
#     (2026-08-15 드라이런: 9세션 전부 0건 조치).
#
# ⚠ 관문을 먼저 통과해야 주문한다
#     일봉 사이클과 **같은 순서**다. 이 순서를 빼면 정본에서 이탈한 엔진으로
#     실자금이 돈다. `PIPESTATUS` 로 관문 실패를 못박는다 — `tee` 뒤의
#     종료코드를 그냥 읽으면 항상 0 이다.
#
# ⚠ 가격 기반 청산(손절·익절)은 이 스크립트와 무관하다
#     거래소 브래킷(`lifecycle_brackets.py`)이 틱 단위로 감시한다.
set -uo pipefail

# ⚠ backend/ 에서 전부 실행한다 — 관문 스크립트는 `backend/scripts/binance/`
#   아래에 있다. 저장소 루트로 올라가면 못 찾고, 그러면 (설계대로) 주문을
#   건너뛴다. 실제로 첫 실행이 그렇게 멈췄다.
cd "$(dirname "$0")/../.." || exit 1           # backend/
LOG_DIR="$(pwd)/runs/binance_paper/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_lifecycle_hourly_reconcile.log"

echo "[lifecycle-hourly] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG_FILE"

bash scripts/binance/run_engine_gates.sh fast cycle 2>&1 | tee -a "$LOG_FILE"
GATE_RC=${PIPESTATUS[0]}
if [ "$GATE_RC" -ne 0 ]; then
  echo "[lifecycle-hourly] **관문 실패 — reconcile/주문 건너뜀**" | tee -a "$LOG_FILE"
  exit 0
fi

source venv/bin/activate
PYTHONPATH=. python3 scripts/binance/lifecycle_live_signal_driver.py \
  --submit --include-real 2>&1 | tee -a "$LOG_FILE"
echo "[lifecycle-hourly] 완료" | tee -a "$LOG_FILE"
exit 0
