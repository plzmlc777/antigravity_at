#!/usr/bin/env bash
# SISDS meta-observer — Phase 8 (CIO-20260410-001).
#
# Weekly system health audit. Reviews pipeline throughput, calibration trend,
# lesson quality, and agent performance. Generates recommendations.
#
# Schedule: 0 4 * * 0 UTC (13:00 KST Sunday, after weekly-judge on Monday AM)
# Uses Opus model (deep analysis needed).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.metaobs.lock"

mkdir -p "${RUNS_DIR}"

if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-metaobs] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/metaobs_${TIMESTAMP}.log"

echo "[sas-metaobs] start ${TIMESTAMP}"
echo "[sas-metaobs] log ${LOG_FILE}"

PROMPT=$(cat <<PROMPT_EOF
SISDS Meta-Observer (Phase 8). PM2 weekly cron, no user.

Dispatch Agent(subagent_type="meta-observer") with prompt:
"Run the full 7-step meta-observer.md workflow.
 Gather pipeline health, calibration trend, lesson quality, agent performance.
 Generate weekly system health report with recommendations.
 Return your complete JSON report."

After the subagent returns, emit exactly ONE line starting with "SAS_METAOBS_RESULT:" summarizing health assessment, CIR, and recommendation count.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model opus \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-metaobs] finished exit=${EXIT_CODE}"

tail -5 "${LOG_FILE}" 2>/dev/null || true

find "${RUNS_DIR}" -name 'metaobs_*.log' -mtime +180 -delete 2>/dev/null || true

exit ${EXIT_CODE}
