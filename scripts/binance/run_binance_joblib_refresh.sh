#!/usr/bin/env bash
# Binance paradigm-source joblib daily incremental refresh.
# Wrapped by sas_loop_wrapper.sh.
#
# Refreshes two joblib datasets consumed by paper paradigm sessions:
#   1. backend/runs/premium_index/{SYM}_premium.joblib (1d premium for
#      bn_premium_index_zscore + bn_premium_velocity_zscore sources)
#   2. backend/runs/microstructure/{SYM}_full_metrics.joblib (5m OI/positioning/
#      taker buy-sell for bn_oi_price_decoupling source)
#
# Both scripts gained --refresh flag (incremental: read existing joblib, fetch
# only days after its last date, merge + dedupe). Original behavior preserved
# without --refresh.
#
# Schedule: daily 02:15 UTC (11:15 KST). Between binance-ohlcv-backfill
# (02:00 UTC) and binance-paper-cycle (02:30 UTC) so paradigm sessions read
# fresh joblibs in the same daily cycle.
#
# Without this, sessions iterate fresh ohlcv timestamps but compute z-scores
# from stale joblib data → pred=0 indefinitely (incident 2026-05-13: 6
# paradigm sessions advanced timestamps but pred remained 0.0 because their
# joblib inputs were stuck at 2026-05-04).

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_binance_joblib_refresh.log"

echo "[binance-joblib] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[binance-joblib] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

# Match paper-pool universe in binance-paper-cycle / binance-ohlcv-backfill.
SYMBOLS="${BINANCE_JOBLIB_SYMBOLS:-SOLUSDT,HBARUSDT,AXSUSDT,DOGEUSDT,UNIUSDT,PYTHUSDT,TONUSDT,ICPUSDT,ETCUSDT,JUPUSDT,COMPUSDT,WLDUSDT,LDOUSDT,1000LUNCUSDT,AVAXUSDT,LINKUSDT}"
DAYS="${BINANCE_JOBLIB_DAYS:-365}"

echo "[binance-joblib] symbols=${SYMBOLS} days=${DAYS}" | tee -a "${LOG_FILE}"

echo "[binance-joblib] premium_index refresh..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.backfill_premium_index \
  --symbols "${SYMBOLS}" --days "${DAYS}" --refresh 2>&1 | tee -a "${LOG_FILE}"
EC1="${PIPESTATUS[0]}"

echo "[binance-joblib] microstructure refresh..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.backfill_microstructure \
  --symbols "${SYMBOLS}" --days "${DAYS}" --refresh 2>&1 | tee -a "${LOG_FILE}"
EC2="${PIPESTATUS[0]}"

echo "[binance-joblib] exit_codes premium=${EC1} micro=${EC2}" | tee -a "${LOG_FILE}"
if [ "${EC1}" != "0" ] || [ "${EC2}" != "0" ]; then
  exit 1
fi
exit 0
