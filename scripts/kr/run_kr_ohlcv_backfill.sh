#!/usr/bin/env bash
# KR 1m OHLCV daily incremental backfill (ka10080).
# Wrapped by sas_loop_wrapper.sh.
#
# Pulls minute bars for KR paper-session symbols from Kiwoom and inserts
# only rows newer than the table's current max — never deletes existing
# history. Idempotent and safe to re-run.
#
# Recommended schedule: daily 16:00 KST (07:00 UTC) Mon-Fri — 30 min after
# market close, before composer-flow-backfill and the KR paper cycles.

set -uo pipefail

SYMBOLS="${KR_OHLCV_SYMBOLS:-005930,061090,122630,000660,007210,055550,196170}"
MAX_PAGES="${KR_OHLCV_MAX_PAGES:-30}"

LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_kr_ohlcv_backfill.log"

echo "[kr-ohlcv] symbols=${SYMBOLS} max_pages=${MAX_PAGES} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[kr-ohlcv] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

PYTHONPATH=. python3 kr_ohlcv_incremental_backfill.py \
  --symbols "${SYMBOLS}" --max-pages "${MAX_PAGES}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[kr-ohlcv] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
