#!/usr/bin/env bash
# 미국 ETF 페이퍼 세션 1사이클 + US 리그 거버너.
# Wrapped by sas_loop_wrapper.sh.
#
# Schedule: daily 21:40 UTC — us-rank-snapshot(21:10)이 순위 스냅샷과 일봉을
# 갱신한 뒤에 돈다. 미국장은 일봉 기준이라 하루 1사이클이면 충분하다.
#
# 리그는 바이낸스와 분리돼 있다(--market us, 좌석 12석). 미국은 일봉 스윙이라
# 거래 빈도가 낮아 분봉 intraday 인 바이낸스와 같은 순위표에서 겨룰 수 없다.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/us_paper_cycle/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_us_paper_cycle.log"

echo "[us-paper-cycle] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[us-paper-cycle] ERROR: venv not found" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 -m scripts.paper_session_cli run --all --exchange us 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[us-paper-cycle] cycle_exit=${EC}" | tee -a "${LOG_FILE}"

PYTHONPATH=. python3 -m scripts.tier_governor --market us 2>&1 | tee -a "${LOG_FILE}"
echo "[us-paper-cycle] governor_exit=${PIPESTATUS[0]}" | tee -a "${LOG_FILE}"

find "${LOG_DIR}" -name '*_us_paper_cycle.log' -mtime +90 -delete 2>/dev/null || true

exit "${EC}"
