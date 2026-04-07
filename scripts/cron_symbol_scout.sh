#!/bin/bash
# Daily symbol-scout cron.
# Usage:
#   cron_symbol_scout.sh binance   (crypto: every day)
#   cron_symbol_scout.sh kr        (Korean: weekdays only, 1h before open)
#
# Produces .claude/hot_candidates/<market>_YYYYMMDD.json (KST date) and cleans files >7d old.
set -e
cd /home/hcpark/auto_trading

MARKET=${1:-binance}
TODAY=$(TZ=Asia/Seoul date +%Y%m%d)
YDAY=$(TZ=Asia/Seoul date -d yesterday +%Y%m%d)
OUTDIR=/home/hcpark/auto_trading/.claude/hot_candidates
LOGDIR=/home/hcpark/auto_trading/logs/cron
mkdir -p "$OUTDIR" "$LOGDIR"

LOGFILE="$LOGDIR/symbol_scout_${MARKET}_${TODAY}.log"

# Cleanup old files (>7 days)
find "$OUTDIR" -name "*.json" -mtime +7 -delete 2>/dev/null || true
find "$LOGDIR" -name "symbol_scout_*.log" -mtime +7 -delete 2>/dev/null || true

echo "[$(date -u +%FT%TZ)] symbol-scout START market=$MARKET TODAY=$TODAY (KST)" > "$LOGFILE"

YDAY_FILE="$OUTDIR/${MARKET}_${YDAY}.json"
OUT_FILE="$OUTDIR/${MARKET}_${TODAY}.json"

if [ "$MARKET" = "binance" ]; then
    PROMPT="symbol-scout 에이전트를 SCAN_CRYPTO 모드로 실행해줘.

작업:
1. Binance Futures 시장을 스캔하여 forward-looking 관점의 top 10 후보 리스트를 작성.
2. 어제 파일이 있으면 change_from_yesterday 계산: $YDAY_FILE
3. 결과를 정확히 다음 경로에 JSON으로 저장: $OUT_FILE
4. 에이전트 정의(.claude/agents/symbol-scout.md)의 출력 스키마 엄수.
5. 완료 후 간단한 1~2줄 한국어 확인 메시지만 출력."
elif [ "$MARKET" = "kr" ]; then
    CTX_FILE="/tmp/symbol_scout_kr_ctx_${TODAY}.json"
    echo "[$(date -u +%FT%TZ)] preparing KR context..." >> "$LOGFILE"
    /home/hcpark/auto_trading/backend/venv/bin/python /home/hcpark/auto_trading/scripts/prepare_kr_context.py --out "$CTX_FILE" >> "$LOGFILE" 2>&1
    if [ ! -s "$CTX_FILE" ]; then
        echo "[$(date -u +%FT%TZ)] ERROR: KR context file empty or missing" >> "$LOGFILE"
        echo "{\"scan_date\":\"$(TZ=Asia/Seoul date +%Y-%m-%d)\",\"market\":\"kospi_kosdaq\",\"top_candidates\":[],\"notes\":\"context fetch failed\"}" > "$OUT_FILE"
        exit 1
    fi
    PROMPT="symbol-scout 에이전트를 SCAN_KR 모드로 실행해줘.

작업:
1. 한국 주식 시장 컨텍스트 파일을 Read: $CTX_FILE
2. 어제 파일이 있으면 change_from_yesterday 계산: $YDAY_FILE
3. Forward-looking top 10 후보를 선별하여 정확히 다음 경로에 JSON으로 저장: $OUT_FILE
4. 에이전트 정의(.claude/agents/symbol-scout.md)의 출력 스키마 엄수.
5. 품질 필터(관리종목, orderWarning, auditInfo) 적용 필수.
6. 완료 후 간단한 1~2줄 한국어 확인 메시지만 출력."
else
    echo "Unknown market: $MARKET (expected: binance | kr)" >> "$LOGFILE"
    exit 1
fi

echo "[$(date -u +%FT%TZ)] invoking claude CLI..." >> "$LOGFILE"
/usr/bin/claude -p "$PROMPT" --permission-mode bypassPermissions >> "$LOGFILE" 2>&1

# Cleanup context file
[ "$MARKET" = "kr" ] && rm -f "$CTX_FILE"

if [ -s "$OUT_FILE" ]; then
    echo "[$(date -u +%FT%TZ)] SUCCESS: $OUT_FILE ($(wc -c < "$OUT_FILE") bytes)" >> "$LOGFILE"
else
    echo "[$(date -u +%FT%TZ)] FAIL: output file missing or empty" >> "$LOGFILE"
    exit 1
fi
