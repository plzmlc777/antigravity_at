#!/usr/bin/env bash
# 일일 1군/2군 리포트 → 텔레그램.
#
# 3군 자동 디스패치(paradigm-dispatch-daily)를 2026-08-13 에 정지하면서 매일 오던
# 텔레그램이 끊겼다. 그 자리를 이 리포트가 채운다. 주간·월간 리포트와 같은 아침
# 시간대(07:00~07:20 KST)에 보낸다 — 스케줄 '15 22 * * *' UTC = 07:15 KST.
#
# 읽기 전용이다. 계좌 조회 1회 + DB 읽기. 거래하지 않는다.
set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_daily_tier_report.log"

echo "[daily-tier-report] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
cd "$(pwd)/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate
PYTHONPATH=. python3 -m scripts.daily_tier_report 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[daily-tier-report] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
