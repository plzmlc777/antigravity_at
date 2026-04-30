#!/usr/bin/env bash
# SAS pipeline watchdog — runs every 6 hours via PM2 (sas-watchdog).
#
# Telegram credentials are loaded from DB (exchange_accounts), NOT .env.
# .env contains only system config (POSTGRES_*, ports).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOG_FILE="${RUNS_DIR}/watchdog_$(date -u +%Y%m%dT%H%M%SZ).log"

mkdir -p "${RUNS_DIR}"

# Load .env (system config only) if present.
if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  set +a
fi

# Load Telegram creds from DB (manual-trigger fallback — wrapper does it too).
if [ -x "${PROJECT_ROOT}/backend/venv/bin/python3" ]; then
  TG_EXPORTS=$(cd "${PROJECT_ROOT}/backend" && PYTHONPATH=. ./venv/bin/python3 "${SCRIPT_DIR}/load_telegram_creds.py" 2>/dev/null || true)
  if [ -n "${TG_EXPORTS}" ]; then
    eval "${TG_EXPORTS}"
  fi
fi

echo "[watchdog] start $(date -u +%Y%m%dT%H%M%SZ)" | tee -a "${LOG_FILE}"
python3 "${SCRIPT_DIR}/watchdog_check.py" 2>&1 | tee -a "${LOG_FILE}"
EXIT=${PIPESTATUS[0]}
echo "[watchdog] finished exit=${EXIT}" | tee -a "${LOG_FILE}"

# Prune logs older than 30 days
find "${RUNS_DIR}" -name 'watchdog_*.log' -mtime +30 -delete 2>/dev/null || true

exit "${EXIT}"
