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

# Resolve project root from this script's location (portable across environments)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
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

if [ "${SAS_BACKFILL_FORCE:-0}" != "1" ] && [ "${CREATED_TODAY}" -gt "0" ]; then
  echo "[sas-daily] ${CREATED_TODAY} entry(ies) already created today (${TODAY_UTC}), skipping"
  exit 0
fi
if [ "${SAS_BACKFILL_FORCE:-0}" = "1" ]; then
  echo "[sas-daily] backfill mode: idempotency check bypassed (${CREATED_TODAY} entries already today)"
fi

# Build the prompt for main-turn Claude
PROMPT=$(cat <<'PROMPT_EOF'
SAS Daily Generator (CIO-015 Phase 3). PM2 cron, no user.

Pipeline (sequential):
1. Dispatch Agent(subagent_type="meta-learner") with prompt:
   "Run Step 5f Category Rotation for family=strategy. Determine the next category via the rotation rules in meta-learner.md and emit exactly one gap_signal via POST /api/v1/gap-signals."
2. Poll curl 'http://localhost:8001/api/v1/gap-signals?status=pending' and pick the newest signal with proposed_intent.family=='strategy'.
3. Dispatch Agent(subagent_type="strategy-builder") in autonomous mode with the signal payload. The builder MUST complete the full autonomous workflow:
   a. Step 7.5: register the audition into (birth, pending).
   b. Run the birth-check backtest (this is the ONLY allowed backtest in this pipeline — do NOT run extra walk-forward / parameter sweeps).
   c. Based on the birth-check outcome, PATCH the audition's stage so it never stays in 'birth':
      - If KPI passes the birth gate → transition to (sandbox, pending). This is REQUIRED for sandbox-processor pickup.
      - If birth-check fails (api error, zero cycles, KPI below floor) → transition to (retired, failed) with a clear reason.
   The audition MUST exit the 'birth' stage before this script returns.
4. PATCH /api/v1/gap-signals/<signal_id> status=consumed with the builder's response JSON as the result.

Verification before emitting the result line — query the audition you just created and confirm stage != 'birth':
   curl -s 'http://localhost:8001/api/v1/strategy-audition?strategy_id=<id>' | jq '.[] | {stage, stage_status}'
If stage is still 'birth', explicitly PATCH it to (sandbox, pending) or (retired, failed) yourself based on the birth-check evidence before returning.

Emit exactly ONE line starting with "SAS_DAILY_RESULT:" with the FINAL stage:
  SAS_DAILY_RESULT: category=<x>, strategy_id=<y>, audition_id=<z>, stage=<sandbox|retired>, kpi=<v>%
or "SAS_DAILY_RESULT: no-op (<reason>)" if the pipeline could not produce a strategy.

Do NOT generate multiple strategies. Do NOT exit while the audition is still in 'birth'.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-daily] finished exit=${EXIT_CODE}"

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'daily_*.log' -mtime +90 -delete 2>/dev/null || true

exit ${EXIT_CODE}
