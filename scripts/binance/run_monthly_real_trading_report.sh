#!/usr/bin/env bash
# Monthly REAL trading report → Telegram (month-over-month comparison).
# Wrapped by sas_loop_wrapper.sh. Read-only DB + one exchange balance query.
# Computes last complete calendar month's realized-PnL stats for acct8, compares
# to the prior month, and telegrams the REAL alert chats. No trading.
#
# Schedule: 1st of each month (sas_loop_wrapper cron "0 9 1 * *" = 18:00 KST).
set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_monthly_real_report.log"

echo "[monthly-real-report] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
cd "$(pwd)/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate
PYTHONPATH=. python3 -m scripts.monthly_real_trading_report 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[monthly-real-report] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
