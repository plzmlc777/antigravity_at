#!/usr/bin/env bash
# Crypto Meta-Strategy paper cycle — Phase 5 wire-in (Binance USDT-M Futures).
# Wrapped by sas_loop_wrapper.sh (PATH/.env injected by wrapper).
# 24/7 — recommended fire daily at 00:30 UTC (post-day boundary cycle).

set -uo pipefail

SESSION="${CRYPTO_META_SESSION:-BTCUSDT_meta_seed}"
LOG_DIR="$(pwd)/backend/runs/crypto_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_${SESSION}.log"

echo "[crypto-meta] session=${SESSION} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[crypto-meta] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

PYTHONPATH=. python3 run_crypto_meta_cycle.py --session "${SESSION}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[crypto-meta] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
