#!/usr/bin/env bash
# SAS loop wrapper — keeps PM2 process alive between scheduled runs.
#
# Usage: sas_loop_wrapper.sh <cron_expression> <actual_script.sh>
#
# Instead of relying on PM2 cron_restart (which doesn't fire for stopped processes),
# this wrapper runs the target script at the specified schedule by sleeping
# until the next occurrence, then executing, and repeating forever.
#
# Cron expressions supported (subset):
#   "0 9 * * *"      → daily at 09:00 UTC
#   "0 */2 * * *"    → every 2 hours at :00
#   "0 */6 * * *"    → every 6 hours at :00
#   "0 6 * * *"      → daily at 06:00 UTC
#   "0 4 * * 0"      → weekly Sunday 04:00 UTC
#   "0 10 * * 1"     → weekly Monday 10:00 UTC
#   "0 11 1 * *"     → monthly 1st at 11:00 UTC
#   "7 9 * * 0"      → weekly Sunday 09:07 UTC

set -uo pipefail

CRON_EXPR="${1:?Usage: sas_loop_wrapper.sh '<cron_expr>' <script.sh>}"
TARGET_SCRIPT="${2:?Usage: sas_loop_wrapper.sh '<cron_expr>' <script.sh>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve target script path (relative to this script's dir if not absolute)
if [[ "${TARGET_SCRIPT}" != /* ]]; then
  TARGET_SCRIPT="${SCRIPT_DIR}/${TARGET_SCRIPT}"
fi

if [ ! -f "${TARGET_SCRIPT}" ]; then
  echo "[sas-loop] ERROR: script not found: ${TARGET_SCRIPT}"
  exit 1
fi

# Parse cron expression into components
IFS=' ' read -r CRON_MIN CRON_HOUR CRON_DOM CRON_MON CRON_DOW <<< "${CRON_EXPR}"

# Calculate seconds until next cron match
next_sleep_seconds() {
  local now_epoch
  now_epoch=$(date -u +%s)

  # Try each minute in the next 31 days (max monthly interval)
  for offset_min in $(seq 1 44640); do
    local candidate_epoch=$((now_epoch + offset_min * 60))
    local c_min c_hour c_dom c_mon c_dow
    c_min=$(date -u -d "@${candidate_epoch}" +%-M)
    c_hour=$(date -u -d "@${candidate_epoch}" +%-H)
    c_dom=$(date -u -d "@${candidate_epoch}" +%-d)
    c_mon=$(date -u -d "@${candidate_epoch}" +%-m)
    c_dow=$(date -u -d "@${candidate_epoch}" +%w)

    # Check minute
    if [[ "${CRON_MIN}" != "*" && "${CRON_MIN}" != "${c_min}" ]]; then continue; fi
    # Check hour (support */N)
    if [[ "${CRON_HOUR}" == *"/"* ]]; then
      local step="${CRON_HOUR#*/}"
      if (( c_hour % step != 0 )); then continue; fi
    elif [[ "${CRON_HOUR}" != "*" && "${CRON_HOUR}" != "${c_hour}" ]]; then continue; fi
    # Check day of month
    if [[ "${CRON_DOM}" != "*" && "${CRON_DOM}" != "${c_dom}" ]]; then continue; fi
    # Check month
    if [[ "${CRON_MON}" != "*" && "${CRON_MON}" != "${c_mon}" ]]; then continue; fi
    # Check day of week
    if [[ "${CRON_DOW}" != "*" && "${CRON_DOW}" != "${c_dow}" ]]; then continue; fi

    echo $((candidate_epoch - now_epoch))
    return 0
  done

  # Fallback: 1 hour
  echo 3600
}

echo "[sas-loop] wrapper started for: $(basename "${TARGET_SCRIPT}")"
echo "[sas-loop] schedule: ${CRON_EXPR}"
echo "[sas-loop] pid: $$"

while true; do
  SLEEP_SEC=$(next_sleep_seconds)
  NEXT_RUN=$(date -u -d "+${SLEEP_SEC} seconds" +"%Y-%m-%d %H:%M UTC")
  echo "[sas-loop] next run: ${NEXT_RUN} (sleeping ${SLEEP_SEC}s)"

  sleep "${SLEEP_SEC}"

  echo "[sas-loop] executing: $(basename "${TARGET_SCRIPT}")"
  bash "${TARGET_SCRIPT}" || echo "[sas-loop] script exited with code $?"
  echo "[sas-loop] execution complete, scheduling next run..."
done
