#!/usr/bin/env bash
# Binance Phase 1 paper trading cycle for all active sessions (24/7 market).
# Wrapped by sas_loop_wrapper.sh.
#
# Runs: paper_session_cli run --all
# All active paper sessions (KR + Binance) processed in single call.
# KR sessions silently skip when ohlcv data is from prior trading day.
# Binance sessions advance using fresh UTC-day boundary data.
#
# Schedule: daily 00:30 UTC (09:30 KST) — 30 minutes after UTC-day rollover
# to allow archive data ingestion if any.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_binance_paper_cycle.log"

echo "[binance-paper] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[binance-paper] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

# Backfill funding rates (last 7 days) for all 14 paper-pool symbols.
# Required by funding_carry paradigm sessions (AXS/HBAR/COMP) — daily fetch
# captures all 3 daily funding periods (00/08/16 UTC).
echo "[binance-paper] funding rate backfill..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 fetch_binance_metrics.py \
  --symbols SOLUSDT,HBARUSDT,AXSUSDT,DOGEUSDT,UNIUSDT,PYTHUSDT,TONUSDT,ICPUSDT,ETCUSDT,JUPUSDT,COMPUSDT,WLDUSDT,LDOUSDT,1000LUNCUSDT \
  --source funding --funding-days 7 2>&1 | tail -40 | tee -a "${LOG_FILE}"

PYTHONPATH=. python3 -m scripts.paper_session_cli run --all 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[binance-paper] exit_code=${EC}" | tee -a "${LOG_FILE}"

# Append a status snapshot for monitoring
echo "" | tee -a "${LOG_FILE}"
echo "[binance-paper] post-cycle status:" | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.paper_session_cli status 2>&1 | tee -a "${LOG_FILE}"

exit "${EC}"
