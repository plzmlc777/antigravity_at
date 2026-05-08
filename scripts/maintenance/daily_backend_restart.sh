#!/usr/bin/env bash
# Daily backend safety restart — defends against DB connection pool drift.
#
# Background: SQLAlchemy connection pool can accumulate idle/stale connections
# over multi-day uptime, eventually exhausting the limit and causing endpoint
# timeouts (e.g. /system/version, /auth/token). pool_pre_ping + pool_recycle
# mitigate but do not eliminate this. A daily restart at low-traffic hour
# guarantees a fresh pool.
#
# Schedule: 03:30 KST (18:30 UTC) — after account-keepalive (03:00 KST).
# Live sessions: paper-only on mint, automatically resumed on backend startup.

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

LOG_FILE="${HOME}/.pm2/logs/daily-backend-restart.log"
TS=$(date '+%Y-%m-%d %H:%M:%S %Z')

echo "[$TS] === Daily backend restart starting ===" >> "$LOG_FILE"

# Find PM2 binary
if [ -x "$ROOT_DIR/tools/node/bin/pm2" ]; then
    PM2="$ROOT_DIR/tools/node/bin/pm2"
elif command -v pm2 >/dev/null 2>&1; then
    PM2="pm2"
else
    echo "[$TS] ERROR: PM2 not found" >> "$LOG_FILE"
    exit 1
fi

# Snapshot before
BACKEND_PID=$($PM2 jlist 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(next((p['pid'] for p in d if p['name']=='at-backend'), 0))" 2>/dev/null || echo 0)
if [ "$BACKEND_PID" != "0" ] && [ -n "$BACKEND_PID" ]; then
    BACKEND_RSS=$(ps -p "$BACKEND_PID" -o rss= 2>/dev/null | tr -d ' ' || echo 0)
    echo "[$TS] Pre-restart at-backend pid=$BACKEND_PID rss=${BACKEND_RSS}KB" >> "$LOG_FILE"
fi

# Restart
"$PM2" restart at-backend at-frontend >> "$LOG_FILE" 2>&1
RC=$?

if [ $RC -eq 0 ]; then
    echo "[$TS] Restart OK" >> "$LOG_FILE"
else
    echo "[$TS] Restart FAILED rc=$RC" >> "$LOG_FILE"
fi

# Verify backend responds within 30s
for i in $(seq 1 15); do
    HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:8001/api/v1/system/version 2>/dev/null || echo 000)
    if [ "$HTTP" = "200" ]; then
        echo "[$TS] Health OK after ${i}x2s" >> "$LOG_FILE"
        exit 0
    fi
    sleep 2
done

echo "[$TS] WARNING: backend not responding 200 within 30s" >> "$LOG_FILE"
exit 1
