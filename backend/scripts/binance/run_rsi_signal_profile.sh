#!/usr/bin/env bash
# RSI 신호 발생 구조 — 주 1회 기록.
#
# 왜 (2026-09-02)
#     1군 48시간 무신호를 파다가 **주간 신호 빈도가 3주 전 42회 → 최근 8~9회**
#     로 꺾인 것이 드러났다. 국면인지 알파 감쇠인지는 한 번의 관측으로 못
#     가른다 — 대조 지표까지 넣어 봐도 절반만 설명됐다(변동성은 관계가 거꾸로,
#     방향은 2주 전 랠리만 설명). **매주 같은 자로 쌓아야** 갈린다.
#
# ⚠ 유니버스는 지금 것 하나로 고정해 전 구간을 훑는다 — 주간 차이가
#   유니버스 변경 탓이 아님을 설계로 보장한다.
#
# ⚠ 무겁다: 359종목 × 봉 999 ≈ 가중치 1,800. 주 1회로 묶어 둔다.
#   매매 사이클(:00/:30)과 겹치지 않게 :17 에 돈다.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1           # backend/

LOG_DIR="$(pwd)/runs/paper_sessions/rsi_extreme/signal_profile"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/run_$(date -u +%Y%m%d).log"

{
  echo "[rsi-signal-profile] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ./venv/bin/python3 scripts/binance/rsi_signal_profile.py
  echo "[rsi-signal-profile] rc=$?"
} >> "$LOG_FILE" 2>&1

find "$LOG_DIR" -name "run_*.log" -mtime +120 -delete 2>/dev/null
exit 0
