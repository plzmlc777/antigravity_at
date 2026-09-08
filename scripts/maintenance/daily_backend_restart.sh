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

# Verify backend responds.
#
# ⚠ 예전엔 30초(15x2s)만 기다렸다. at-backend 는 기동에 그보다 오래 걸려
#   (메모리 400MB 급) **매일 종료코드 1** 로 끝났고, 그래서 진짜 실패와
#   구분이 안 됐다 — 언젠가 정말 안 올라와도 로그가 똑같아 보인다.
#   2026-09-08 대표님 지시로 120초로 늘렸다.
# ⚠ $TS 는 스크립트 시작 때 한 번 잡은 값이라 경과가 안 보인다. 여기서는
#   현재 시각과 실제 대기 초를 함께 남긴다.
HEALTH_WAIT_S=${HEALTH_WAIT_S:-120}
T0=$(date +%s)
for i in $(seq 1 $((HEALTH_WAIT_S / 2))); do
    HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:8001/api/v1/system/version 2>/dev/null || echo 000)
    if [ "$HTTP" = "200" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Health OK after $(($(date +%s) - T0))s" >> "$LOG_FILE"
        exit 0
    fi
    sleep 2
done

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] WARNING: backend not responding 200 within ${HEALTH_WAIT_S}s (last HTTP=$HTTP)" >> "$LOG_FILE"
exit 1
