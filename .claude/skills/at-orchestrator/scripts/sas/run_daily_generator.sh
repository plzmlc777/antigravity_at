#!/usr/bin/env bash
# SAS daily generator — CIO-20260408-015 Phase 3.
#
# Runs once per day via PM2 cron_restart to generate exactly ONE new strategy
# through the meta-learner → strategy-builder autonomous pipeline.
#
# Schedule: 0 9 * * *  (09:00 local time, every day)
# Invokes: claude -p with a scripted prompt; the prompt drives main-turn Claude
#          to call meta-learner (Step 5f category rotation) then strategy-builder
#          (autonomous mode + Step 7.5 audition registration).
#
# Idempotency: checks for an audition entry created today before dispatching.
#              If today's slot is already filled, exits silently.
#
# Lock file prevents concurrent runs (in case of PM2 double-fire).

set -euo pipefail

PROJECT_ROOT="/home/hcpark/antigravity"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.daily.lock"
API="http://localhost:8001/api/v1"

mkdir -p "${RUNS_DIR}"

# Single-instance guard
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-daily] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TODAY_UTC="$(date -u +%Y-%m-%d)"
LOG_FILE="${RUNS_DIR}/daily_${TIMESTAMP}.log"

echo "[sas-daily] start ${TIMESTAMP}"
echo "[sas-daily] log ${LOG_FILE}"

# Idempotency check: any audition entry created today?
CREATED_TODAY=$(curl -s "${API}/strategy-audition?status=all&limit=50" \
  | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    today = '${TODAY_UTC}'
    count = sum(1 for e in data if (e.get('created_at') or '').startswith(today))
    print(count)
except Exception as e:
    print(0)
")

if [ "${CREATED_TODAY}" -gt "0" ]; then
  echo "[sas-daily] ${CREATED_TODAY} entry(ies) already created today (${TODAY_UTC}), skipping"
  exit 0
fi

# Build the prompt for main-turn Claude
PROMPT=$(cat <<'PROMPT_EOF'
SAS Daily Generator Cycle — CIO-20260408-015 Phase 3.

You are running inside a PM2 cron job. There is no interactive user. Execute the following scripted pipeline:

## Step 1 — Determine next category (rotation)
curl -s 'http://localhost:8001/api/v1/strategy-audition?status=all&limit=100'

From the response, compute the next category per the rules in meta-learner.md Step 5f (untouched first, oldest-used next, 8 categories total).

## Step 2 — Dispatch meta-learner to emit a strategy gap_signal
Agent(
  subagent_type="meta-learner",
  description="SAS daily gap_signal",
  prompt="Run Step 5f (Category Rotation) for family=strategy. Selected category: <NEXT_CATEGORY>. Find a capability gap within that category and POST to /api/v1/gap-signals."
)

## Step 3 — Poll the queue and dispatch strategy-builder autonomous
curl -s 'http://localhost:8001/api/v1/gap-signals?status=pending'

For each pending signal with family=strategy, dispatch:
Agent(
  subagent_type="strategy-builder",
  description="Autonomous generation",
  prompt="Autonomous mode. family=strategy. Follow strategy-builder.md Autonomous Mode section including Step 7.5 SAS registration."
)

## Step 4 — PATCH the gap_signal as consumed
curl -s -X PATCH 'http://localhost:8001/api/v1/gap-signals/<signal_id>' with status=consumed.

## Step 5 — Return a single-line summary
Print exactly one line: "SAS_DAILY_RESULT: <category> -> <strategy_id> (<audition_id>)" or "SAS_DAILY_RESULT: no-op (<reason>)".

Do NOT run backtests. Do NOT touch the audition pool beyond Step 7.5 auto-registration. Do NOT generate multiple strategies.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-daily] finished exit=${EXIT_CODE}"

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'daily_*.log' -mtime +90 -delete 2>/dev/null || true

exit ${EXIT_CODE}
