#!/usr/bin/env bash
# SISDS live monitor — Phase 6 (CIO-20260410-001).
#
# Daily check of all live-stage strategies:
# Job 1: Activate (live, pending) after user approval
# Job 2: Monitor (live, running) for degradation
# Job 3: Enforce grace period for (live, degraded)
#
# Schedule: 0 6 * * * UTC (15:00 KST daily)
# Lightweight — haiku model, fast checks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.livemon.lock"
API="http://localhost:8001/api/v1"

mkdir -p "${RUNS_DIR}"

if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-livemon] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/livemon_${TIMESTAMP}.log"

echo "[sas-livemon] start ${TIMESTAMP}"
echo "[sas-livemon] log ${LOG_FILE}"

# Quick check: any live-stage entries at all?
LIVE_PENDING=$(curl -s "${API}/strategy-audition/by-stage?stage=live&stage_status=pending&limit=5" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
LIVE_RUNNING=$(curl -s "${API}/strategy-audition/by-stage?stage=live&stage_status=running&limit=10" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
LIVE_DEGRADED=$(curl -s "${API}/strategy-audition/by-stage?stage=live&stage_status=degraded&limit=10" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

TOTAL=$((LIVE_PENDING + LIVE_RUNNING + LIVE_DEGRADED))

if [ "${TOTAL}" -eq "0" ]; then
  echo "[sas-livemon] no live-stage entries (pending=${LIVE_PENDING} running=${LIVE_RUNNING} degraded=${LIVE_DEGRADED})"
  exit 0
fi

echo "[sas-livemon] live entries: pending=${LIVE_PENDING} running=${LIVE_RUNNING} degraded=${LIVE_DEGRADED}"

PROMPT=$(cat <<PROMPT_EOF
SISDS Live Monitor (Phase 6). PM2 daily cron, no user.

Dispatch Agent(subagent_type="live-monitor") with prompt:
"Run all 3 jobs from live-monitor.md:
 Job 1: Activate (live, pending) entries.
 Job 2: Monitor (live, running) for degradation (rules D1-D5).
 Job 3: Enforce grace period for (live, degraded).
 Return your summary JSON."

After the subagent returns, emit exactly ONE line starting with "SAS_LIVEMON_RESULT:" summarizing activated/healthy/degraded/demoted counts.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model haiku \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-livemon] finished exit=${EXIT_CODE}"

tail -3 "${LOG_FILE}" 2>/dev/null || true

find "${RUNS_DIR}" -name 'livemon_*.log' -mtime +90 -delete 2>/dev/null || true

exit ${EXIT_CODE}
