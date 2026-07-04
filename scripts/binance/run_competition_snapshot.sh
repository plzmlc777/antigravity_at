#!/usr/bin/env bash
# Weekly competition-pool ranking snapshot (Phase 1 tournament tracking).
# Wrapped by sas_loop_wrapper.sh. Read-only — ranks Category B paper strategies
# and writes a dated snapshot (runs/competition/snapshot_YYYYMMDD.json) so the
# 2-week accumulation trajectory is recorded. No elimination (that is Phase 2).
#
# Schedule: every Monday (sas_loop_wrapper cron "10 22 * * 0" = Mon 07:10 KST).
set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_competition_snapshot.log"

echo "[competition-snapshot] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
cd "$(pwd)/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate
PYTHONPATH=. python3 -m scripts.competition_pool_report --stamp "$(date -u +%Y%m%d)" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[competition-snapshot] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
