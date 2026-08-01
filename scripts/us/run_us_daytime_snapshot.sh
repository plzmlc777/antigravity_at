#!/usr/bin/env bash
# 한국 주간거래(Blue Ocean) 세션 중에만 얻을 수 있는 순위 지표 수집.
# Wrapped by sas_loop_wrapper.sh.
#
# 왜 별도 cron 인가 (2026-08-01 실측):
#   usa24291(주간거래 괴리율)은 한국 주간거래 세션(09:00~16:45 KST) 중에만
#   데이터를 반환한다. 16:07 KST 수집 시 100건 / 06:10 KST 수집 시 0건.
#   Blue Ocean 오버나이트 세션의 실시간 괴리를 재는 지표라 세션이 닫히면 값이 없다.
#   미국 마감 후에 도는 us-rank-snapshot 으로는 영영 수집할 수 없어 창을 분리했다.
#
# Schedule: 평일 07:30 UTC (16:30 KST) — 주간거래 종료(16:45 KST) 직전.
#   세션이 없는 날(미국 휴장 등)에는 0건이 정상이며 실패로 보지 않는다.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/us_rank_snapshot/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_us_daytime_snapshot.log"

echo "[us-daytime-snapshot] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[us-daytime-snapshot] ERROR: venv not found" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 -m scripts.collect_us_rank_snapshot --window daytime 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[us-daytime-snapshot] exit_code=${EC}" | tee -a "${LOG_FILE}"

find "${LOG_DIR}" -name '*_us_daytime_snapshot.log' -mtime +90 -delete 2>/dev/null || true

exit "${EC}"
