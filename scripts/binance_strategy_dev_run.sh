#!/bin/bash
# Track B — Binance Futures 전략 자율 개발 러너 (LOCAL ONLY)
#
# 목적:
#   민트/신서버 도착 전(~2026-04-21)까지, 로컬 Binance OHLCV(약 2,700만 건)를 사용해
#   strategy-evolver 에이전트가 12%/월 잠재력 있는 Binance Futures 전략 후보를 자율 발굴.
#
# 결과물:
#   .claude/strategy_candidates/<timestamp>_<symbol>_<base>.md
#   각 후보는 walk-forward 검증 통과 + risk-manager 1차 승인 필요.
#
# 운영:
#   - 로컬 PC에서만 실행 (GCP는 US IP라서 Binance 차단)
#   - 사용자가 수동 실행하거나, 로컬 cron으로 야간 배치
#   - 개발-only: 실거래 배포 절대 금지 (신서버 도착 전까지)

set -e

# ── 위치 ─────────────────────────────────────────────────────────────────
ROOT=/home/hcpark/antigravity
cd "$ROOT"

# ── 입력 파라미터 ────────────────────────────────────────────────────────
# 사용: ./binance_strategy_dev_run.sh [SYMBOL] [BASE_STRATEGY] [MODE]
SYMBOL="${1:-BTCUSDT}"
BASE="${2:-dip_martingale}"
MODE="${3:-novel}"   # parameter | hybrid | novel

# ── 로그/출력 ────────────────────────────────────────────────────────────
RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
QUEUE_DIR="$ROOT/.claude/strategy_candidates"
mkdir -p "$QUEUE_DIR"
OUT="$QUEUE_DIR/${RUN_ID}_${SYMBOL}_${BASE}_${MODE}.md"
STATUS="$QUEUE_DIR/${RUN_ID}_${SYMBOL}_${BASE}_${MODE}_STATUS.txt"

echo "[$(date -u +%FT%TZ)] binance-strategy-dev START symbol=$SYMBOL base=$BASE mode=$MODE" > "$STATUS"

# ── 60일 이상 오래된 후보 정리 (디스크 보호) ────────────────────────────
find "$QUEUE_DIR" -name "*_STATUS.txt" -mtime +60 -delete 2>/dev/null || true
find "$QUEUE_DIR" -name "*.md" -mtime +60 -delete 2>/dev/null || true

# ── strategy-evolver 호출 ───────────────────────────────────────────────
# 핵심 제약:
#   1. Binance Futures (선물)
#   2. 레버리지 활용 가능 (1~10x)
#   3. Walk-Forward 검증 필수 (overfit_ratio ≤ 0.30)
#   4. 12%/월 환산 수익 목표
#   5. 결과는 후보 파일로 저장 (실거래 배포 금지)
/usr/bin/claude -p "strategy-evolver 에이전트로 Binance Futures 전략 후보를 자율 개발해줘.

타겟:
- 거래소: Binance Futures (USDT-M)
- 심볼: ${SYMBOL}
- 베이스 전략: ${BASE}
- 진화 모드: ${MODE}
- 최종 KPI: 월 12% 이상 수익률 (project_return_target.md)

엄격한 제약:
1. 로컬 DB의 Binance OHLCV만 사용 (.claude/skills/at-backtest/scripts/backtest.py 또는 backtest_native.py)
2. 레버리지 1~10x 활용 가능 (margin_type=ISOLATED 권장)
3. Walk-Forward 검증 필수: 최소 3분할, train/test = 70/30, overfit_ratio ≤ 0.30
4. 백테스트 기간: 최소 180일 이상
5. **절대 실거래 배포 금지** — 결과는 후보 파일로만 저장 (신서버 도착 전까지)
6. risk-manager 1차 평가 포함 (max drawdown, leverage exposure 체크)

워크플로우:
1. 베이스 전략 코드 읽기 (backend/app/strategies/${BASE}.py 또는 유사)
2. ${MODE} 모드로 변이 생성 (3~5개)
3. 각 변이를 Binance OHLCV로 백테스트
4. Walk-Forward 검증 (overfit_ratio 측정)
5. 통과한 변이만 후보로 채택
6. risk-manager 1차 평가 (승인/거부 + 사유)
7. 최종 결과를 markdown으로 출력 (수익률 표 + 파라미터 + 검증 결과 + 리스크 평가)

출력은 한국어 markdown. JSON은 마지막에 첨부." --permission-mode bypassPermissions > "$OUT" 2>&1
EXIT=$?

echo "[$(date -u +%FT%TZ)] binance-strategy-dev END exit=$EXIT bytes=$(wc -c < "$OUT")" >> "$STATUS"

if [ $EXIT -eq 0 ]; then
    echo "✅ 후보 저장: $OUT"
else
    echo "❌ 실패 (exit=$EXIT). 로그: $OUT"
fi
