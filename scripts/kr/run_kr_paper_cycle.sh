#!/usr/bin/env bash
# KR EOD paper cycle — wrapped by sas_loop_wrapper.sh (PATH/.env injected by wrapper).
# Invocation: sas_loop_wrapper.sh "0 8 * * 1-5" scripts/kr/run_kr_paper_cycle.sh
#
# 17:00 KST (08:00 UTC) Mon-Fri 이 권장 발화 시각 (장마감 15:30 KST + 90분 여유)

set -uo pipefail

SESSION="${KR_PAPER_SESSION:-061090_s2_seed}"
LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_${SESSION}.log"

echo "[kr-paper] session=${SESSION} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

# venv 활성화
if [ ! -f venv/bin/activate ]; then
  echo "[kr-paper] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

PYTHONPATH=. python3 run_kr_paper_cycle.py --session "${SESSION}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[kr-paper] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
