#!/usr/bin/env bash
# 3군 paradigm dispatch — 매일 1건 자율 발굴 (Phase B, 2026-07-11 배선).
# Wrapped by sas_loop_wrapper.sh.
#
# Flow:
#   1. backend/runs/research_track/queue.json에서 pending 가설 1건 pop
#      (비어 있으면 SELF-RECOMMEND 모드 — architect가 novel 가설 자체 발의)
#   2. headless claude -p로 paradigm-architect 서브에이전트 투입
#      → R-0 prescreen → R-1 → R-2 → R-3 → R-4 자율 수행
#      → R-4 PASS 시 tier_promotion_queue.json 등록 (2군 리그가 시드)
#      → FAIL 시 graveyard 문서 생성
#   3. PARADIGM_RESULT 라인 파싱 → Telegram 통보
#
# Schedule: daily 18:45 UTC (03:45 KST) — keepalive(18:00)·backend-restart(18:30) 이후.
# Auth: ~/.claude/oauth_token.env (독립 grant 장기 토큰).
# Smoke test: PARADIGM_DISPATCH_SMOKE=1 → 플러밍만 검증 (architect 미투입).

set -uo pipefail

export PATH="${HOME}/.npm-global/bin:${PATH}"
# shellcheck disable=SC1091
[ -f "${HOME}/.claude/oauth_token.env" ] && source "${HOME}/.claude/oauth_token.env"

PROJECT_ROOT="$(pwd)"
QUEUE="${PROJECT_ROOT}/backend/runs/research_track/queue.json"
RUNS_DIR="${PROJECT_ROOT}/backend/runs/research_track/dispatch_logs"
LOCK_FILE="${RUNS_DIR}/.dispatch.lock"
mkdir -p "${RUNS_DIR}"

# Single-instance guard — R 파이프라인은 수 시간 걸릴 수 있음.
if [ -f "${LOCK_FILE}" ]; then
  PREV_PID=$(cat "${LOCK_FILE}" 2>/dev/null || echo "")
  if [ -n "${PREV_PID}" ] && kill -0 "${PREV_PID}" 2>/dev/null; then
    echo "[paradigm-dispatch] previous run still active (pid ${PREV_PID}), skipping"
    exit 0
  fi
  rm -f "${LOCK_FILE}"
fi
echo "$$" > "${LOCK_FILE}"
trap 'rm -f "${LOCK_FILE}"' EXIT

TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${RUNS_DIR}/dispatch_${TS}.log"
echo "[paradigm-dispatch] start ${TS}"
echo "[paradigm-dispatch] log ${LOG_FILE}"

