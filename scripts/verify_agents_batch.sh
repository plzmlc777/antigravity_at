#!/bin/bash
# 에이전트/스킬 순차 검증 배치 스크립트
# nohup으로 백그라운드 실행되며 로컬 SSH 단절에 영향 받지 않음
set +e  # 개별 실패해도 계속 진행

LOGDIR=/home/hcpark/auto_trading/.claude/verification_logs
mkdir -p "$LOGDIR"
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
STATUS_FILE="$LOGDIR/${RUN_ID}_STATUS.txt"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$STATUS_FILE"
}

log "=== Verification batch START (run_id=$RUN_ID) ==="
log "cwd=$(pwd) user=$(whoami) host=$(hostname)"

cd /home/hcpark/auto_trading

# --- 1/3: symbol-select ---
log "[1/3] symbol-select START"
OUT1="$LOGDIR/${RUN_ID}_1_symbol_select.md"
/usr/bin/claude -p 'at-symbol-select 스킬을 사용해서 한국 주식(키움) 대상 symbol-select 워크플로우를 실행해줘. 전략은 rsi_martingale, 현재 종목은 005930. FIND(후보 10개) → COMPARE(현재+후보 간략 비교) → SELECT(상위 3개 추천) 순서. 백엔드 API http://localhost:8001. 결과는 JSON 출력.'   --permission-mode bypassPermissions > "$OUT1" 2>&1
EXIT1=$?
log "[1/3] symbol-select END exit=$EXIT1 bytes=$(wc -c < "$OUT1")"

# --- 2/3: strategy-evolver ---
log "[2/3] strategy-evolver START"
OUT2="$LOGDIR/${RUN_ID}_2_strategy_evolver.md"
/usr/bin/claude -p 'strategy-evolver 에이전트를 실행해서 rsi_martingale 전략의 파라미터 변이(mutation)를 생성해줘. 베이스: symbol=261520, strategy=rsi_martingale, 기본 파라미터 사용. 변이 모드는 parameter. 3~5개 변이 후보를 생성하고 at-backtest 스킬로 간략 검증한 뒤 피트니스 순으로 랭킹. 백엔드 API http://localhost:8001. JSON 출력.'   --permission-mode bypassPermissions > "$OUT2" 2>&1
EXIT2=$?
log "[2/3] strategy-evolver END exit=$EXIT2 bytes=$(wc -c < "$OUT2")"

# --- 3/3: stock-searcher ---
log "[3/3] stock-searcher START"
OUT3="$LOGDIR/${RUN_ID}_3_stock_searcher.md"
/usr/bin/claude -p 'stock-searcher 에이전트를 호출해서 machine_mode=true로 오늘 한국 주식 시장에서 상승률 상위 10종목을 찾고, 각 종목에 대해 간략 투자 의견을 JSON으로 반환해줘. 데이터는 at-symbol-select/references 또는 백엔드 API http://localhost:8001 사용.'   --permission-mode bypassPermissions > "$OUT3" 2>&1
EXIT3=$?
log "[3/3] stock-searcher END exit=$EXIT3 bytes=$(wc -c < "$OUT3")"

# --- INDEX 생성 ---
INDEX="$LOGDIR/${RUN_ID}_INDEX.md"
cat > "$INDEX" << INDEXEOF
# Agent Verification Batch — $RUN_ID

Batch run of 3 agent/skill verifications on GCP server (35.202.214.187).

| # | Verification | Output | Exit | Size |
|---|---|---|---|---|
| 1 | symbol-select (at-symbol-select, Kiwoom) | ${RUN_ID}_1_symbol_select.md | $EXIT1 | $(wc -c < "$OUT1") bytes |
| 2 | strategy-evolver (rsi_martingale) | ${RUN_ID}_2_strategy_evolver.md | $EXIT2 | $(wc -c < "$OUT2") bytes |
| 3 | stock-searcher (top risers) | ${RUN_ID}_3_stock_searcher.md | $EXIT3 | $(wc -c < "$OUT3") bytes |

- Status log: ${RUN_ID}_STATUS.txt
- Run started: (see STATUS first line)
- Run completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)
INDEXEOF

log "INDEX written: $INDEX"

# --- Git commit + push ---
log "Git commit + push START"
cd /home/hcpark/auto_trading
git add .claude/verification_logs/${RUN_ID}_*.md .claude/verification_logs/${RUN_ID}_*.txt 2>&1 | tee -a "$STATUS_FILE"
git commit -m "verify(agents): batch run $RUN_ID on GCP

- 1/3 symbol-select exit=$EXIT1
- 2/3 strategy-evolver exit=$EXIT2
- 3/3 stock-searcher exit=$EXIT3
" 2>&1 | tee -a "$STATUS_FILE"
COMMIT_EXIT=$?
log "Git commit exit=$COMMIT_EXIT"

if [ $COMMIT_EXIT -eq 0 ]; then
  git push origin master 2>&1 | tee -a "$STATUS_FILE"
  log "Git push exit=$?"
fi

log "=== Verification batch DONE ==="
