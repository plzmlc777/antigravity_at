#!/usr/bin/env bash
# SAS sandbox processor — SISDS Phase 3 (CIO-20260410-001).
#
# Runs after the daily generator to process any (sandbox, pending) entries.
# For each pending strategy, dispatches sandbox-researcher to investigate.
#
# Schedule: 30 minutes after daily generator (0 1 * * * UTC = 10:00 KST)
#           Or triggered directly after daily-generator completes.
#
# Idempotency: checks if any (sandbox, pending) entries exist. If none, exits.
# Also skips strategies already being researched (sandbox, running).
# Max 1 strategy per cycle (avoid long-running sessions).

set -euo pipefail

# Resolve project root from script location (portable)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.sandbox.lock"
API="http://localhost:8001/api/v1"

mkdir -p "${RUNS_DIR}"

# Single-instance guard
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-sandbox] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/sandbox_${TIMESTAMP}.log"

echo "[sas-sandbox] start ${TIMESTAMP}"
echo "[sas-sandbox] log ${LOG_FILE}"

# Check for pending sandbox entries
PENDING=$(curl -s "${API}/strategy-audition/by-stage?stage=sandbox&stage_status=pending&limit=5")
PENDING_COUNT=$(echo "${PENDING}" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "${PENDING_COUNT}" -eq "0" ]; then
  echo "[sas-sandbox] no (sandbox, pending) entries, skipping"
  exit 0
fi

# Also check how many are already running (concurrency limit = 1 at a time for now)
RUNNING_COUNT=$(curl -s "${API}/strategy-audition/by-stage?stage=sandbox&stage_status=running&limit=5" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "${RUNNING_COUNT}" -ge "1" ]; then
  echo "[sas-sandbox] ${RUNNING_COUNT} sandbox already running, skipping (limit=1)"
  exit 0
fi

# Pick the first pending strategy
STRATEGY_ID=$(echo "${PENDING}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d[0]['strategy_id'] if d else '')" 2>/dev/null || echo "")
CATEGORY=$(echo "${PENDING}" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d[0].get('category','') if d else '')" 2>/dev/null || echo "")

if [ -z "${STRATEGY_ID}" ]; then
  echo "[sas-sandbox] could not parse pending strategy_id"
  exit 1
fi

echo "[sas-sandbox] investigating: ${STRATEGY_ID} (category=${CATEGORY})"

# Transition to (sandbox, running) before dispatch
curl -s -X POST "${API}/strategy-audition/${STRATEGY_ID}/transition" \
  -H 'Content-Type: application/json' \
  -d "{
    \"to_stage\": \"sandbox\",
    \"to_status\": \"running\",
    \"transitioned_by\": \"sas-sandbox-processor\",
    \"reason\": \"sandbox-researcher dispatch starting\"
  }" > /dev/null

# Build prompt via temp file (avoids shell escaping issues with JSON context)
PROMPT_FILE="${RUNS_DIR}/.sandbox_prompt_${STRATEGY_ID}.txt"

cat > "${PROMPT_FILE}" <<PROMPT_EOF
SAS Sandbox Research (SISDS Phase 3). PM2 cron, no user.

Dispatch Agent(subagent_type="sandbox-researcher") with prompt:
"Investigate strategy ${STRATEGY_ID} (category: ${CATEGORY}). Follow sandbox-researcher.md full 10-step workflow.

Budget: max 100 backtests. Standard conditions: BTCUSDT / 1h / 90d / 10000 USD / BinanceFutures.
Return your full investigation JSON including decision, evidence, hypotheses, and lessons."

After the subagent returns, emit exactly ONE line starting with "SAS_SANDBOX_RESULT:" summarizing the outcome (strategy_id, decision, best_compound, backtests_run).
PROMPT_EOF

claude -p "$(cat "${PROMPT_FILE}")" \
  --permission-mode bypassPermissions \
  --model sonnet \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

rm -f "${PROMPT_FILE}"

EXIT_CODE=$?
echo "[sas-sandbox] finished exit=${EXIT_CODE}"

# Show result summary
if [ -f "${LOG_FILE}" ]; then
  tail -5 "${LOG_FILE}" 2>/dev/null || true
fi

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'sandbox_*.log' -mtime +90 -delete 2>/dev/null || true

exit ${EXIT_CODE}
