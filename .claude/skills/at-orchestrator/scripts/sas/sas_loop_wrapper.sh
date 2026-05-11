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

# PM2's `args` field is space-tokenized, so the single quotes around the cron
# expression in ecosystem.config.cjs (e.g. `'0 8 * * 1-5' ./script.sh`) are
# stripped and the wrapper receives 6 positionals: 5 cron parts + script path.
# When invoked manually with proper quoting, it gets 2 positionals (cron, script).
# Handle both shapes: the LAST positional is always the script; everything
# before it is the cron expression.
if [ $# -lt 2 ]; then
  echo "Usage: sas_loop_wrapper.sh '<cron_expr>' <script.sh>" >&2
  exit 1
fi
TARGET_SCRIPT="${!#}"
CRON_EXPR="${*:1:$#-1}"

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

# Calculate seconds until next cron match using Python.
# Supports: '*'  '5'  '*/N'  'a-b'  'a,b,c'  combinations of comma+range
# (e.g. '1-5'  '0,15,30,45'  '1-3,5')
next_sleep_seconds() {
  python3 -c "
import datetime

cron_min, cron_hour, cron_dom, cron_mon, cron_dow = '${CRON_EXPR}'.split()

def parse_field(expr, lo, hi):
    if expr == '*':
        return set(range(lo, hi + 1))
    out = set()
    for chunk in expr.split(','):
        if chunk == '*':
            out.update(range(lo, hi + 1))
        elif '/' in chunk:
            base, step = chunk.split('/', 1)
            base_set = parse_field(base if base else '*', lo, hi)
            step = int(step)
            for v in sorted(base_set):
                if (v - lo) % step == 0:
                    out.add(v)
        elif '-' in chunk:
            a, b = chunk.split('-', 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(chunk))
    return out

mins  = parse_field(cron_min,  0, 59)
hours = parse_field(cron_hour, 0, 23)
doms  = parse_field(cron_dom,  1, 31)
mons  = parse_field(cron_mon,  1, 12)
dows  = parse_field(cron_dow,  0, 7)  # 0 and 7 both = Sunday

now = datetime.datetime.utcnow()
candidate = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)

for _ in range(44640):  # max 31 days look-ahead
    dow_sun = (candidate.weekday() + 1) % 7  # Python: Mon=0, cron: Sun=0
    if (candidate.minute in mins and
        candidate.hour in hours and
        candidate.day in doms and
        candidate.month in mons and
        (dow_sun in dows or (dow_sun == 0 and 7 in dows))):
        delta = int((candidate - now).total_seconds())
        print(max(delta, 60))
        break
    candidate += datetime.timedelta(minutes=1)
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
