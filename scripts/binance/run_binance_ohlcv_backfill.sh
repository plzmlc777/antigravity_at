#!/usr/bin/env bash
# Binance Futures 1m OHLCV daily incremental backfill from data.binance.vision archive.
# Wrapped by sas_loop_wrapper.sh.
#
# Why: paper paradigm sessions iterate through ohlcv timestamps. Without
# this job, ohlcv stops at initial backfill cutoff → sessions stall on the
# last available bar (incident 2026-05-13: 14 paradigm sessions cycles=18
# vs uniq_ts=1). Funding/OI/positioning backfills run in binance-paper-cycle
# but do not maintain price candles.
#
# Schedule: daily 02:00 UTC (11:00 KST). Binance Vision daily archive for
# the prior UTC day is reliably published by ~01:00 UTC, so 02:00 is safe.
# Runs before binance-paper-cycle (02:30 UTC) so the cycle sees fresh data.
#
# 겹침 2일(ON CONFLICT DO NOTHING 으로 멱등)로 아카이브 늦은 게시에 대비한다.
# catch-up 은 --auto-gap 이 종목별로 알아서 한다 — 수동 --days 지정 불필요.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_binance_ohlcv_backfill.log"

echo "[binance-ohlcv] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[binance-ohlcv] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

# 자기치유 모드 (2026-08-09). 하드코딩 목록 + 고정 일수를 버렸다.
#
# 왜 — 이 목록이 **세 번 연속 같은 사고**를 냈다:
#   2026-05-13  14개 세션이 마지막 봉에서 정지 (목록에 없던 종목)
#   2026-07-11  16/26 세션 정지 — ADA/BCH/BNB/FIL/LTC/NEAR/WIF/XRP 누락
#   2026-08-09  DB 1m 214종목 중 168개가 2026-05-12 에 정지. 유동성 통과
#               132종목 중 과거 온전+최신인 종목이 12개뿐이었고, 그 substrate
#               로 내린 3군 판정이 위조됐다 (paradigm 251: decay_ratio 0.138
#               GRAVEYARD → DB 재판정 0.481 PASS 반전).
# 목록을 손으로 늘리는 건 매번 사후 대응이고 신규 상장이 생기면 또 뚫린다.
#
# 이제:
#   --universe-min-vol  거래소 exchangeInfo + 24h 거래대금에서 매번 새로 받는다
#                       (DB 상태에 의존하지 않음, 신규 상장 자동 포함)
#   --auto-gap          종목별 DB 마지막 봉부터 채운다 (며칠 밀려도 스스로 복구)
#   --max-days          종목당 상한 — 초과분은 다음 실행이 이어받는다
#
# BINANCE_OHLCV_SYMBOLS 를 주면 유니버스에 **추가**된다 (대체가 아니라 합집합).
MIN_VOL="${BINANCE_OHLCV_MIN_VOL:-5000000}"
MAX_DAYS="${BINANCE_OHLCV_MAX_DAYS:-150}"
EXTRA_SYMBOLS="${BINANCE_OHLCV_SYMBOLS:-}"

ARGS=(--universe-min-vol "${MIN_VOL}" --auto-gap --max-days "${MAX_DAYS}")
if [ -n "${EXTRA_SYMBOLS}" ]; then
  ARGS+=(--symbols "${EXTRA_SYMBOLS}")
fi

echo "[binance-ohlcv] min_vol=${MIN_VOL} max_days=${MAX_DAYS} extra=${EXTRA_SYMBOLS:-없음}" | tee -a "${LOG_FILE}"

PYTHONPATH=. python3 -m scripts.backfill_ohlcv_archive \
  "${ARGS[@]}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[binance-ohlcv] exit_code=${EC}" | tee -a "${LOG_FILE}"

exit "${EC}"
