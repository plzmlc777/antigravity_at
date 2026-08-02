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

# ── 인증 ─────────────────────────────────────────────────────────────
# headless claude 는 대화형 로그인을 못 하므로 독립 grant 장기 토큰을 주입한다.
# 없으면 "Not logged in · Please run /login" 로 exit 1 (실측 2026-08-01).
# run_paradigm_dispatch.sh 와 동일 패턴.
[ -f "${HOME}/.claude/oauth_token.env" ] && source "${HOME}/.claude/oauth_token.env"

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
# 제목만 주면 axis_class 이름만 바꾼 같은 메커니즘이 반복된다(실측 2026-08-02:
# 15건 중 10건이 "거시지표 레짐 → 월간 자산배분"으로 수렴). 최근 건은 가설
# 본문 일부까지 주입해 **메커니즘 클래스** 수준에서 중복을 판정하게 한다.
QUEUE_SNAPSHOT=$(PYTHONPATH=. python3 -m scripts.us_hypothesis_queue list 2>/dev/null | tail -30)
RECENT_DETAIL=$(PYTHONPATH=. python3 - <<'PYEOF' 2>/dev/null
import json
from pathlib import Path
q = json.loads(Path("configs/us_hypothesis_queue.json").read_text(encoding="utf-8"))["queue"]
for e in q[-6:]:
    print(f"- [{e['id']}] axis_class={e['axis_class']}")
    print(f"  {e['hypothesis'][:220]}")
PYEOF
)
echo "[us-seeder] 현재 큐:" | tee -a "${LOG_FILE}"
echo "${QUEUE_SNAPSHOT}" | tee -a "${LOG_FILE}"

cd "${PROJECT_ROOT}" || exit 1

