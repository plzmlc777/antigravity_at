#!/usr/bin/env bash
# RSI 1군 자율 대조 감시 — 10분마다.
#
# 왜 (2026-08-31)
#     고아 포지션이 익절·손절 없이 1.3시간 살아 있었고, 그 사이 증거금이 막혀
#     +12.83$ 짜리 신호를 놓쳤다. **대표님이 텔레그램을 보고 말씀하실 때까지
#     시스템은 몰랐다.** 대조 도구는 있었지만 사람이 「정기 점검」을 칠 때만
#     돌았고, 08-30 14:05 이후 19시간 35분 동안 한 번도 안 돌았다.
#
#     옛 1군(신상저격수)에는 `lifecycle-hourly-reconcile` 이 매시 :20 에 있다.
#     RSI 가 1군을 물려받을 때 그 감시가 따라오지 않았다 — 교훈 #102.
#
# ⚠ 아무것도 고치지 않는다. 보고 알릴 뿐이다.
#   자동 개입은 판단을 요구하고, 판단은 대표님 몫이다.
#
# ⚠ 매매 사이클(:00/:30)과 겹치지 않게 :05 오프셋으로 돈다.
#   같은 순간에 REST 를 두드리면 가중치 한도에서 서로 방해한다.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1           # backend/

LOG_DIR="$(pwd)/runs/paper_sessions/rsi_extreme/sentry_logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d).log"

{
  echo "[rsi-sentry] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ./venv/bin/python3 scripts/binance/rsi_live_sentry.py --account 8
  echo "[rsi-sentry] rc=$?"
} >> "$LOG_FILE" 2>&1

# 로그가 무한히 자라지 않게 30일만 남긴다
find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null

exit 0
