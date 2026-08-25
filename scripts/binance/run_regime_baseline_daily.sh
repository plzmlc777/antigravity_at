#!/usr/bin/env bash
# 국면 기질 일일 갱신 — 최근 구간만 다시 계산해 기존 표에 덮는다.
#
# 왜 최근 며칠을 **다시** 계산하나 (2026-08-25)
#   선도수익률(fwd_48h)은 그 시간이 지나야 여문다. 어제 만든 표에서 최근 이틀은
#   아직 NaN 이거나 반쪽이다. 겹쳐 다시 계산해 덮어야 값이 채워진다.
#   `--merge` 가 (symbol, date) 중복을 **새 값 우선**으로 처리한다.
#
# 일정: 매일 03:00 UTC (12:00 KST) — ohlcv-1m-daily(02:30 UTC) 다음
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1
LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_regime_baseline.log"

cd backend || exit 1
[ -f venv/bin/activate ] || { echo "[regime] venv 없음" | tee -a "${LOG_FILE}"; exit 1; }
source venv/bin/activate

DAYS="${REGIME_DAYS:-14}"   # ⚠ 최소 4일(=MIN_BARS 144봉)보다 넉넉히. 선도 48h 가 여물 시간을 겹친다
FROM=$(date -u -d "${DAYS} days ago" +%Y-%m-%d)
UNI="${REGIME_UNIVERSE:-configs/rsi_paper_universe.txt}"
echo "[regime] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) from=${FROM} uni=${UNI}" \
  | tee -a "${LOG_FILE}"

PYTHONPATH=. nice -n 10 ionice -c3 python3 -m scripts.research.build_regime_baseline \
  --universe "${UNI}" --from "${FROM}" --merge --workers 4 \
  2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[regime] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
