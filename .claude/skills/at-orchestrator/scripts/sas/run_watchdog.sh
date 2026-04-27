#!/usr/bin/env bash
# SAS pipeline watchdog — runs every 6 hours via PM2 (sas-watchdog).
#
# Sources project-root .env for TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID,
# then delegates all logic to watchdog_check.py.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOG_FILE="${RUNS_DIR}/watchdog_$(date -u +%Y%m%dT%H%M%SZ).log"

mkdir -p "${RUNS_DIR}"

# Load .env if present (gitignored — holds TELEGRAM_* secrets).
if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  set +a
fi

echo "[watchdog] start $(date -u +%Y%m%dT%H%M%SZ)" | tee -a "${LOG_FILE}"
python3 "${SCRIPT_DIR}/watchdog_check.py" 2>&1 | tee -a "${LOG_FILE}"
EXIT=${PIPESTATUS[0]}
echo "[watchdog] finished exit=${EXIT}" | tee -a "${LOG_FILE}"

# Prune logs older than 30 days
find "${RUNS_DIR}" -name 'watchdog_*.log' -mtime +30 -delete 2>/dev/null || true

exit "${EXIT}"
