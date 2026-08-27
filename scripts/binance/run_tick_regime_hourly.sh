#!/usr/bin/env bash
# 틱 국면 기질 매시 갱신 — 후행은 끝까지, 선도는 여문 만큼만.
#
# 왜 매시인가 (2026-08-27)
#   `state()`/`market_state()` 는 실시간 후행 판단에 쓰인다. 하루 한 번 돌리면
#   그 값이 최대 24시간 묵는다. 실제로 선도 지평 6시간 때문에 최근 앵커를
#   버리다가 state() 가 7시간 묵은 값을 내놓은 적이 있다 — 매시로 돌린다.
#
# 왜 --merge 인가
#   선도(fwd/mfe/mae)는 시간이 지나야 여문다. 어제 만든 표의 최근 몇 시간은
#   아직 NaN 이다. 겹쳐 다시 계산해 덮어야 값이 채워진다.
#   (symbol, hour) 중복은 **새 값 우선**.
#
# 일정: 매시 정각 5분 (틱 수집기 flush 900초 주기 뒤로 여유)
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1
LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H)_tick_regime.log"

cd backend || exit 1
[ -f venv/bin/activate ] || { echo "[tickreg] venv 없음" | tee -a "${LOG_FILE}"; exit 1; }
source venv/bin/activate

# ⚠ 최근 구간만 다시 계산해 덮는다. 전체를 매시 다시 돌리면 틱이 쌓일수록
#   비용이 선형으로 는다(182일이면 감당 못 한다). 겹침은 선도 최장 지평(6h)
#   보다 넉넉히 잡는다.
HOURS="${TICK_REGIME_HOURS:-16}"
echo "[tickreg] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) hours_back=${HOURS}" \
  | tee -a "${LOG_FILE}"

PYTHONPATH=. nice -n 15 ionice -c3 python3 -m scripts.research.build_tick_regime \
  --hours-back "${HOURS}" --merge 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[tickreg] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
