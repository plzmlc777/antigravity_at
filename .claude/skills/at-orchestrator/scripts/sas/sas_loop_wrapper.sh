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

# PM2 doesn't source ~/.bashrc/.profile, so npm-global bin (where `claude` lives)
# is missing from PATH. All SAS scripts shell out to `claude -p ...`, so we must
# inject it here once for every wrapped child.
export PATH="${HOME}/.npm-global/bin:${PATH}"

# Load project-root .env if present (gitignored).
# IMPORTANT: .env holds ONLY system config (POSTGRES_*, ports, APP_ENV).
# Account/exchange credentials (API keys, secrets, telegram tokens) live in
# the `exchange_accounts` DB table — see memory/feedback_credentials_in_db.md.
if [ -f "$(pwd)/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$(pwd)/.env"
  set +a
fi

# Telegram alert credentials are loaded from DB (exchange_accounts), NOT .env.
# load_telegram_creds.py decrypts the bot token from the first row with
# telegram_enabled=TRUE and emits `export TELEGRAM_BOT_TOKEN=...` lines.
# Silent no-op if no row is configured — child scripts treat empty token as
# "alerts disabled".
SAS_LOAD_TG="$(pwd)/.claude/skills/at-orchestrator/scripts/sas/load_telegram_creds.py"
if [ -f "${SAS_LOAD_TG}" ] && [ -x "$(pwd)/backend/venv/bin/python3" ]; then
  TG_EXPORTS=$(cd "$(pwd)/backend" && PYTHONPATH=. ./venv/bin/python3 "${SAS_LOAD_TG}" 2>/dev/null || true)
  if [ -n "${TG_EXPORTS}" ]; then
    eval "${TG_EXPORTS}"
  fi
fi

CRON_EXPR="${1:?Usage: sas_loop_wrapper.sh '<cron_expr>' <script.sh>}"
TARGET_SCRIPT="${2:?Usage: sas_loop_wrapper.sh '<cron_expr>' <script.sh>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve target script path (relative to cwd, not this script's dir)
if [[ "${TARGET_SCRIPT}" != /* ]]; then
  TARGET_SCRIPT="$(pwd)/${TARGET_SCRIPT}"
fi

if [ ! -f "${TARGET_SCRIPT}" ]; then
  echo "[sas-loop] ERROR: script not found: ${TARGET_SCRIPT}"
  exit 1
fi

# Parse cron expression into components
IFS=' ' read -r CRON_MIN CRON_HOUR CRON_DOM CRON_MON CRON_DOW <<< "${CRON_EXPR}"

# Calculate seconds until next cron match using Python (fast, handles all cases)
next_sleep_seconds() {
  python3 -c "
import time, datetime

cron_min, cron_hour, cron_dom, cron_mon, cron_dow = '${CRON_EXPR}'.split()

now = datetime.datetime.utcnow()
# Start from next minute
candidate = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

for _ in range(44640):  # max 31 days
    m, h, dom, mon, dow = candidate.minute, candidate.hour, candidate.day, candidate.month, candidate.weekday()
    dow_sun = (dow + 1) % 7  # Python: Mon=0, cron: Sun=0

    # Check minute
    if cron_min != '*' and int(cron_min) != m: candidate += datetime.timedelta(minutes=1); continue
    # Check hour (support */N)
    if cron_hour != '*':
        if '/' in cron_hour:
            step = int(cron_hour.split('/')[1])
            if h % step != 0: candidate += datetime.timedelta(minutes=1); continue
        elif int(cron_hour) != h: candidate += datetime.timedelta(minutes=1); continue
    # Check day of month
    if cron_dom != '*' and int(cron_dom) != dom: candidate += datetime.timedelta(minutes=1); continue
    # Check month
    if cron_mon != '*' and int(cron_mon) != mon: candidate += datetime.timedelta(minutes=1); continue
    # Check day of week
    if cron_dow != '*' and int(cron_dow) != dow_sun: candidate += datetime.timedelta(minutes=1); continue

    delta = int((candidate - now).total_seconds())
    print(max(delta, 60))
    break
else:
    print(3600)
"
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
