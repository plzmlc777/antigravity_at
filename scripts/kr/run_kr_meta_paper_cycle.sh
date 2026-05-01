#!/usr/bin/env bash
# KR Meta-Strategy paper cycle — Phase 5 wire-in.
# Wrapped by sas_loop_wrapper.sh (PATH/.env injected by wrapper).
# Recommended fire time: 17:10 KST Mon-Fri (after the existing s31 cycle).

set -uo pipefail

SESSION="${KR_META_SESSION:-061090_meta_seed}"
LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_${SESSION}.log"

echo "[kr-meta] session=${SESSION} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[kr-meta] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

PYTHONPATH=. python3 run_kr_meta_cycle.py --session "${SESSION}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[kr-meta] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
