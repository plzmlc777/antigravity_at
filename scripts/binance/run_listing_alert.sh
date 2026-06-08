#!/usr/bin/env bash
# Binance new/upcoming crypto listing alert (lifecycle REAL trigger).
# Wrapped by sas_loop_wrapper.sh. Read-only — polls exchangeInfo, telegrams 7899
# on a newly-detected crypto perp listing. No trading. Idempotent (seen-state JSON).
#
# Schedule: every 6 hours (sas_loop_wrapper cron "0 */6 * * *").
set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_listing_alert.log"

echo "[listing-alert] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
cd "$(pwd)/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate
PYTHONPATH=. python3 -m scripts.binance.listing_alert 2>&1 | tee -a "${LOG_FILE}"
