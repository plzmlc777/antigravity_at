#!/usr/bin/env bash
# 틱 수집 상주 — Binance Futures `@trade` 377종목, Parquet 20GB 롤링.
#
# ⚠ cron 이 아니라 **상주 프로세스**다. 웹소켓은 24시간마다 강제 종료되므로
#   재연결이 정상 동작이고, 수집기가 스스로 다시 붙는다. PM2 는 프로세스가
#   죽었을 때만 되살린다.
#
# 용량 (2026-08-26 실측)
#   한계 행당 4.38 B (파일 고정비 2,992 B — 행이 쌓일수록 여기 수렴)
#   ⚠ 유량 추정이 4.5배 빗나갔다. 61초 표본으로 1,669만건/일 로 봤는데
#     실제 첫 flush 는 7,490만건/일 이었다 — 짧은 표본은 시간대 편향을 탄다.
#   그래서 예산을 20 → 50GB 로 올렸다. 디스크 여유 273GB 라 감당된다.
#   50GB 면 대략 5~6개월(한계값 기준) ~ 50일(초기 관측값 기준).
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1
cd backend || exit 1
[ -f venv/bin/activate ] || { echo "[tick] venv 없음"; exit 1; }
source venv/bin/activate

BUDGET="${TICK_BUDGET_GB:-50}"
UNI="${TICK_UNIVERSE:-configs/rsi_paper_universe.txt}"
echo "[tick] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) budget=${BUDGET}GB uni=${UNI}"

exec nice -n 5 python3 scripts/binance/tick_collector.py \
  --universe "${UNI}" --budget-gb "${BUDGET}"
