#!/usr/bin/env bash
# SISDS meta-observer — Phase 8 (CIO-20260410-001).
#
# Weekly system health audit. Reviews pipeline throughput, calibration trend,
# lesson quality, and agent performance. Generates recommendations.
#
# Schedule: 0 4 * * 0 UTC (13:00 KST Sunday, after weekly-judge on Monday AM)
# Uses Opus model (deep analysis needed).
#
# Post-processing:
#   - extracts the agent's JSON report from claude -p output
#   - persists to runs/sas/metaobs_latest.json
#   - sends a human-readable summary to Telegram

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"
RUNS_DIR="${PROJECT_ROOT}/.claude/skills/at-orchestrator/runs/sas"
LOCK_FILE="${RUNS_DIR}/.metaobs.lock"
STATUS_FILE="${RUNS_DIR}/metaobs_latest.json"

mkdir -p "${RUNS_DIR}"

# Load .env (TELEGRAM_BOT_TOKEN / CHAT_ID) — wrapper already does this when
# triggered by PM2, but manual `bash run_meta_observer.sh` invocations also need it.
if [ -f "${PROJECT_ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
  set +a
fi

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

PROMPT=$(cat <<'PROMPT_EOF'
SISDS Meta-Observer (Phase 8). PM2 weekly cron, no user.

Dispatch Agent(subagent_type="meta-observer") with prompt:
"Run the full 7-step meta-observer.md workflow.
 Gather pipeline health, calibration trend, lesson quality, agent performance.
 Generate weekly system health report with recommendations.
 Return your complete JSON report."

After the subagent returns, output ONLY its raw JSON report verbatim. No
prose, no markdown fences, no leading or trailing text. The very first
character of your response must be `{` and the very last must be `}`.
This output is parsed by python json.loads on the runner side.
PROMPT_EOF
)

claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  --model opus \
  < /dev/null \
  > "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "[sas-metaobs] claude exited ${EXIT_CODE}"

# ── Post-process: extract JSON, persist, push summary to Telegram ─────────
LOG_FILE="${LOG_FILE}" \
STATUS_FILE="${STATUS_FILE}" \
python3 - << 'PYEOF'
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LOG_FILE = Path(os.environ['LOG_FILE'])
STATUS_FILE = Path(os.environ['STATUS_FILE'])
TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')

if not LOG_FILE.exists():
    print('[sas-metaobs] WARN: log file missing — claude -p produced no output')
    sys.exit(0)

text = LOG_FILE.read_text(errors='replace')

# Find the largest balanced {...} block that parses as JSON.
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
    print('[sas-metaobs] WARN: no parseable JSON in log; raw tail follows')
    print(text[-500:])
    sys.exit(0)

STATUS_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
print(f'[sas-metaobs] report saved → {STATUS_FILE}')

# Build human-readable Telegram summary.
ph = report.get('pipeline_health') or {}
ch = report.get('calibration_health') or {}
recs = report.get('recommendations') or []
notes = (report.get('notes') or '').strip()

def pct(x):
    if x is None: return '-'
    try: return f'{float(x)*100:.0f}%'
    except Exception: return str(x)

lines = [
    f"📊 SISDS 주간 자가 audit ({report.get('report_week', '?')})",
    "",
    f"전체: {ph.get('assessment', '?')}  /  Calibration: {ch.get('assessment', '?')}",
    "",
    "[파이프라인]",
    f"  생성/주:        {ph.get('generation_rate', '?')}",
    f"  Sandbox 통과율: {pct(ph.get('sandbox_pass_rate'))}",
    f"  Paper 승격률:   {pct(ph.get('paper_promotion_rate'))}",
    f"  Paper 통과율:   {pct(ph.get('paper_pass_rate'))}",
    f"  Live 운영:      {ph.get('live_count', 0)}",
    "",
    f"[Calibration]  CIR={ch.get('cir', '-')} ({ch.get('cir_interpretation', '?')}) / 최악 transition: {ch.get('worst_transition', '-')}",
    "",
    f"[권고사항 {len(recs)}건]",
]

priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
sorted_recs = sorted(recs, key=lambda r: priority_order.get((r.get('priority') or '').lower(), 9))

for r in sorted_recs[:6]:
    pri = (r.get('priority') or '?').upper()
    target = r.get('target', '?')
    finding = (r.get('finding') or '')[:140]
    rec = (r.get('recommendation') or '')[:160]
    lines.append(f"  • [{pri}] {target}")
    lines.append(f"    발견: {finding}")
    lines.append(f"    제안: {rec}")
if len(recs) > 6:
    lines.append(f"  ... 외 {len(recs) - 6}건")

if notes:
    lines.extend(['', '[요약]', notes[:500]])

msg = '\n'.join(lines)
if len(msg) > 3800:
    msg = msg[:3800] + '\n... (truncated)'

print('---SUMMARY (also sent to Telegram if configured)---')
print(msg)

if TG_TOKEN and TG_CHAT:
    url = f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage'
    data = urllib.parse.urlencode({
        'chat_id': TG_CHAT,
        'text': msg,
        'disable_web_page_preview': 'true',
    }).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            print(f'[sas-metaobs] telegram HTTP {r.status}')
    except Exception as e:
        print(f'[sas-metaobs] telegram error: {e}')
else:
    print('[sas-metaobs] telegram credentials missing — summary printed only')
PYEOF

find "${RUNS_DIR}" -name 'metaobs_*.log' -mtime +180 -delete 2>/dev/null || true

exit "${EXIT_CODE}"
