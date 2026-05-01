#!/usr/bin/env bash
# Weekly meta-learner retrain — rebuilds perf_matrix and atomically swaps the
# canonical model path that run_kr_meta_paper_cycle.sh consumes.
# Recommended fire time: Sundays 09:00 KST (00:00 UTC).
#
# Per-symbol mode: KR_META_RETRAIN_SYMBOL=<symbol> (e.g. 005930) → versioned
#   canonical at runs/kr_paper/models/meta_lgbm_<symbol>.pkl
# Legacy mode (env unset): default symbol+canonical inside retrain_meta_learner.py.

set -uo pipefail

SYMBOL="${KR_META_RETRAIN_SYMBOL:-}"
LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LABEL="${SYMBOL:-default}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_meta_retrain_${LABEL}.log"

echo "[kr-meta-retrain] symbol=${LABEL} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[kr-meta-retrain] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

if [ -z "$SYMBOL" ]; then
  PYTHONPATH=. python3 retrain_meta_learner.py 2>&1 | tee -a "${LOG_FILE}"
else
  PYTHONPATH=. python3 retrain_meta_learner.py \
    --symbol "$SYMBOL" \
    --canonical "runs/kr_paper/models/meta_lgbm_${SYMBOL}.pkl" \
    --matrix-out "perf_matrix_${SYMBOL}_latest.jsonl" 2>&1 | tee -a "${LOG_FILE}"
fi
EC="${PIPESTATUS[0]}"
echo "[kr-meta-retrain] symbol=${LABEL} exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
