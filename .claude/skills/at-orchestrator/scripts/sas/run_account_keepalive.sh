#!/usr/bin/env bash
# Account keepalive — daily ping of real Kiwoom/Binance accounts.
#
# Schedule: daily 18:00 UTC (= 03:00 KST).
# Dispatched by PM2 via sas_loop_wrapper.sh.
#
# Two-layer design (hybrid):
# - Worker (backend/scripts/account_keepalive.py): deterministic balance ping,
#   DB write to account_keepalive_logs, Telegram alert on hard failure.
# - Sub-agent (.claude/agents/account-keepalive.md, sonnet): runs the worker,
#   parses output, adds soft-anomaly detection (consecutive failures, latency
#   drift, suspicious zero balances).
#
# Idempotency: balance-query is read-only; safe to re-run.

set -uo pipefail

# Defensive PATH export (manual triggers without the wrapper).
export PATH="${HOME}/.npm-global/bin:${PATH}"

# Headless auth: long-lived OAuth token (independent grant, valid ~1yr,
# issued 2026-07-11). Avoids the 8h credentials-file rotation that killed
# keepalive 2026-06-21..07-11.
# shellcheck disable=SC1091
[ -f "${HOME}/.claude/oauth_token.env" ] && source "${HOME}/.claude/oauth_token.env"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/keepalive"
LOCK_FILE="${RUNS_DIR}/.keepalive.lock"
BACKEND_DIR="${PROJECT_ROOT}/backend"

mkdir -p "${RUNS_DIR}"

# Single-instance guard (worker can take ~5 min for 8 accounts; previous run
# might still be active if cron mis-fires).
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[keepalive] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/keepalive_${TIMESTAMP}.log"

echo "[keepalive] start ${TIMESTAMP}"
echo "[keepalive] log ${LOG_FILE}"

# Sanity: backend venv must exist for the worker script.
if [ ! -x "${BACKEND_DIR}/venv/bin/python3" ]; then
  echo "[keepalive] ERROR: backend venv missing — cannot run worker"
  exit 1
fi

PROMPT=$(cat <<'PROMPT_EOF'
Account keepalive (daily). PM2 cron, no user.

Dispatch Agent(subagent_type="account-keepalive") with prompt:
"Run the keepalive job per account-keepalive.md:
 1) Execute the worker (backend/scripts/account_keepalive.py)
 2) Parse its JSON output
 3) Layer soft-anomaly detection (consecutive failures, latency spikes, suspicious zero balances)
 4) Emit final JSON on a line starting with KEEPALIVE_RESULT:"

After the subagent returns, echo the KEEPALIVE_RESULT line as-is. Nothing else.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model sonnet \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[keepalive] finished exit=${EXIT_CODE}"

# Show result summary
if [ -f "${LOG_FILE}" ]; then
  grep -E "^KEEPALIVE_RESULT:" "${LOG_FILE}" 2>/dev/null | tail -1 || tail -3 "${LOG_FILE}"
fi

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'keepalive_*.log' -mtime +90 -delete 2>/dev/null || true

exit ${EXIT_CODE}
