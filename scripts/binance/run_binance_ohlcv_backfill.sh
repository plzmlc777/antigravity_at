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
# --days 3 gives 2-day overlap (idempotent via ON CONFLICT DO NOTHING) for
# robustness against archive late-publication. For first run / catch-up
# scenarios use a larger --days value manually.

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

# Paper-pool universe (14 alts) + BTCUSDT/ETHUSDT used as cross-symbol leaders
# (bn_cross_lead_lag / bn_cross_eth sources). Without BTC/ETH fresh, leader
# bars stall and cross paradigms emit pred=0 indefinitely.
SYMBOLS="${BINANCE_OHLCV_SYMBOLS:-BTCUSDT,ETHUSDT,SOLUSDT,HBARUSDT,AXSUSDT,DOGEUSDT,UNIUSDT,PYTHUSDT,TONUSDT,ICPUSDT,ETCUSDT,JUPUSDT,COMPUSDT,WLDUSDT,LDOUSDT,1000LUNCUSDT,AVAXUSDT,LINKUSDT}"
DAYS="${BINANCE_OHLCV_DAYS:-3}"

echo "[binance-ohlcv] symbols=${SYMBOLS} days=${DAYS}" | tee -a "${LOG_FILE}"

PYTHONPATH=. python3 -m scripts.backfill_ohlcv_archive \
  --symbols "${SYMBOLS}" --days "${DAYS}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[binance-ohlcv] exit_code=${EC}" | tee -a "${LOG_FILE}"

exit "${EC}"
