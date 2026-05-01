#!/usr/bin/env bash
# Crypto Meta-Learner weekly retrain — atomic swap of canonical model file.
# Recommended fire time: Sundays 02:00 UTC.
#
# Per-symbol mode: CRYPTO_META_RETRAIN_SYMBOL=<symbol> (e.g. BTCUSDT).
# Default: BTCUSDT.

set -uo pipefail

SYMBOL="${CRYPTO_META_RETRAIN_SYMBOL:-BTCUSDT}"
LOG_DIR="$(pwd)/backend/runs/crypto_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_meta_retrain_${SYMBOL}.log"

echo "[crypto-meta-retrain] symbol=${SYMBOL} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[crypto-meta-retrain] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
source venv/bin/activate

PYTHONPATH=. python3 retrain_meta_learner_crypto.py --symbol "$SYMBOL" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[crypto-meta-retrain] symbol=${SYMBOL} exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
