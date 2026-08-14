#!/usr/bin/env bash
# 정본(Canon) 사전 관문 — 주문을 내기 전에 사본이 정본을 따르는지 확인한다.
#
# 왜 (정본 엔진 계획 5단계)
#   골든·파리티 검사는 만들어 놓고 아무도 부르지 않으면 없는 것과 같다.
#   실제로 `engine_parity_gate.py` 는 작성된 뒤 3개월간 호출처가 0개였고,
#   그 사이 2026-08-08 사고(같은 policy, 다른 실행기, 다른 전략)가 났다.
#   사람이 기억해서 돌리는 검사는 결국 안 돌아간다.
#
# 무엇을 검사하나 (빠른 것만 — 매일 주문 앞을 막아야 하므로)
#   1) 커널·브래킷·수수료 단위 테스트          약 45초
#   2) 골든 재생 (lifecycle 서브셋 67건)        약 30초
#   lifecycle 만 보는 이유: **실자금이 걸린 유일한 경로**다. 전량 검사(154케이스
#   파리티 45분 + 골든 전량 30분)는 주간 잡으로 따로 돈다.
#
# 실패하면
#   종료코드 1. 호출부(run_binance_paper_cycle.sh)가 **주문 단계를 건너뛴다.**
#   검사에 실패한 엔진으로 실자금을 굴리는 것보다 하루 쉬는 편이 낫다.
#
# 사용:
#   ./scripts/binance/run_engine_gates.sh          # 빠른 관문 (기본)
#   ./scripts/binance/run_engine_gates.sh --full   # 전량 (파리티 + 골든 전체)
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 2
PY=./venv/bin/python3
MODE="${1:-fast}"
# 거래 사이클 중인가 — 실패 시 주문이 **실제로** 막히는 상황인지 구분한다.
# 수동 실행은 막을 주문이 없으므로 orders_blocked 로 세면 안 된다.
CONTEXT="${2:-manual}"
FAILED=0
SUMMARY=""

note() { echo "[engine-gate] $*"; }
fail() { FAILED=1; SUMMARY="${SUMMARY}\n  ✗ $*"; note "실패: $*"; }
pass() { SUMMARY="${SUMMARY}\n  ✓ $*"; note "통과: $*"; }

note "=== 정본 관문 시작 (mode=${MODE}) ==="

# ── 1) 단위 테스트 ────────────────────────────────────────────────────
if $PY -m unittest discover -s tests/composer_framework -p 'test_*.py' > /tmp/engine_gate_unit.log 2>&1; then
  UNIT_TOTAL="$(grep -oE 'Ran [0-9]+ tests' /tmp/engine_gate_unit.log | grep -oE '[0-9]+' | head -1)"
  UNIT_PASSED="${UNIT_TOTAL}"
  pass "단위 테스트 (Ran ${UNIT_TOTAL} tests)"
else
  UNIT_TOTAL="$(grep -oE 'Ran [0-9]+ tests' /tmp/engine_gate_unit.log | grep -oE '[0-9]+' | head -1)"
  UNIT_FAILS="$(grep -oE 'failures=[0-9]+' /tmp/engine_gate_unit.log | grep -oE '[0-9]+' | head -1)"
  UNIT_PASSED="$(( ${UNIT_TOTAL:-0} - ${UNIT_FAILS:-0} ))"
  fail "단위 테스트 — $(grep -E '^(FAILED|ERROR)' /tmp/engine_gate_unit.log | tail -1)"
fi

# ── 2) 골든 재생 ──────────────────────────────────────────────────────
if [ "$MODE" = "--full" ]; then
  GOLDEN_ARGS=""
  GOLDEN_LABEL="골든 재생 (전량)"
else
  GOLDEN_ARGS="--filter lifecycle"
  GOLDEN_LABEL="골든 재생 (lifecycle 서브셋)"
fi
# shellcheck disable=SC2086
if $PY -m scripts.research.golden_replay --verify $GOLDEN_ARGS > /tmp/engine_gate_golden.log 2>&1; then
  pass "${GOLDEN_LABEL} — $(grep -oE '일치 [0-9]+ / 불일치 [0-9]+ / 재생불가 [0-9]+' /tmp/engine_gate_golden.log | tail -1)"
else
  fail "${GOLDEN_LABEL} — $(grep -oE '일치 [0-9]+ / 불일치 [0-9]+ / 재생불가 [0-9]+' /tmp/engine_gate_golden.log | tail -1)"
