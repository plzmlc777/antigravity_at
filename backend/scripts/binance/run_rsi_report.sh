#!/usr/bin/env bash
# RSI 1군 정기 보고 — :02 / :32.
#
# 왜 (2026-08-31)
#     대표님: "왜 자동으로 보고하지 않는 거야?"
#     오전에 이상 감시는 자율로 만들었지만 **정기 보고는 사람이 쳐야 도는
#     상태로 뒀다.** 감시기가 「이상이 있을 때만」 운다면, 이건 「이상이
#     없어도 30분마다」 보낸다 — 조용한 것과 멈춘 것은 다르다.
#
# ⚠ 왜 :02/:32 인가
#     매매 사이클이 :00/:30 +20초에 돌고, 그 끝에 원장을 쓴다. 정각에
#     읽으면 **직전 사이클 결과를 못 본 보고**가 나간다.
#
# ⚠ 아무것도 고치지 않는다. 읽고 보낼 뿐이다.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1           # backend/

LOG_DIR="$(pwd)/runs/paper_sessions/rsi_extreme/report_logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d).log"

{
  echo "[rsi-report] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ./venv/bin/python3 scripts/binance/rsi_report.py --account 8
  echo "[rsi-report] rc=$?"
} >> "$LOG_FILE" 2>&1

find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null
exit 0
