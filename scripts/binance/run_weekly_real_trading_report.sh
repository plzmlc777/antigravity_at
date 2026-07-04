#!/usr/bin/env bash
# Weekly REAL trading report → Telegram (week-over-week comparison).
# Wrapped by sas_loop_wrapper.sh. Read-only DB + one exchange balance query.
# Computes the last 7 days' realized-PnL stats for acct8, compares to the prior
# 7 days, and telegrams the REAL alert chats. No trading.
#
# Schedule: every Monday (sas_loop_wrapper cron "0 22 * * 0" = Sun 22:00 UTC =
# Mon 07:00 KST).
set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_weekly_real_report.log"

echo "[weekly-real-report] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
cd "$(pwd)/backend" || exit 1
# shellcheck disable=SC1091
source venv/bin/activate
PYTHONPATH=. python3 -m scripts.real_trading_report --period week 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[weekly-real-report] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