PROMPT=$(cat <<PROMPT_EOF
미국 ETF 트랙 가설 큐 시딩 (매시 cron, 사용자 없음 — 절대 질문하지 말 것).

목표: **새로운 미국 시장 전략 축 1건**을 조사해 큐에 추가한다.

현재 큐:
${QUEUE_SNAPSHOT}

최근 등록분 상세 (메커니즘 클래스 판정용):
${RECENT_DETAIL}

## 포화된 클래스 — 이 방향은 더 넣지 말 것

**(A) 신호 축 포화** (07:25 조임): "거시지표 하나로 레짐 판정 → 월간 자산배분 교체"
(OAS / 2s10s / CPI / ISM PMI / 실현변동성 / 10개월 SMA / 듀얼모멘텀 / 섹터·팩터
로테이션). 지표만 바꾼 변형도 금지.

**(B) 실행 형태 포화** (14:55 조임 — 지금 가장 중요): 소재는 다양해졌으나 실행
구조가 **"지표로 ETF 순위 매겨 상위 N개를 월간 교체"** 하나로 다시 몰렸다
(조임 이후 9건 중 7건). 신호가 새로워도 이 형태면 **중복으로 간주하고 금지**한다.

→ 다음 중 **다른 실행 형태**를 취할 것:
   - **이벤트 트리거형** — 특정 조건 발생 시점에만 진입, 평소 무포지션
     (예: 괴리율이 임계 초과한 날에만, 지수 편입 발표일에만)
   - **조건부 보유형** — 조건 충족 동안만 보유하고 깨지면 즉시 청산(고정 주기 아님)
   - **페어/스프레드형** — 두 자산의 상대가격에 베팅 (롱 표현 가능한 조합만)
   - **임계 돌파형** — 순위가 아니라 절대 임계 기준 진입
   - **다단계 필터형** — 조건 2~3개를 순차 통과한 소수 종목만
   hypothesis 본문에 **실행 형태를 명시**할 것.

## 우선 탐색할 미개척 영역 (이 중에서 고르면 가산점)
- **한국 개인 수급** — us_rank_snapshot.rank_type='kiwoom_trade' 로 매일 적재 중.
  키움 고객(한국 개인)의 미국 ETF 거래 집중 순위. 미국 현지 데이터로 복제 불가.
- **주간거래 괴리율** — rank_type='day_disparity'. Blue Ocean 오버나이트 세션과
  정규장 종가의 괴리. 역시 우리만 가진 축.
- **오버나이트 vs 정규장 분리 수익률** — 키움 일봉 종가는 오버나이트 포함,
  시가는 정규장 시가. 두 구간을 분리해 각각의 수익 구조를 보는 축.
- **ETF 내부 구조** — NAV 괴리, 자금유출입, 구성종목 집중도
- **옵션 만기·분기 리밸런싱 수급** — 만기주 전후, 분기말 리밸런싱 압력
- **개별주 이벤트** — 실적 발표, 지수 편입/제외 (단 공매도 불가 제약 유의)
- **일중 구조** — 단 분봉은 2026-01 이후 7개월뿐이므로 R-0 advisory 한정

절차:
1. WebSearch 로 미국 트레이딩 커뮤니티(r/algotrading, r/LETFs, r/thetagang,
   r/options, Bogleheads, composer.trade, QuantConnect, Quantpedia, EliteTrader,
   SeekingAlpha, TradingView 아이디어 등)에서 실제로 논의되는 규칙 기반 전략을
   조사한다. 매번 다른 검색어를 쓰고, 위 미개척 영역과 연결되는 것을 우선 찾는다.
2. 아래 **미국 트랙 확정 제약**에 비추어 사용 가능한지 판정한다:
   - 공매도 불가 (키움 증거금 매수·매도 100%) → LONG 표현만 허용
   - 왕복 수수료 0.502% 고정 → 고빈도·소폭엣지는 자동 탈락 (Lesson #80)
   - 분봉은 2026-01 이후 7개월뿐, 일봉은 6.7년 → intraday 축 금지
   - elite gate: 거래당 edge >= +2%, trades/yr >= 12, util >= 30%, Sharpe >= 1.5
   - Lesson #78 유동성 게이트 / #81 위험조정(Sharpe·MDD) 필수
   - 데이터는 무료만 (yfinance, FRED, 키움 API). 유료 API 금지.
2-1. **우선순위 규율** (지금까지 P2 남발로 변별력이 사라졌다):
   - P1 = 기존 데이터(일봉 60 코어 + 567 레버리지 + 1,393 신규, 분봉 8종,
          us_rank_snapshot)만으로 **즉시 검증 가능** AND 위 미개척 영역에 해당
   - P2 = 기존 데이터로 즉시 검증 가능하나 미개척 영역은 아님
   - P3 = yfinance/FRED 등 **외부 데이터 확보가 선행**돼야 함
   - P4 = 그 외 / 감쇠 가능성이 높은 잘 알려진 아노말리
   외부 데이터가 필요하면 P3 을 넘길 수 없다.

3. 제약을 통과하는 축 1건을 골라 다음 명령으로 추가한다:
   cd backend && PYTHONPATH=. python3 -m scripts.us_hypothesis_queue add \\
     --title "..." --hypothesis "..." --source "..." \\
     --axis-class "..." --data-deps "..." --constraints "...|..." \\
     --priority N --notes "..."
   hypothesis 는 R-0 프리스크린이 바로 읽을 수 있게 구체적으로(진입/청산/보유/
   유니버스/판정선) 쓴다. constraints 에는 이 가설이 우리 제약에 걸리는 지점을 적는다.
4. 중복 판정은 **(신호 축, 실행 형태) 두 축 모두**로 한다. axis_class 이름이
   달라도, 신호가 새로워도, **실행 형태가 "월간 순위 로테이션"이면 중복**이다.
   겹치지 않는 축을 못 찾으면 **추가하지 말고** 결과 줄에 id "none" 과 사유를
   적는다 — 억지로 채우는 것보다 비우는 편이 낫다. 지금은 큐가 24건이라
   양보다 다양성이 중요하다.

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

# ── 큐 파일만 커밋·푸시 ──────────────────────────────────────────────
# 시더는 민트에서 돌면서 민트 워킹트리의 큐 JSON 만 고친다. 그대로 두면 하루치
# ~25건이 민트에만 쌓이고 GitHub·로컬과 갈라진다(배포 시 pull 충돌의 원인).
#
# 스테이징 범위를 큐 파일 하나로 못박는다 — 민트에는 연구 산출물 등 커밋되지
# 않은 로컬 변경이 다수 있어, 범위를 넓히면 의도치 않은 파일을 쓸어담는다.
#
# push 실패(로컬에서 먼저 푸시해 non-fast-forward 등)는 경고만 남기고 넘어간다.
# 커밋 자체는 민트에 남으므로 유실되지 않고, 다음 성공 시 함께 올라간다.
QUEUE_REL="backend/configs/us_hypothesis_queue.json"
cd "${PROJECT_ROOT}" || exit 1

if git diff --quiet -- "${QUEUE_REL}" 2>/dev/null; then
  echo "[us-seeder] 큐 변경 없음 — 커밋 생략" | tee -a "${LOG_FILE}"
else
  SEED_ID=$(echo "${RESULT_LINE}" | grep -oE '"id": *"[^"]*"' | head -1 | cut -d'"' -f4)
  SEED_TITLE=$(echo "${RESULT_LINE}" | grep -oE '"title": *"[^"]*"' | head -1 | cut -d'"' -f4)
  git add -- "${QUEUE_REL}"
  git commit -q -m "chore(us): 가설 큐 시딩 ${SEED_ID:-?} — ${SEED_TITLE:-untitled}

us-hypothesis-seeder 자동 커밋 (매시 1건, 2026-08-02 만료 예정).
스테이징 범위는 큐 JSON 한 파일로 고정." 2>&1 | tee -a "${LOG_FILE}"
  if git push -q origin master 2>>"${LOG_FILE}"; then
    echo "[us-seeder] 큐 커밋·푸시 완료 (${SEED_ID:-?})" | tee -a "${LOG_FILE}"
  else
    echo "[us-seeder] WARN: push 실패 — 커밋은 민트에 남아 있음. 다음 회차나 수동 푸시로 반영됨" | tee -a "${LOG_FILE}"
  fi
fi

find "${LOG_DIR}" -name '*_us_seeder.log' -mtime +14 -delete 2>/dev/null || true

exit "${EXIT_CODE}"
