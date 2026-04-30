#!/usr/bin/env bash
# SISDS live monitor — Phase 6 (CIO-20260410-001).
#
# Daily check of all live-stage strategies AND paper-running surveillance:
# Job 1: Activate (live, pending) after user approval
# Job 2: Monitor (live, running) for degradation (D1-D5)
# Job 3: Enforce grace period for (live, degraded)
# Job 4: Paper-stage health surveillance (P1-P4) — added 2026-W18 retro
#
# Schedule: 0 6 * * * UTC (15:00 KST daily)
# Lightweight — haiku model, fast checks.

set -uo pipefail

# Defensive PATH export — wrapper does this too, but manual `bash this.sh`
# invocations would otherwise hit `claude: command not found`.
export PATH="${HOME}/.npm-global/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.livemon.lock"
API="http://localhost:8001/api/v1"
BACKEND_DIR="${PROJECT_ROOT}/backend"

mkdir -p "${RUNS_DIR}"

# Source .env (system config only) — wrapper does this on PM2 path; manual triggers need it too.
# Telegram creds come from DB (exchange_accounts), NOT .env.
if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  set +a
fi

# Load Telegram creds from DB
if [ -x "${BACKEND_DIR}/venv/bin/python3" ]; then
  TG_EXPORTS=$(cd "${BACKEND_DIR}" && PYTHONPATH=. ./venv/bin/python3 "${SCRIPT_DIR}/load_telegram_creds.py" 2>/dev/null || true)
  if [ -n "${TG_EXPORTS}" ]; then
    eval "${TG_EXPORTS}"
  fi
fi

# Mint service token for /live/* auth (Job 4 needs it; Job 2 also needs it now)
if [ -d "${BACKEND_DIR}/venv" ] && [ -f "${BACKEND_DIR}/issue_service_token.py" ]; then
  TOKEN=$(cd "${BACKEND_DIR}" && PYTHONPATH=. ./venv/bin/python3 issue_service_token.py 2>/dev/null || true)
  if [ -n "${TOKEN}" ]; then
    export BACKEND_SERVICE_TOKEN="${TOKEN}"
    echo "[sas-livemon] service token issued (len=${#TOKEN})"
  else
    echo "[sas-livemon] WARN: failed to issue service token — /live/* calls will hit 401"
  fi
fi

if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[sas-livemon] previous run still active (pid ${PREV_PID}), aborting"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/livemon_${TIMESTAMP}.log"

echo "[sas-livemon] start ${TIMESTAMP}"
echo "[sas-livemon] log ${LOG_FILE}"

# Quick scope check: any live-stage entries OR paper-running entries?
LIVE_PENDING=$(curl -s "${API}/strategy-audition/by-stage?stage=live&stage_status=pending&limit=5" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
LIVE_RUNNING=$(curl -s "${API}/strategy-audition/by-stage?stage=live&stage_status=running&limit=10" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
LIVE_DEGRADED=$(curl -s "${API}/strategy-audition/by-stage?stage=live&stage_status=degraded&limit=10" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
PAPER_RUNNING=$(curl -s "${API}/strategy-audition/by-stage?stage=paper&stage_status=running&limit=20" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

TOTAL=$((LIVE_PENDING + LIVE_RUNNING + LIVE_DEGRADED + PAPER_RUNNING))
if [ "${TOTAL}" -eq "0" ]; then
  echo "[sas-livemon] nothing to do (live: 0, paper-running: 0)"
  exit 0
fi

echo "[sas-livemon] scope: live(p=${LIVE_PENDING}, r=${LIVE_RUNNING}, d=${LIVE_DEGRADED})  paper-running=${PAPER_RUNNING}"

PROMPT=$(cat <<'PROMPT_EOF'
SISDS Live Monitor (Phase 6 + 2026-W18 retro). PM2 daily cron, no user.

Dispatch Agent(subagent_type="live-monitor") with prompt:
"Run ALL FOUR jobs from live-monitor.md:
 Job 1: Activate (live, pending) entries.
 Job 2: Monitor (live, running) for degradation (D1-D5).
 Job 3: Enforce grace period for (live, degraded).
 Job 4: Paper-stage health surveillance (P1-P4) — for every (paper, running) audition.
 Return your complete JSON report."

The agent has BACKEND_SERVICE_TOKEN in its environment for authenticated /live/* calls.

After the subagent returns, output ONLY its raw JSON report verbatim (first
char `{`, last char `}`). No prose, no markdown fences. The runner parses it
to relay paper-surveillance alerts to Telegram.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model haiku \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-livemon] claude exited ${EXIT_CODE}"

# ── Post-process: extract JSON report, relay paper-surveillance alerts to Telegram ──
LOG_FILE="${LOG_FILE}" python3 - << 'PYEOF'
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LOG_FILE = Path(os.environ['LOG_FILE'])
TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')

if not LOG_FILE.exists():
    sys.exit(0)
text = LOG_FILE.read_text(errors='replace')

def extract_largest_json(s):
    starts = [i for i, c in enumerate(s) if c == '{']
    candidates = []
    for start in starts:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == '{': depth += 1
            elif s[i] == '}':
                depth -= 1
                if depth == 0:
                    candidates.append(s[start:i+1])
                    break
    candidates.sort(key=len, reverse=True)
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue
    return None

report = extract_largest_json(text)
if report is None:
    print('[sas-livemon] no parseable JSON report')
    sys.exit(0)

j4 = (report.get('job4_paper_surveillance') or {})
alerts = j4.get('alerts') or []
high_or_med = [a for a in alerts if (a.get('severity') or '').lower() in ('high', 'medium')]
if not high_or_med:
    print(f"[sas-livemon] paper surveillance: {j4.get('healthy', 0)}/{j4.get('running', 0)} healthy, no alerts to relay")
    sys.exit(0)

if not TG_TOKEN or not TG_CHAT:
    print(f"[sas-livemon] {len(high_or_med)} paper-surveillance alert(s) but Telegram credentials missing")
    sys.exit(0)

lines = [f"⚠️ paper 세션 헬스체크 알림 ({len(high_or_med)}건)"]
for a in high_or_med:
    sev = (a.get('severity') or '?').upper()
    sid = a.get('strategy_id', '?')
    tag = a.get('tag', '?')
    msg = a.get('message') or ''
    age = a.get('age_hours')
    cyc = a.get('total_cycles')
    extras = []
    if age is not None: extras.append(f"age={age}h")
    if cyc is not None: extras.append(f"cycles={cyc}")
    extras_s = ' '.join(extras)
    lines.append(f"  [{sev}] {sid} {tag} {extras_s}")
    if msg:
        lines.append(f"    → {msg[:140]}")

text_msg = '\n'.join(lines)
if len(text_msg) > 3800:
    text_msg = text_msg[:3800] + '\n... (truncated)'

url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
data = urllib.parse.urlencode({
    'chat_id': TG_CHAT,
    'text': text_msg,
    'disable_web_page_preview': 'true',
}).encode()
try:
    with urllib.request.urlopen(url, data=data, timeout=10) as r:
        print(f'[sas-livemon] telegram HTTP {r.status} ({len(high_or_med)} alerts)')
except Exception as e:
    print(f'[sas-livemon] telegram error: {e}')
PYEOF

tail -3 "${LOG_FILE}" 2>/dev/null || true

find "${RUNS_DIR}" -name 'livemon_*.log' -mtime +90 -delete 2>/dev/null || true

exit "${EXIT_CODE}"