# ── 1. 큐에서 pending 1건 pop (없으면 SELF-RECOMMEND) ─────────────────
HYPO=$(python3 - "$QUEUE" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
path = sys.argv[1]
try:
    d = json.load(open(path))
except Exception:
    d = {"queue": []}
for e in d.get("queue", []):
    if e.get("status", "pending") == "pending":
        e["status"] = "in_progress"
        e["dispatched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json.dump(d, open(path, "w"), indent=1, ensure_ascii=False)
        print(e.get("hypothesis", ""))
        break
PYEOF
)

if [ -n "${HYPO}" ]; then
  HYPO_BLOCK="Hypothesis (from queue): ${HYPO}"
else
  HYPO_BLOCK="SELF-RECOMMEND mode: no queued hypothesis. Read backend/runs/research_track/INDEX.json, backend/runs/research_track/PARADIGM_QUEUE_2026Q3.md (lessons + family retires). Propose ONE novel hypothesis yourself — respect all family retires and the 77+ lesson prescreen, prefer non-OHLCV substrate per Lesson #77 (event/announcement/microstructure/positioning over raw price patterns). No DNA duplicate (5/6 dim overlap → pick another)."
fi
echo "[paradigm-dispatch] mode: $([ -n "${HYPO}" ] && echo queue || echo self-recommend)"

# ── 2. architect 투입 ────────────────────────────────────────────────
if [ "${PARADIGM_DISPATCH_SMOKE:-0}" = "1" ]; then
  PROMPT='Print exactly this one line and nothing else: PARADIGM_RESULT: {"smoke": true}'
  TIMEOUT=120
else
  PROMPT=$(cat <<PROMPT_EOF
Paradigm dispatch (daily cron, 3군 자동 발굴. No user present — never ask questions).

${HYPO_BLOCK}

Dispatch Agent(subagent_type="paradigm-architect") with a prompt to:
1. Run the 3군 pipeline per .claude/plans/tier3_redesign.md (2026-08-08 재설계 —
   R-2/R-3/R-4 elite gate 는 폐기됐다. 자금 위험이 0인 3군에 실전급 기준을 세운 것이
   79일 무배출의 원인이었고, 과적합 판별은 2군 forward 가 담당한다):
     G0  기존 R-0 prescreen 유지 (DNA 중복 / 무정보 / 수수료 하한 / 표본 밀도)
     G1  시간가중 성과 — **단일 종목·단일 스펙으로 판정한다. 다종목 요구는 폐기됐다.**
     G2  실행가능성 — lookahead / 지연 후 마찰여유 / 실행주기 정합
2. G1·G2 판정은 **직접 하지 말고 반드시 코드로 실행**한다:
     python3 scripts/research/tier3_gate.py --trades <backtest_trades.json> \
       --lookahead-clean true|false --edge-after-1bar <x> --friction <x> \
       --hold-min <x> --cycle-min <x> --out runs/research_track/<paradigm>/tier3_gate__<sym>.json
   거래 JSON 은 [{"entry_ts","exit_ts","net_ret"}] 형식이다. G2 인자를 생략하면
   UNKNOWN 으로 차단된다 — 측정하지 않았으면 통과시키지 않는다.
   현재 실행 인프라의 사이클 주기는 **1440분(하루 1회)** 이다.
3. 게이트 PASS 시에만 승격 큐에 올린다. 이때도 손으로 JSON 을 편집하지 말고
   같은 CLI 의 --enqueue 를 쓴다 (게이트 결과가 큐 엔트리에 함께 기록되고,
   governor 가 시드 직전에 그 값을 다시 확인한다):
     ... --enqueue --name <name> --spec configs/paper_sessions/<f>.json \
         --paradigm <paradigm> --symbol <SYM>
   Paper specs ONLY. NEVER create live/real sessions, never touch live_bot_sessions or exchange accounts.
4. 게이트 FAIL 시: graveyard document per convention, update INDEX.
5. Respect backfill discipline (archive-first, <10GB, no parallel downloaders).

After the subagent returns, print exactly one line starting with:
PARADIGM_RESULT: {"paradigm": "<name>", "final_phase": "<R-x|GRAVEYARD|R5_ENQUEUED>", "verdict": "<one-line summary>"}
Nothing else after that line.
PROMPT_EOF
)
  TIMEOUT="${PARADIGM_DISPATCH_TIMEOUT:-14400}"
fi

timeout "${TIMEOUT}" claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  < /dev/null > "${LOG_FILE}" 2>&1
EXIT_CODE=$?
echo "[paradigm-dispatch] claude exit=${EXIT_CODE}"

RESULT_LINE=$(grep -E "^PARADIGM_RESULT:" "${LOG_FILE}" 2>/dev/null | tail -1 || true)
echo "[paradigm-dispatch] ${RESULT_LINE:-no result line}"

# ── 3. 큐 상태 갱신 ──────────────────────────────────────────────────
python3 - "$QUEUE" "${RESULT_LINE:-}" "${HYPO:-}" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
queue_path, result_line, hypo = sys.argv[1], sys.argv[2], sys.argv[3]
if hypo:
    try:
        d = json.load(open(queue_path))
        for e in d.get("queue", []):
            if e.get("status") == "in_progress" and e.get("hypothesis") == hypo:
                e["status"] = "done" if result_line else "failed"
                e["result"] = result_line[:500]
                e["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        json.dump(d, open(queue_path, "w"), indent=1, ensure_ascii=False)
    except Exception as exc:
        print(f"queue update failed: {exc}")
PYEOF

# ── 4. Telegram 통보 (backend venv 필요) ─────────────────────────────
MODE_KO=$([ -n "${HYPO}" ] && echo "큐" || echo "SELF-RECOMMEND")
if [ -n "${RESULT_LINE:-}" ]; then
  MSG="🔬 3군 디스패치 완료 (${MODE_KO})
${RESULT_LINE#PARADIGM_RESULT:}"
else
  MSG="🔬 3군 디스패치 실패 (${MODE_KO}) — exit=${EXIT_CODE}, 로그: ${LOG_FILE}"
fi
(
  cd "${PROJECT_ROOT}/backend" || exit 1
  # shellcheck disable=SC1091
  source venv/bin/activate
  PYTHONPATH=. python3 -c "
import sys
from scripts.binance.lifecycle_live_signal_driver import _telegram_notify
_telegram_notify(8, sys.argv[1])
print('telegram sent')
" "${MSG}"
) || echo "[paradigm-dispatch] telegram notify failed"

# Prune logs older than 90 days
find "${RUNS_DIR}" -name 'dispatch_*.log' -mtime +90 -delete 2>/dev/null || true

exit "${EXIT_CODE}"
