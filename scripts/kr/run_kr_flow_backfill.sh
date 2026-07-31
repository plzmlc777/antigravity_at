#!/usr/bin/env bash
# Daily KR investor flow backfill (ka10059) -> investor_flow_daily.
# Wrapped by sas_loop_wrapper.sh.
#
# Feeds the surviving per-symbol paper strategies, which read this table as
# their signal source: S60 (005930) 외인+기관 consensus, S61 (122630) 외국인
# 5일 누적 trend. Without a fresh row here neither session produces a signal.
#
# Was run_composer_flow_backfill.sh (Composer Phase 6). The composer/pattern KR
# track was retired 2026-07-11 and this job repurposed; renamed 2026-07-31
# because the old name read as dead-track leftovers.
#
# Recommended schedule: daily 16:30 KST (07:30 UTC) — gives ka10059 ~1 hour
# after market close to publish today's data.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/kr_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_kr_flow_backfill.log"

# Defaults match the ecosystem env; both live sessions are covered.
SYMBOLS="${KR_FLOW_SYMBOLS:-005930,122630}"

# Today's date in KST (the date ka10059 just published) and a small look-back
# window to recover any missed days.
TODAY=$(TZ=Asia/Seoul date +%Y%m%d)
MIN_DT=$(TZ=Asia/Seoul date -d "5 days ago" +%Y%m%d)

echo "[kr-flow] symbols=${SYMBOLS} start=${TODAY} min=${MIN_DT} ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[kr-flow] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 fetch_kiwoom_investor_flow.py \
  --symbols "${SYMBOLS}" \
  --start-dt "${TODAY}" --min-dt "${MIN_DT}" 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[kr-flow] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
