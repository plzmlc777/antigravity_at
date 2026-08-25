#!/usr/bin/env bash
# `ohlcv_1m` 일일 갱신 — 바이낸스 공개 아카이브 (무료·키 불필요).
#
# 왜 (2026-08-25)
#   구 `ohlcv` 테이블을 채우던 `binance-ohlcv-backfill` 을 걷어내려면 그 전에
#   `ohlcv_1m` 을 매일 채우는 경로가 있어야 한다. 없이 지우면 1분봉이
#   영구히 멈춘다. 실사에서 `ohlcv_1m` 이 이미 **6~7일 뒤처져** 있었다.
#
# 안전
#   `extend_ohlcv_1m_archive.py` 는 절대 삭제하지 않는다 — 임시 테이블 COPY 후
#   `ON CONFLICT DO NOTHING`. 같은 날을 다시 받아도 무해하다.
#   ⚠ `collect_ohlcv_hourly.py --bulk` 는 구간을 줘도 **종목 전체를 지운다**.
#     2026-08-20 에 그걸로 175종목 9,184만 행을 잃었다. 이 경로를 쓰지 마라.
#
# 일정: 매일 02:30 KST (binance-ohlcv-backfill 02:00 다음)
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1              # 저장소 루트
LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_ohlcv_1m_daily.log"

cd backend || exit 1
if [ ! -f venv/bin/activate ]; then
  echo "[ohlcv-1m] ERROR: venv 없음 $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

# 최근 며칠만 다시 받는다 — 이미 있는 행은 건너뛰므로 겹쳐도 싸다.
DAYS="${OHLCV_1M_DAYS:-7}"
FROM=$(date -u -d "${DAYS} days ago" +%Y-%m-%d)
TO=$(date -u +%Y-%m-%d)
UNI="${OHLCV_1M_UNIVERSE:-configs/rsi_paper_universe.txt}"

echo "[ohlcv-1m] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) from=${FROM} to=${TO} uni=${UNI}" \
  | tee -a "${LOG_FILE}"

PYTHONPATH=. nice -n 10 ionice -c3 python3 -m scripts.extend_ohlcv_1m_archive \
  --universe "${UNI}" --from "${FROM}" --to "${TO}" --sleep 0.3 \
  2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[ohlcv-1m] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
