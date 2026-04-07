#!/bin/bash
# 일간 CIO daily-review 워크플로우
# KST 16:00 (장 마감 후) 실행 권장
set -e
cd /home/hcpark/auto_trading
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
LOGDIR=/home/hcpark/auto_trading/.claude/verification_logs
mkdir -p "$LOGDIR"
OUT="$LOGDIR/${RUN_ID}_daily_review.md"
STATUS="$LOGDIR/${RUN_ID}_daily_review_STATUS.txt"

# 14일 이상 오래된 daily review 로그 정리
find "$LOGDIR" -name '*_daily_review*.md' -mtime +14 -delete 2>/dev/null || true
find "$LOGDIR" -name '*_daily_review_STATUS.txt' -mtime +14 -delete 2>/dev/null || true

echo "[$(date -u +%FT%TZ)] daily-review START" > "$STATUS"

/usr/bin/claude -p 'CIO 에이전트로 daily-review 워크플로우를 실행해줘. 백엔드 API http://localhost:8001. 단계:
1. ASSESS: ops-monitor + market-researcher 병렬 실행
2. PLAN: HEALTHY가 아닌 세션에 대해 strategy-advisor → backtest-analyst → risk-manager 순차
3. EXECUTE: risk-manager가 approved일 때만 trade-executor 실행

오늘 GCP 서버의 모든 라이브 세션에 대해 풀 사이클 수행. 결과는 JSON 출력. decision_log.md 갱신 필수.'   --permission-mode bypassPermissions > "$OUT" 2>&1
EXIT=$?

echo "[$(date -u +%FT%TZ)] daily-review END exit=$EXIT bytes=$(wc -c < "$OUT")" >> "$STATUS"

# Git commit + push
cd /home/hcpark/auto_trading
git add .claude/verification_logs/${RUN_ID}_daily_review*.md .claude/verification_logs/${RUN_ID}_daily_review_STATUS.txt 2>>"$STATUS"
git commit -m "cron(daily-review): $RUN_ID exit=$EXIT" >>"$STATUS" 2>&1 && git push origin master >>"$STATUS" 2>&1
echo "[$(date -u +%FT%TZ)] commit+push exit=$?" >> "$STATUS"
