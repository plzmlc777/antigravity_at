#!/usr/bin/env bash
# SAS weekly judge — CIO-20260408-015 Phase 3.
#
# Runs once per week via PM2 cron_restart. Dispatches audition-judge to
# evaluate this week's audition pool via standardized backtest competition
# and selects ONE winner (or none if no shortlist survivors).
#
# Schedule: 0 10 * * 1  (10:00 local time, every Monday)
# Invokes: claude -p with a prompt that triggers main-turn Claude to call
#          Agent(subagent_type="audition-judge").
#
# Idempotency: checks if this week's judging already produced a non-audition
#              transition. If so, exits silently.

set -euo pipefail

# Resolve project root from this script's location (portable across environments)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.weekly.lock"
API="http://localhost:8001/api/v1"

mkdir -p "${RUNS_DIR}"

# Single-instance guard
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-weekly] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CURRENT_WEEK="$(date -u +%G-W%V)"
LOG_FILE="${RUNS_DIR}/weekly_${TIMESTAMP}.log"

echo "[sas-weekly] start ${TIMESTAMP} week=${CURRENT_WEEK}"
echo "[sas-weekly] log ${LOG_FILE}"

# Idempotency check: any graduated/eliminated entry with judged_at in this week?
ALREADY_JUDGED=$(curl -s "${API}/strategy-audition?status=all&week=${CURRENT_WEEK}&limit=100" \
  | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    judged = sum(1 for e in data if e.get('status') in ('graduated', 'eliminated') and e.get('judged_at'))
    print(judged)
except Exception:
    print(0)
")

if [ "${ALREADY_JUDGED}" -gt "0" ]; then
  echo "[sas-weekly] ${ALREADY_JUDGED} entry(ies) already judged this week (${CURRENT_WEEK}), skipping"
  exit 0
fi

PROMPT=$(cat <<'PROMPT_EOF'
SAS Weekly Judge (CIO-015 Phase 3). PM2 cron, no user.

Dispatch Agent(subagent_type="audition-judge") with prompt:
"Run the full audition-judge.md workflow on the current ISO week. Return your summary JSON."

After the subagent returns, emit exactly ONE line starting with "SAS_WEEKLY_RESULT:" summarizing winner or no-winner. Do not repeat the JSON.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-weekly] finished exit=${EXIT_CODE}"

# Prune logs older than 365 days (weekly = ~52 files/year)
find "${RUNS_DIR}" -name 'weekly_*.log' -mtime +365 -delete 2>/dev/null || true

exit ${EXIT_CODE}
