#!/usr/bin/env bash
# Tier governor — 2군(System-2 paper pool) 자동 승격/강등 집행.
# Wrapped by sas_loop_wrapper.sh.
#
# day30_decision_protocol.md 결정 트리를 매일 기계 집행:
# TERMINATE 자동, PROMOTE/RESEED는 Telegram 통보(1군 진입은 수동 승인).
# 2026-07-11 대표님 "2군 3군 승격 강등 완전 자동화" 지시로 신설.
#
# Schedule: daily 03:40 UTC (12:40 KST) — binance-paper-cycle(02:30) +
# lifecycle-spawner(03:00) 이후, 당일 최신 equity/trades 반영 상태에서 판정.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/tier_governor/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_tier_governor.log"

echo "[tier-governor] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[tier-governor] ERROR: venv not found" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 scripts/tier_governor.py 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[tier-governor] exit_code=${EC}" | tee -a "${LOG_FILE}"

# Prune logs older than 90 days
find "${LOG_DIR}" -name '*_tier_governor.log' -mtime +90 -delete 2>/dev/null || true

exit "${EC}"