fi
# ⚠ '일치' 로 grep 하면 '불일치' 도 걸린다(부분문자열). 숫자를 **위치로** 읽는다:
#   "일치 67 / 불일치 0 / 재생불가 0" → 67, 0, 0
GOLD_NUMS="$(grep -oE '일치 [0-9]+ / 불일치 [0-9]+ / 재생불가 [0-9]+' /tmp/engine_gate_golden.log \
             | tail -1 | grep -oE '[0-9]+')"
GOLD_M="$(echo "$GOLD_NUMS" | sed -n 1p)"
GOLD_X="$(echo "$GOLD_NUMS" | sed -n 2p)"

# ── 3) 파리티 게이트 (전량 모드에서만 — 45분 걸린다) ──────────────────
if [ "$MODE" = "--full" ]; then
  if $PY -m scripts.research.engine_parity_gate --all-sessions \
       --out "runs/engine_parity/gate_$(date +%Y%m%d).json" > /tmp/engine_gate_parity.log 2>&1; then
    pass "파리티 게이트 — $(grep -oE '결과: PASS [0-9]+ / FAIL [0-9]+ / SKIP [0-9]+' /tmp/engine_gate_parity.log | tail -1)"
  else
    fail "파리티 게이트 — $(grep -oE '결과: PASS [0-9]+ / FAIL [0-9]+ / SKIP [0-9]+' /tmp/engine_gate_parity.log | tail -1)"
  fi
  PAR_LINE="$(grep -oE 'PASS [0-9]+ / FAIL [0-9]+ / SKIP [0-9]+' /tmp/engine_gate_parity.log | tail -1)"
  PARITY_ARG="--parity $(echo "$PAR_LINE" | grep -oE '[0-9]+' | paste -sd/ -)"
fi

echo -e "[engine-gate] === 요약 ===${SUMMARY}"

# ── DB 기록 ───────────────────────────────────────────────────────────
# ⚠ 기록 실패가 **관문 판정을 바꾸면 안 된다.** 관문은 주문 앞에 선다.
#   `|| true` 로 부르고, 기록 스크립트도 예외를 삼켜 항상 0 으로 끝난다.
if [ "$FAILED" -eq 0 ]; then VERDICT=pass; else VERDICT=fail; fi
$PY -m scripts.record_gate_run \
    --mode "$([ "$MODE" = "--full" ] && echo full || echo fast)" \
    --verdict "$VERDICT" \
    --unit "${UNIT_PASSED:-}/${UNIT_TOTAL:-}" \
    --golden "${GOLD_M:-}/${GOLD_X:-}" \
    ${PARITY_ARG:-} \
    --context "$CONTEXT" 2>&1 | tail -1 || true

if [ "$FAILED" -ne 0 ]; then
  note "**정본 이탈(non-canonical drift) — 주문 단계를 건너뛴다**"
  # 텔레그램 경보 (실패했을 때만. 조용히 넘어가면 관문이 없는 것과 같다)
  $PY - <<'PYEOF' || true
# 텔레그램 경보 — 토큰은 **DB(exchange_accounts, Fernet)** 에 있다. .env 가 아니다.
# lifecycle_live_signal_driver._telegram_notify 와 같은 경로·같은 수신 그룹을 쓴다.
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "scripts/binance")
REAL_ACCOUNT_ID = 8          # run_binance_paper_cycle.sh 의 --real-account-id 와 같은 값
try:
    from lifecycle_live_signal_driver import _telegram_notify
except Exception as exc:
    print(f"[engine-gate] 텔레그램 모듈 로드 실패: {exc}")
    raise SystemExit(0)
try:
    body = open("/tmp/engine_gate_golden.log").read()[-500:]
except Exception:
    body = "(로그 없음)"
msg = ("\u26d4 <b>정본 이탈 — 오늘 주문을 건너뜁니다</b>\n\n"
       "사본이 정본(Canon)에서 벗어났습니다. 커널·정책 변경을 확인하세요.\n"
       "<pre>" + body.replace("&", "&amp;").replace("<", "&lt;") + "</pre>")
try:
    _telegram_notify(REAL_ACCOUNT_ID, msg)
    print("[engine-gate] 텔레그램 경보 요청 완료")
except Exception as exc:
    print(f"[engine-gate] 텔레그램 경보 실패: {exc}")
PYEOF
  exit 1
fi

note "=== 정본 관문 통과 ==="
exit 0
