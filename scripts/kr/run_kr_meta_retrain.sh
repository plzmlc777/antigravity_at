#!/usr/bin/env bash
# Weekly meta-learner retrain — rebuilds perf_matrix and atomically swaps the
# canonical model path that run_kr_meta_paper_cycle.sh consumes.
# Recommended fire time: Sundays 09:00 KST (00:00 UTC).

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_meta_retrain.log"

echo "[kr-meta-retrain] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[kr-meta-retrain] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

PYTHONPATH=. python3 retrain_meta_learner.py 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[kr-meta-retrain] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
