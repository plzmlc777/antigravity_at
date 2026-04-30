#!/usr/bin/env bash
# KR daily dynamic selection — 7 strategies × last 30 days → top 1 + persist report.
# Invocation: sas_loop_wrapper.sh "0 9 * * 1-5" scripts/kr/run_kr_selector.sh
#
# 18:00 KST (09:00 UTC) Mon-Fri.

set -uo pipefail

SYMBOL="${KR_SELECTOR_SYMBOL:-061090}"
LOG_DIR="$(pwd)/backend/runs/kr_paper/selector"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_${SYMBOL}.log"
JSON_FILE="${LOG_DIR}/latest_${SYMBOL}.json"

echo "[kr-selector] symbol=${SYMBOL} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1
source venv/bin/activate

PYTHONPATH=. python3 run_kr_selector.py --symbol "${SYMBOL}" --output "${JSON_FILE}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[kr-selector] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
