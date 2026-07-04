#!/usr/bin/env bash
# Monthly paper-mode report (Category A/B split) → Telegram.
# Wrapped by sas_loop_wrapper.sh. Read-only — aggregates SessionStore paper
# trades by category and telegrams the REAL alert chats. No trading.
set -uo pipefail
LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_paper_monthly_report.log"
echo "[paper-monthly-report] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
cd "$(pwd)/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate
PYTHONPATH=. python3 -m scripts.paper_report --period month 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[paper-monthly-report] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
