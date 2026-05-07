#!/usr/bin/env bash
# Composer Phase 6 — daily KR investor flow backfill (ka10059).
# Wrapped by sas_loop_wrapper.sh.
#
# Pulls the latest day's investor flow for each production paper-session symbol
# so the next composer-paper-cycle run has fresh data.
#
# Recommended schedule: daily 16:30 KST (07:30 UTC) — gives ka10059 ~1 hour
# after market close to publish today's data.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_composer_flow_backfill.log"

# Symbols mirror configs/paper_sessions/*_pattern_flow.json
SYMBOLS="${COMPOSER_FLOW_SYMBOLS:-122630,007210,055550}"

# Today's date in KST (the date ka10059 just published) and a small look-back
# window to recover any missed days.
TODAY=$(TZ=Asia/Seoul date +%Y%m%d)
MIN_DT=$(TZ=Asia/Seoul date -d "5 days ago" +%Y%m%d)

echo "[composer-flow] symbols=${SYMBOLS} start=${TODAY} min=${MIN_DT} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[composer-flow] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 fetch_kiwoom_investor_flow.py \
  --symbols "${SYMBOLS}" \
  --start-dt "${TODAY}" --min-dt "${MIN_DT}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[composer-flow] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
