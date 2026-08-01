#!/usr/bin/env bash
# 임시 태스크 — 미국 트랙 가설 큐에 매시 1건씩 자동 추가.
# Wrapped by sas_loop_wrapper.sh.
#
# 대표님 지시(2026-08-01 22:14 KST): "내일까지 임시로 한 시간에 1개의 전략을
# 추가하는 태스크". 초기 큐를 빠르게 채우기 위한 일회성 조치이며, 상시 운영용이
# 아니다 — 아래 DEADLINE 이 지나면 스스로 아무 일도 하지 않고 종료한다.
#
# 만료 후 정리: pm2 delete us-hypothesis-seeder && pm2 save
#
# Schedule: 매시 17분 (PM2 cron). 정각을 피해 다른 잡과 겹치지 않게 한다.

set -uo pipefail

# ── 자동 만료 ────────────────────────────────────────────────────────
# 2026-08-02(일) 23:59 KST 까지만 동작. 이후 호출은 즉시 no-op.
DEADLINE_EPOCH=$(date -d '2026-08-02 23:59:00' +%s 2>/dev/null || echo 0)
NOW_EPOCH=$(date +%s)
if [ "${DEADLINE_EPOCH}" -ne 0 ] && [ "${NOW_EPOCH}" -gt "${DEADLINE_EPOCH}" ]; then
  echo "[us-seeder] 만료됨(2026-08-02 23:59 KST 이후) — 아무 작업도 하지 않음."
  echo "[us-seeder] 정리: pm2 delete us-hypothesis-seeder && pm2 save"
  exit 0
fi

LOG_DIR="$(pwd)/backend/runs/us_hypothesis_seeder/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_us_seeder.log"

echo "[us-seeder] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

PROJECT_ROOT="$(pwd)"
cd "${PROJECT_ROOT}/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[us-seeder] ERROR: venv not found" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

# ── 현재 큐 상태를 프롬프트에 주입 (중복 발의 차단) ──────────────────
QUEUE_SNAPSHOT=$(PYTHONPATH=. python3 -m scripts.us_hypothesis_queue list 2>/dev/null | tail -30)
echo "[us-seeder] 현재 큐:" | tee -a "${LOG_FILE}"
echo "${QUEUE_SNAPSHOT}" | tee -a "${LOG_FILE}"

cd "${PROJECT_ROOT}" || exit 1

PROMPT=$(cat <<PROMPT_EOF
미국 ETF 트랙 가설 큐 시딩 (매시 cron, 사용자 없음 — 절대 질문하지 말 것).

목표: **새로운 미국 시장 전략 축 1건**을 조사해 큐에 추가한다.

현재 큐 (axis_class 중복 금지):
${QUEUE_SNAPSHOT}

절차:
1. WebSearch 로 미국 트레이딩 커뮤니티(r/algotrading, r/LETFs, r/thetagang,
   Bogleheads, composer.trade, QuantConnect, Quantpedia, EliteTrader 등)에서
   실제로 논의되는 규칙 기반 전략을 조사한다. 매번 다른 검색어를 쓸 것.
2. 아래 **미국 트랙 확정 제약**에 비추어 사용 가능한지 판정한다:
   - 공매도 불가 (키움 증거금 매수·매도 100%) → LONG 표현만 허용
   - 왕복 수수료 0.502% 고정 → 고빈도·소폭엣지는 자동 탈락 (Lesson #80)
   - 분봉은 2026-01 이후 7개월뿐, 일봉은 6.7년 → intraday 축 금지
   - elite gate: 거래당 edge >= +2%, trades/yr >= 12, util >= 30%, Sharpe >= 1.5
   - Lesson #78 유동성 게이트 / #81 위험조정(Sharpe·MDD) 필수
   - 데이터는 무료만 (yfinance, FRED, 키움 API). 유료 API 금지.
3. 제약을 통과하는 축 1건을 골라 다음 명령으로 추가한다:
   cd backend && PYTHONPATH=. python3 -m scripts.us_hypothesis_queue add \\
     --title "..." --hypothesis "..." --source "..." \\
     --axis-class "..." --data-deps "..." --constraints "...|..." \\
     --priority N --notes "..."
   hypothesis 는 R-0 프리스크린이 바로 읽을 수 있게 구체적으로(진입/청산/보유/
   유니버스/판정선) 쓴다. constraints 에는 이 가설이 우리 제약에 걸리는 지점을 적는다.
4. 기존 axis_class 와 겹치면 다른 축을 고른다. 겹치는 것밖에 없으면 추가하지 말고
   그 사실을 결과 줄에 적는다.

절대 금지: 실거래/라이브 세션 접근, 백테스트 실행(여기서는 큐 등록만), 유료 API.

마지막에 정확히 한 줄만 출력:
US_SEED_RESULT: {"id": "<us-XXX 또는 none>", "axis_class": "<...>", "title": "<...>"}
PROMPT_EOF
)

timeout "${US_SEEDER_TIMEOUT:-1800}" claude -p "${PROMPT}" \
  --permission-mode bypassPermissions \
  < /dev/null >> "${LOG_FILE}" 2>&1
EXIT_CODE=$?
echo "[us-seeder] claude exit=${EXIT_CODE}" | tee -a "${LOG_FILE}"

RESULT_LINE=$(grep -E "^US_SEED_RESULT:" "${LOG_FILE}" 2>/dev/null | tail -1 || true)
echo "[us-seeder] ${RESULT_LINE:-no result line}" | tee -a "${LOG_FILE}"

find "${LOG_DIR}" -name '*_us_seeder.log' -mtime +14 -delete 2>/dev/null || true

exit "${EXIT_CODE}"
