#!/usr/bin/env bash
# Daily dashboard refresh: fetch all sources -> build index.html.
# Env: DASH_OUTDIR (csv dir), DASH_SITE (output html), DASH_PY (python bin).
set -uo pipefail
cd "$(dirname "$0")"
PY="${DASH_PY:-python3}"
ts() { TZ='Asia/Seoul' date '+%Y-%m-%d %H:%M:%S KST'; }
echo "[$(ts)] refresh start (OUTDIR=${DASH_OUTDIR:-default} SITE=${DASH_SITE:-default})"
for s in fetch_fx fetch_commodities fetch_market_funds fetch_market_credit fetch_semis fetch_oil fetch_freight fetch_rates fetch_reports; do
  if $PY "$s.py"; then echo "  ok  $s"; else echo "  WARN $s failed (keeping last-good CSV)"; fi
done
if $PY judge_etf.py; then echo "  ok  judge_etf"; else echo "  WARN judge_etf failed (keeping last judgment)"; fi
if $PY build_site.py; then echo "[$(ts)] build ok"; else echo "[$(ts)] BUILD FAILED"; exit 1; fi
if $PY notify_telegram.py; then echo "  ok  notify_telegram"; else echo "  WARN notify_telegram failed"; fi
echo "[$(ts)] refresh done"
