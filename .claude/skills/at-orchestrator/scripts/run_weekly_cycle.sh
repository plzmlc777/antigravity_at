#!/usr/bin/env bash
# run_weekly_cycle.sh — One-shot runner for the weekly LEARN→EVOLVE→REFLECT cycle.
#
# Designed to be invoked by PM2 cron_restart. Generates the prompt via
# weekly_cycle.sh, pipes it through `claude -p`, and writes a timestamped
# log under .claude/skills/at-orchestrator/runs/.
#
# Usage:
#   ./run_weekly_cycle.sh                # run now
#   PM2 cron_restart: '7 9 * * 0'        # auto-run Sundays 09:07 local time

set -euo pipefail

PROJECT_ROOT="/home/hcpark/antigravity"
SCRIPT_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/scripts"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs"
LOCK_FILE="${RUNS_DIR}/.weekly_cycle.lock"

mkdir -p "${RUNS_DIR}"

# Single-instance guard: refuse to start if a previous run is still in progress.
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[run_weekly_cycle] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/cycle_${TIMESTAMP}.log"

echo "[run_weekly_cycle] starting at ${TIMESTAMP}"
echo "[run_weekly_cycle] log: ${LOG_FILE}"

# Build the prompt and submit it. claude is expected to be on PATH.
PROMPT="$(bash "${SCRIPT_DIR}/weekly_cycle.sh")"

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[run_weekly_cycle] finished with exit ${EXIT_CODE}"

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'cycle_*.log' -mtime +90 -delete 2>/dev/null || true

# PM2 cron_restart reschedules on exit, so a clean exit is fine.
exit ${EXIT_CODE}
