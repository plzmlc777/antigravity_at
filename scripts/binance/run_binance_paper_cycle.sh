#!/usr/bin/env bash
# Binance Phase 1 paper trading cycle for all active sessions (24/7 market).
# Wrapped by sas_loop_wrapper.sh.
#
# Runs: paper_session_cli run --all --exchange binance
# Only Binance USDT/USDC perp sessions advance here. KR sessions (6-digit
# tickers) are routed to composer-paper-cycle instead — see split rationale
# 2026-05-18 (avoid duplicate work + cleaner ownership per market).
#
# Schedule: daily 00:30 UTC (09:30 KST) — 30 minutes after UTC-day rollover
# to allow archive data ingestion if any.

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_binance_paper_cycle.log"

echo "[binance-paper] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[binance-paper] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

# STEP 0: spawn lifecycle sessions for NEW listings BEFORE the cycle runs, so a
# fresh listing is spawned (REST-backfilled) → cycled (entry signal) → auto-linked
# → reconciled (live entry) all in THIS single run = Day-1 entry. Previously the
# spawner ran on its own cron (12:00 KST) AFTER this cycle (11:30), so new sessions
# only entered the NEXT day (~Day-2). Idempotent: re-spawn finds 0 new.
echo "[binance-paper] lifecycle spawn new listings (REST backfill)..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.research.lifecycle_session_spawner \
  --refresh-listings --policy all \
  --baseline-hold-days 30,21 --early-exit-check-days 7,14 \
  --early-exit-vc-threshold 0.40 --bear-skip-threshold -0.05 2>&1 | tail -25 | tee -a "${LOG_FILE}"

# Backfill funding rates (last 7 days) for all 14 paper-pool symbols.
# Required by funding_carry paradigm sessions (AXS/HBAR/COMP) — daily fetch
# captures all 3 daily funding periods (00/08/16 UTC).
echo "[binance-paper] funding rate backfill..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 fetch_binance_metrics.py \
  --symbols SOLUSDT,HBARUSDT,AXSUSDT,DOGEUSDT,UNIUSDT,PYTHUSDT,TONUSDT,ICPUSDT,ETCUSDT,JUPUSDT,COMPUSDT,WLDUSDT,LDOUSDT,1000LUNCUSDT \
  --source funding --funding-days 7 2>&1 | tail -40 | tee -a "${LOG_FILE}"

# Forward-collection of positioning metrics for future paradigm research
# (research_track_master.md option A — added 2026-05-04). Binance REST caps
# at 30 days backward; we collect the latest 2-day window daily (overlap
# = idempotent via ON CONFLICT). Metrics:
#   - binance_positioning_metric: top_long_short_account / position,
#     global_long_short_account, taker_buy_sell
#   - binance_open_interest_hist: OI at 5m granularity
# Initial 30d backfill 2026-05-04. From here, daily forward-collection
# accumulates → ~60d data by 2026-06-03 (funding_carry Day 30) → enables
# OI dynamics + LSR positioning paradigms.
echo "[binance-paper] positioning + OI 5m forward-collection..." | tee -a "${LOG_FILE}"
POS_SYMBOLS="SOLUSDT,HBARUSDT,AXSUSDT,DOGEUSDT,UNIUSDT,PYTHUSDT,TONUSDT,ETCUSDT,JUPUSDT,COMPUSDT,WLDUSDT,LDOUSDT,AVAXUSDT,LINKUSDT"
PYTHONPATH=. python3 fetch_binance_metrics.py \
  --symbols "${POS_SYMBOLS}" \
  --source positioning --period 5m --positioning-days 2 2>&1 | tail -80 | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 fetch_binance_metrics.py \
  --symbols "${POS_SYMBOLS}" \
  --source oi --oi-period 5m --positioning-days 2 2>&1 | tail -30 | tee -a "${LOG_FILE}"

PYTHONPATH=. python3 -m scripts.paper_session_cli run --all --exchange binance 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[binance-paper] exit_code=${EC}" | tee -a "${LOG_FILE}"

# lifecycle short — PAPER 전용 (2026-08-08 대표님 지시로 1군 → 2군 강등).
#
# REAL 트랙을 끈 이유: 3개월 실계좌 운용에서 수익의 138%가 상위 4건에 몰렸고,
# 그 4건조차 진입이 38시간 지연된 우연에 크게 기대고 있었다(최대이득 ARX는 지연
# 덕에 +10%→+20%, 최대손실 REU는 지연 덕에 -50%→-13.7%). GRVTUSDT 마지막
# 포지션을 2026-08-08 17:42 청산(realized -37.92)하고 REAL 트랙을 정지한다.
# 페이퍼 트랙은 그대로 두어 계속 검증한다.
#
# 두 곳을 함께 꺼야 완전히 멈춘다:
#   (1) auto-link 의 --real-account-id  → 신규 상장마다 REAL 세션을 자동 생성
#   (2) reconcile 의 --include-real     → REAL 주문 실행
# 하나만 끄면 세션은 계속 생기거나(1 누락), 주문이 계속 나간다(2 누락).
# REAL 재개 시 두 플래그를 같이 되살릴 것.
echo "[binance-paper] lifecycle auto-link new listings (paper only)..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 scripts/binance/lifecycle_live_provision.py \
  --auto-link --account-id 12 --notional 200 --initial-capital 10000 \
  --commit 2>&1 | tee -a "${LOG_FILE}"
# reconcile: System-2 의 현재 side 를 링크된 PAPER 세션에 미러링.
echo "[binance-paper] lifecycle live signal reconcile (paper only)..." | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 scripts/binance/lifecycle_live_signal_driver.py --submit 2>&1 | tee -a "${LOG_FILE}"

# Append a status snapshot for monitoring
echo "" | tee -a "${LOG_FILE}"
echo "[binance-paper] post-cycle status:" | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.paper_session_cli status 2>&1 | tee -a "${LOG_FILE}"

exit "${EC}"
