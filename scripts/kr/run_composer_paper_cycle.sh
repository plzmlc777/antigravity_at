#!/usr/bin/env bash
# Composer Phase 6 — daily paper trading cycle for all active sessions.
# Wrapped by sas_loop_wrapper.sh.
#
# Runs: paper_session_cli run --all
# Reads each session's pipeline_spec, builds runtime data (OHLCV from DB,
# pre-scanned signals, KR investor flow), fits/predicts, applies policy,
# persists state.
#
# Recommended schedule: daily 16:50 KST (07:50 UTC) — runs 20 minutes after
# the flow-backfill so ka10059 data is fresh when features are built.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_composer_paper_cycle.log"

echo "[composer-paper] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[composer-paper] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 -m scripts.paper_session_cli run --all 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[composer-paper] exit_code=${EC}" | tee -a "${LOG_FILE}"

# Append a status snapshot for monitoring
echo "" | tee -a "${LOG_FILE}"
echo "[composer-paper] post-cycle status:" | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.paper_session_cli status 2>&1 | tee -a "${LOG_FILE}"

exit "${EC}"
