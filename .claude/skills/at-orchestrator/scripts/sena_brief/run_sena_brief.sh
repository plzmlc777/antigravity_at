#!/usr/bin/env bash
# Sena Technology (061090) daily brief — pre-market (08:30 KST) / post-market (16:30 KST).
#
# Schedule: dispatched by sas_loop_wrapper.sh
#   pre  → KST 08:30 = UTC 23:30 (cron "30 23 * * 0-4")
#   post → KST 16:30 = UTC 07:30 (cron "30 7  * * 1-5")
#
# Pipeline:
#   1. Resolve telegram creds from exchange_accounts via load_telegram_creds.py
#   2. Run backend/scripts/sena_daily_brief.py --mode {pre|post}
#   3. Worker fetches Naver quote/news/discussion + OpenDART disclosures
#      and sends a single Markdown message to the configured chat.
#
# Idempotency: all data fetches are read-only HTTP GETs; safe to re-run.

set -uo pipefail

# Mode is provided via env var SENA_BRIEF_MODE (set by PM2 ecosystem entry),
# or as the first positional arg for manual invocation.
MODE="${SENA_BRIEF_MODE:-${1:-}}"
if [ "${MODE}" != "pre" ] && [ "${MODE}" != "post" ]; then
  echo "[sena-brief] usage: SENA_BRIEF_MODE=<pre|post> $0  OR  $0 <pre|post>"
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sena_brief"
LOAD_CREDS="${PROJECT_ROOT}/.claude/skills/at-orchestrator/scripts/sas/load_telegram_creds.py"

mkdir -p "${RUNS_DIR}"

TS="$(TZ=Asia/Seoul date '+%Y%m%dT%H%M%S')"
LOG_FILE="${RUNS_DIR}/sena_brief_${MODE}_${TS}.log"

echo "[sena-brief] start mode=${MODE} ts=${TS}" | tee "${LOG_FILE}"

if [ ! -x "${BACKEND_DIR}/venv/bin/python3" ]; then
  echo "[sena-brief] ERROR: backend venv missing at ${BACKEND_DIR}/venv" | tee -a "${LOG_FILE}"
  exit 1
fi

# Load telegram creds from DB. Silent if not configured.
if [ -f "${LOAD_CREDS}" ]; then
  CREDS_OUT="$("${BACKEND_DIR}/venv/bin/python3" "${LOAD_CREDS}" 2>>"${LOG_FILE}")" || true
  if [ -n "${CREDS_OUT}" ]; then
    eval "${CREDS_OUT}"
  fi
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
  echo "[sena-brief] WARN: telegram creds missing — will still build msg but skip send (will fail)" | tee -a "${LOG_FILE}"
fi

cd "${PROJECT_ROOT}"
"${BACKEND_DIR}/venv/bin/python3" backend/scripts/sena_daily_brief.py --mode "${MODE}" 2>&1 | tee -a "${LOG_FILE}"
EXIT_CODE="${PIPESTATUS[0]}"

# Rotate logs — keep last 30 files.
ls -1t "${RUNS_DIR}"/sena_brief_*.log 2>/dev/null | tail -n +31 | xargs -r rm -f

echo "[sena-brief] end exit=${EXIT_CODE}" | tee -a "${LOG_FILE}"
exit "${EXIT_CODE}"
