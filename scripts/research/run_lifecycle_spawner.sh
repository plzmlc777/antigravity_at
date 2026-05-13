#!/usr/bin/env bash
# Daily auto-spawn of lifecycle paper sessions for newly listed Binance perpetuals.
# Wrapped by sas_loop_wrapper.sh.
#
# Workflow per run:
#   1. Re-fetch /fapi/v1/exchangeInfo, update listing_dates.json
#   2. Identify listings aged 1-14 days, not in blocklist (stocks/commodities),
#      not already covered by an existing paper session
#   3. Backfill that symbol's 1m ohlcv (35 days)
#   4. Create per-listing PaperSession via paper_session_cli
#
# Schedule: daily 03:00 UTC (12:00 KST) — AFTER binance-paper-cycle (02:30 UTC)
# so new sessions appear on the NEXT day's cycle (acceptable — lifecycle hold
# is 30 days, missing one day at entry is negligible).
#
# Idempotent: re-runs same day produce 0 spawns (existing sessions detected).

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_lifecycle_spawner.log"

echo "[lifecycle-spawner] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[lifecycle-spawner] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 -m scripts.research.lifecycle_session_spawner \
  --refresh-listings 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[lifecycle-spawner] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
