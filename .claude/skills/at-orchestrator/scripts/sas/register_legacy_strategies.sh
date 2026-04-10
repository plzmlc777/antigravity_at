#!/usr/bin/env bash
# Register existing proven strategies into the SISDS audition pipeline.
# One-time migration script — safe to re-run (API enforces strategy_id uniqueness).
#
# These strategies enter at (sandbox, pending) so sandbox-researcher
# investigates them through the standard 10-step workflow.

set -euo pipefail

API="http://localhost:8001/api/v1/strategy-audition"
WEEK=$(date -u +%G-W%V)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%S)

echo "[legacy-register] Registering legacy strategies for week ${WEEK}..."

declare -A STRATEGIES
STRATEGIES[dip_martingale]="mean_reversion"
STRATEGIES[rsi_martingale]="mean_reversion"
STRATEGIES[ema_momentum]="momentum"
STRATEGIES[time_momentum]="time_based"
STRATEGIES[chart_pattern]="pattern"
STRATEGIES[funding_rate_arb]="arbitrage"
STRATEGIES[spot_futures_hedge]="arbitrage"
STRATEGIES[us_market_follow]="momentum"

SUCCESS=0
SKIP=0
FAIL=0

for STRATEGY_ID in "${!STRATEGIES[@]}"; do
  CATEGORY="${STRATEGIES[$STRATEGY_ID]}"

  RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API}" \
    -H 'Content-Type: application/json' \
    -d "{
      \"strategy_id\": \"${STRATEGY_ID}\",
      \"category\": \"${CATEGORY}\",
      \"audition_week\": \"${WEEK}\",
      \"stage\": \"sandbox\",
      \"stage_status\": \"pending\",
      \"audition_metadata\": {
        \"source\": \"legacy_migration\",
        \"migration_date\": \"${TIMESTAMP}\",
        \"proven_strategy\": true,
        \"file_path\": \".claude/skills/at-live-signal/scripts/strategies/${STRATEGY_ID}.py\"
      }
    }")

  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo "  [OK] ${STRATEGY_ID} (${CATEGORY}) → sandbox/pending"
    SUCCESS=$((SUCCESS + 1))
  elif echo "$BODY" | grep -q "already exists"; then
    echo "  [SKIP] ${STRATEGY_ID} — already registered"
    SKIP=$((SKIP + 1))
  else
    echo "  [FAIL] ${STRATEGY_ID} — HTTP ${HTTP_CODE}: ${BODY}"
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "[legacy-register] Done: ${SUCCESS} registered, ${SKIP} skipped, ${FAIL} failed"
