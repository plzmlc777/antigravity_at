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

PROJECT_ROOT="/home/hcpark/antigravity"
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
SAS Weekly Judge Cycle — CIO-20260408-015 Phase 3.

You are running inside a PM2 cron job. There is no interactive user. Execute exactly one audition judging cycle:

## Step 1 — Dispatch the audition-judge agent
Agent(
  subagent_type="audition-judge",
  description="SAS weekly judging",
  prompt="Run the full 9-step workflow from audition-judge.md on the current week's audition pool. Standardized config: BTCUSDT / 1h / 90 days / $10000 / BinanceFutures. Follow all PATCH rules strictly (losers first, winner last). Return the summary JSON."
)

## Step 2 — Parse the returned JSON
Extract: winner.strategy_id, winner.monthly_return_compound, eliminated count, no_winner_reason.

## Step 3 — Graveyard soft-move (Phase 3 addition)
For each eliminated strategy in the response, move its file from:
  /home/hcpark/antigravity/.claude/skills/at-live-signal/scripts/strategies/<id>.py
to:
  /home/hcpark/antigravity/.claude/skills/at-live-signal/scripts/strategies/_graveyard/<id>.py

Use: `mkdir -p /home/hcpark/antigravity/.claude/skills/at-live-signal/scripts/strategies/_graveyard && mv <src> <dst>`

The StrategyRegistry skips `_`-prefixed directories automatically so no code change needed.

After each move, PATCH the audition entry with graveyard_path set to the new absolute path.

## Step 4 — Return a single-line summary
Print exactly one line: "SAS_WEEKLY_RESULT: winner=<id> score=<compound> eliminated=<N>" or "SAS_WEEKLY_RESULT: no-winner reason=<reason>".

Do NOT touch graduated strategies' files. Do NOT deploy anything to live trading.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-weekly] finished exit=${EXIT_CODE}"

# Prune logs older than 365 days (weekly = ~52 files/year)
find "${RUNS_DIR}" -name 'weekly_*.log' -mtime +365 -delete 2>/dev/null || true

exit ${EXIT_CODE}
