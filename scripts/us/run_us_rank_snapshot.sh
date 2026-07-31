#!/usr/bin/env bash
# 미국 ETF 순위정보 일일 스냅샷 수집.
# Wrapped by sas_loop_wrapper.sh.
#
# 왜 매일인가: 키움 순위 API 는 조회 시점 값만 주고 과거 시계열이 없다.
# 키움 거래상위(한국 개인 수급)·주간거래 괴리율(Blue Ocean vs 정규장)은
# 미국 현지 데이터에 없는 고유 substrate 라, 오늘 안 받으면 영영 못 쓴다.
#
# Schedule: daily 21:10 UTC
#   서머타임 미국 정규장 마감 20:00 UTC(05:00 KST) → 70분 후
#   표준시              마감 21:00 UTC(06:00 KST) → 10분 후
#   두 체제 모두 마감 이후를 보장한다.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/us_rank_snapshot/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_us_rank_snapshot.log"

echo "[us-rank-snapshot] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[us-rank-snapshot] ERROR: venv not found" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 -m scripts.collect_us_rank_snapshot 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[us-rank-snapshot] exit_code=${EC}" | tee -a "${LOG_FILE}"

# 일봉도 같이 갱신 — 확정된 마지막 영업일까지만 저장된다(미완결 배제 내장)
PYTHONPATH=. python3 -m scripts.backfill_us_daily --years 0.2 2>&1 | tee -a "${LOG_FILE}"
echo "[us-rank-snapshot] daily_refresh_exit=${PIPESTATUS[0]}" | tee -a "${LOG_FILE}"

find "${LOG_DIR}" -name '*_us_rank_snapshot.log' -mtime +90 -delete 2>/dev/null || true

exit "${EC}"
