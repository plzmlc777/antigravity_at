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

# lifecycle short — PAPER + REAL (2026-08-12 대표님 지시로 REAL 재개).
#
# ── 2026-08-12 재개 ──────────────────────────────────────────────────
# 재개되는 트랙은 이전과 **다른 물건**이다. 오늘 소스의 재진입 버그를 고쳤다:
#   `bn_lifecycle_decay*` 가 -1.0 을 영원히 내보내 익절 뒤 즉시 재진입했다.
#   실계좌는 REUSDT 한 종목에 8회, ARXUSDT 에 3회 진입했다. 패러다임은
#   "상장 Day-1 종가 숏 **한 번**" 이다. 이제 진입 신호 창이 상장 후 3일만
#   열린다(listing_date/entry_window_days). 조기청산 신호(양수)는 보존.
#
# 재개 근거와 한계 (2026-08-12 백테스트, 순수 규칙·재진입 없음, n=251):
#   표본 안 (R-4 이전, 241건) 중앙 +18.32% / 승률 57.7% / t +5.70
#   표본 밖 (이후,   10건)    중앙 +19.09% / 승률 60.0% / t +0.61
#   → 알파 감쇠는 안 보이나 **표본 밖 10건으로는 통계 확인 불가**.
#     상위 1건을 빼면 +0.73% 로 견고성이 없다. 20~25건에서 재판정한다.
#
# 이번 재개의 주목적은 수익이 아니라 **3자 동기화 검증**이다 —
# 백테스트 / System-2 페이퍼 / 실계좌가 같은 규칙으로 같은 값을 내는지.
# 대조 도구: scripts/research/lifecycle_three_way_sync.py
#
# 위험 통제 (기존, lifecycle_live_signal_driver.py):
#   REAL_MAX_SYMBOL_FRACTION 0.20  — 종목당 지갑의 20% (MDD 플래토)
#   REAL_MARGIN_FRACTION     0.97  — 가용 마진의 97%
#   보유창 후 하드 강제청산       — 2026-07-27 고아 포지션 사고 대응
#
# ── 2026-08-08 정지 당시 기록 (보존) ─────────────────────────────────
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
echo "[binance-paper] lifecycle auto-link new listings (paper + REAL)..." | tee -a "${LOG_FILE}"
# ── 2026-08-12: 추종 신호 earlyexit_d14 → **earlyexit_d7** (대표님 지시) ──
#
# `--name-filter` 기본값이 earlyexit_d14 라 지금까지 실계좌는 d14 를 따랐다.
# 131건 캘린더 포트폴리오 시뮬(회귀 검사 통과, 현행 사이징 20%x1 고정):
#
#   신호            포착%   MDD%     최악$    총손익$   거래당$   SL%   조기%   놓침
#   earlyexit_d7    80.2  -41.43  -202.19  1277.79   12.17  25.7  51.4   26
#   h21             67.2  -35.73  -141.39   833.32    9.47  31.8   0.0   43
#   earlyexit_d14   66.4  -50.39  -102.66   378.81    4.35  34.5  24.1   44   ← 종전
#   base            61.1  -37.70   -80.31   325.82    4.07  38.8   0.0   51
#
# d7 은 d14 대비 포착률 +13.8%p(놓침 44→26), SL 34.5→25.7%, 총손익 3.4배,
# **MDD 는 -50.4→-41.4% 로 개선**. 조기청산이 51.4% 발동해 자본이 빨리 돌아온다.
# 단 최악 단일거래가 -102.66 → -202.19 로 2배다 — 자본 회전이 빨라 포지션이
# 커지기 때문이다. 사이징(20%x1)은 이번 변경에서 건드리지 않는다.
#
# 참고: 거래 **단위** 백테스트(251건)에서는 d7 이 base 대비 -14.08%p(t -3.05)로
# 최악이었다. 포트폴리오에서 뒤집힌 이유는 조기청산이 기회를 두 배로 늘리기
# 때문이다. 거래당 지표만으로 판정하면 안 된다는 사례다.
PYTHONPATH=. python3 scripts/binance/lifecycle_live_provision.py \
  --auto-link --name-filter earlyexit_d7 \
  --account-id 12 --notional 200 --initial-capital 10000 \
  --real-account-id 8 \
  --commit 2>&1 | tee -a "${LOG_FILE}"
# ── 실행기 사전 관문 (통합 실행기 계획 5단계, 2026-08-13) ──────────────
#
# 골든·파리티 검사는 만들어 놓고 아무도 부르지 않으면 없는 것과 같다. 실제로
# `engine_parity_gate.py` 는 작성 후 3개월간 호출처가 0개였고, 그 사이
# 2026-08-08 사고(같은 policy, 다른 실행기, 다른 전략)로 실자금이 43일간
# 미검증 규칙으로 돌았다. 사람이 기억해서 돌리는 검사는 결국 안 돌아간다.
#
# 그래서 **주문 바로 앞**에 세운다. 단위 테스트 + 골든 재생(lifecycle 67건),
# 약 35초. 실패하면 reconcile 을 건너뛰고 텔레그램으로 알린다 — 검사에 실패한
# 엔진으로 실자금을 굴리는 것보다 하루 쉬는 편이 낫다.
#
# 실패 검증 완료: 커널을 일부러 깨뜨리자 단위 2실패 + 골든 54/67 불일치로
# 종료코드 1 을 냈다. 막지 못하는 관문은 관문이 아니므로 반드시 확인해야 한다.
echo "[binance-paper] 실행기 사전 관문..." | tee -a "${LOG_FILE}"
# `cmd | tee` 의 종료코드는 기본적으로 **tee** 의 것이다. 이 파일 상단에
# `set -o pipefail` 이 있어 지금은 옳게 동작하지만, 그 설정이 130행 위에 있어
# 나중에 누가 지우면 **관문이 항상 통과로 읽힌다**. PIPESTATUS 로 못박는다.
./scripts/binance/run_engine_gates.sh 2>&1 | tee -a "${LOG_FILE}"
GATE_RC=${PIPESTATUS[0]}

if [ "${GATE_RC}" -eq 0 ]; then
  # reconcile: System-2 의 현재 side 를 링크된 PAPER + REAL 세션에 미러링.
  echo "[binance-paper] lifecycle live signal reconcile (paper + REAL)..." | tee -a "${LOG_FILE}"
  PYTHONPATH=. python3 scripts/binance/lifecycle_live_signal_driver.py \
    --submit --include-real 2>&1 | tee -a "${LOG_FILE}"
else
  echo "[binance-paper] **관문 실패 — reconcile/주문 건너뜀**" | tee -a "${LOG_FILE}"
fi

# Append a status snapshot for monitoring
echo "" | tee -a "${LOG_FILE}"
echo "[binance-paper] post-cycle status:" | tee -a "${LOG_FILE}"
PYTHONPATH=. python3 -m scripts.paper_session_cli status 2>&1 | tee -a "${LOG_FILE}"

exit "${EC}"
