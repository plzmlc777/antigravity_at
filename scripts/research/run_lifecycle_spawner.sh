#!/usr/bin/env bash
# Daily auto-spawn of lifecycle paper sessions for newly listed Binance perpetuals.
# Wrapped by sas_loop_wrapper.sh.
#
# Workflow per run:
#   1. Re-fetch /fapi/v1/exchangeInfo, update listing_dates.json
#   2. Identify listings aged 1-14 days, not in blocklist (stocks/commodities),
#      not already covered by an existing paper session (per-variant detection)
#   3. Backfill that symbol's 1m ohlcv (35 days) — shared across variants
#   4. Create per-listing PaperSession(s) via paper_session_cli — FIVE variants:
#        - baseline (R-4 PASS): Day 1 short, hold to Day 30
#        - baseline_h21 (R-3 plateau optimum, 2026-05-20): same entry, hold=21.
#          R-3 grid plateau top-10 favored hold=21 (median +24-28%, win 62-66%)
#          over hold=30 — parallel A/B measures whether the shorter horizon
#          preserves median while freeing capital ~30% sooner
#        - early_exit_d14 (R-2-bis +1.41% mean uplift, +2.5pp win, t-stat 1.70→2.13):
#          Day 1 short; at Day 14 if vol_cliff>=0.40, exit early
#        - early_exit_d7 (2026-05-18 aggressive expansion): same as d14 but
#          earlier check_day for shorter capital cycling — A/B measures
#          whether earlier exit signal preserves the +1.41% uplift while
#          freeing capital sooner
#        - bear_skip (R-3 regime gate, 2026-05-20): same entry semantics but
#          suppresses short when BTC 30d pre-listing return <= -0.05 (R-3
#          BEAR cohort n=38 median -50.08% win 42.1% — catastrophic). Regime
#          decision FROZEN at spawn time. A/B vs baseline measures regime-
#          filter uplift in NEUTRAL+BULL listings (no-op) and avoided drawdown
#          in BEAR listings (no entry)
#
# Schedule: daily 03:00 UTC (12:00 KST) — AFTER binance-paper-cycle (02:30 UTC)
# so new sessions appear on the NEXT day's cycle (acceptable — lifecycle hold
# is 30 days, missing one day at entry is negligible).
#
# Idempotent: re-runs same day produce 0 spawns (existing sessions detected per
# variant — baseline and early_exit sessions for the same symbol are tracked
# independently).

set -uo pipefail

LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_lifecycle_spawner.log"

echo "[lifecycle-spawner] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"

cd "$(pwd)/backend" || exit 1

if [ ! -f venv/bin/activate ]; then
  echo "[lifecycle-spawner] ERROR: venv not found at $(pwd)/venv" | tee -a "${LOG_FILE}"
  exit 1
fi
# shellcheck disable=SC1091
source venv/bin/activate

PYTHONPATH=. python3 -m scripts.research.lifecycle_session_spawner \
  --refresh-listings \
  --policy all \
  --baseline-hold-days 30,21 \
  --early-exit-check-days 7,14 \
  --early-exit-vc-threshold 0.40 \
  --bear-skip-threshold -0.05 \
  2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
echo "[lifecycle-spawner] exit_code=${EC}" | tee -a "${LOG_FILE}"
exit "${EC}"
