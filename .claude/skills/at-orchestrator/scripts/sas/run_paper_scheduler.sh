#!/usr/bin/env bash
# SAS paper scheduler — SISDS Phase 4 (CIO-20260410-001).
#
# Two jobs in one run:
# Job 1: Promote (sandbox, passed) → start paper trading session
# Job 2: Evaluate (paper, running) entries older than 14 days
#
# Schedule: Every 6 hours (0 */6 * * * UTC)
# Lightweight — paper-scheduler agent (haiku) is fast.
#
# Idempotency: checks current state before acting. Safe to re-run.

set -euo pipefail

# Defensive PATH export (manual triggers without the wrapper).
export PATH="${HOME}/.npm-global/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.paper.lock"
API="http://localhost:8001/api/v1"
BACKEND_DIR="${PROJECT_ROOT}/backend"

mkdir -p "${RUNS_DIR}"

# Mint a fresh JWT for the paper-scheduler service user. Agent reads it
# from BACKEND_SERVICE_TOKEN and includes "Authorization: Bearer ..." on
# every /live/* and /strategy-audition/* call.
if [ -d "${BACKEND_DIR}/venv" ] && [ -f "${BACKEND_DIR}/issue_service_token.py" ]; then
  TOKEN=$(cd "${BACKEND_DIR}" && PYTHONPATH=. ./venv/bin/python3 issue_service_token.py 2>/dev/null || true)
  if [ -n "${TOKEN}" ]; then
    export BACKEND_SERVICE_TOKEN="${TOKEN}"
    echo "[sas-paper] service token issued (len=${#TOKEN})"
  else
    echo "[sas-paper] WARN: failed to issue service token — agent will hit 401 on /live/start"
  fi
else
  echo "[sas-paper] WARN: backend venv or issue_service_token.py missing"
fi

# Single-instance guard
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-paper] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/paper_${TIMESTAMP}.log"

echo "[sas-paper] start ${TIMESTAMP}"
echo "[sas-paper] log ${LOG_FILE}"

# Quick check: anything to do?
SANDBOX_PASSED=$(curl -s "${API}/strategy-audition/by-stage?stage=sandbox&stage_status=passed&limit=5" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
PAPER_RUNNING=$(curl -s "${API}/strategy-audition/by-stage?stage=paper&stage_status=running&limit=10" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "${SANDBOX_PASSED}" -eq "0" ] && [ "${PAPER_RUNNING}" -eq "0" ]; then
  echo "[sas-paper] nothing to do (0 sandbox passed, 0 paper running)"
  exit 0
fi

echo "[sas-paper] sandbox_passed=${SANDBOX_PASSED} paper_running=${PAPER_RUNNING}"

PROMPT=$(cat <<PROMPT_EOF
SAS Paper Scheduler (SISDS Phase 4). PM2 cron, no user.

Dispatch Agent(subagent_type="paper-scheduler") with prompt:
"Run both jobs from paper-scheduler.md:
 Job 1: Check for (sandbox, passed) entries and start paper sessions (max 3 concurrent).
 Job 2: Evaluate (paper, running) entries older than 14 days.
 Return your summary JSON."

After the subagent returns, emit exactly ONE line starting with "SAS_PAPER_RESULT:" summarizing promoted/evaluated/skipped counts.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model haiku \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-paper] finished exit=${EXIT_CODE}"

# Show result summary
if [ -f "${LOG_FILE}" ]; then
  tail -3 "${LOG_FILE}" 2>/dev/null || true
fi

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'paper_*.log' -mtime +90 -delete 2>/dev/null || true

exit ${EXIT_CODE}
