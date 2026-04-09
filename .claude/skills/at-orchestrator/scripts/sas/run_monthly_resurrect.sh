#!/usr/bin/env bash
# SAS monthly resurrect — CIO-20260408-015 Phase 4.
#
# Runs on the 1st of each month via PM2 cron_restart. Dispatches the
# monthly-resurrect agent which reviews the graveyard pool and selects
# up to 3 strategies for re-evaluation based on classification rules.
#
# Schedule: 0 11 1 * *  (11:00 on day 1 of each month)
#
# Idempotency: checks if any resurrect_count changed in the current
# calendar month. If so, exits silently.

set -euo pipefail

PROJECT_ROOT="/home/hcpark/antigravity"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.monthly.lock"
API="http://localhost:8001/api/v1"

mkdir -p "${RUNS_DIR}"

if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-monthly] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
CURRENT_MONTH="$(date -u +%Y-%m)"
LOG_FILE="${RUNS_DIR}/monthly_${TIMESTAMP}.log"

echo "[sas-monthly] start ${TIMESTAMP} month=${CURRENT_MONTH}"
echo "[sas-monthly] log ${LOG_FILE}"

# Idempotency: any resurrection activity this month?
ALREADY_RUN=$(curl -s "${API}/strategy-audition?status=all&limit=200" \
  | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    month = '${CURRENT_MONTH}'
    count = sum(
        1 for e in data
        if (e.get('last_resurrected_at') or '').startswith(month)
    )
    print(count)
except Exception:
    print(0)
")

if [ "${ALREADY_RUN}" -gt "0" ]; then
  echo "[sas-monthly] ${ALREADY_RUN} resurrection(s) already this month, skipping"
  exit 0
fi

PROMPT=$(cat <<'PROMPT_EOF'
SAS Monthly Resurrect (CIO-015 Phase 4). PM2 cron, no user.

Dispatch Agent(subagent_type="monthly-resurrect") with prompt:
"Run the full monthly-resurrect.md workflow. Review the graveyard pool, classify elimination reasons, score candidates, and resurrect up to 3 that meet the threshold. Return your summary JSON."

After the subagent returns, emit exactly ONE line starting with "SAS_MONTHLY_RESULT:" summarizing the outcome (resurrected count, skipped count).
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-monthly] finished exit=${EXIT_CODE}"

# Prune logs older than 730 days (2 years ~ 24 files)
find "${RUNS_DIR}" -name 'monthly_*.log' -mtime +730 -delete 2>/dev/null || true

exit ${EXIT_CODE}
