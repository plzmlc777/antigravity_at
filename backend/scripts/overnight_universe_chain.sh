#!/usr/bin/env bash
# 야간 연쇄 — 일봉 적재가 끝나면 스캔까지 자동으로 잇는다 (2026-08-14).
#
# 왜: 적재가 12~15시간이라 사람이 지켜볼 수 없다. 끝나는 시각을 모르니
#     "끝나면 다음"을 기계가 하게 한다. 아침에 결과가 준비돼 있어야 한다.
#
# 하는 일 (전부 읽기 전용 연구 작업 — 거래 경로에 손대지 않는다)
#   1) 진행 중인 일봉 적재가 끝날 때까지 대기
#   2) 증분 갱신 — 오늘치 부분봉을 다시 만든다
#   3) 전 종목 숏 규칙 스캔 (유동성 게이트 통과분)
#   4) 요약을 파일로 남기고 텔레그램 발송
#
# 사용: nohup bash scripts/overnight_universe_chain.sh > /tmp/chain.log 2>&1 &

set -u
cd "$(dirname "$0")/.." || exit 1
source venv/bin/activate 2>/dev/null
export PYTHONPATH=.:scripts

SUMMARY="/tmp/overnight_summary.txt"
MAXWAIT=$((16 * 3600))          # 16시간이면 뭔가 잘못된 것이다
START=$(date +%s)

log() { echo "[$(TZ='Asia/Seoul' date '+%m-%d %H:%M')] $*"; }

log "연쇄 시작 — 적재 완료 대기"
while pgrep -f 'build_ohlcv_daily --from-gate' > /dev/null; do
    if [ $(($(date +%s) - START)) -gt "$MAXWAIT" ]; then
        log "16시간 초과 — 대기 중단"
        break
    fi
    sleep 120
done
log "적재 프로세스 종료 확인"

# 2) 증분 — 오늘치는 계속 자라므로 다시 만든다
log "증분 갱신"
python3 -m scripts.build_ohlcv_daily --incremental >> /tmp/build_daily3.log 2>&1
log "증분 완료 (exit=$?)"

# 3) 스캔 — 표본 밖 분할은 필수 인자다
log "전 종목 숏 규칙 스캔"
python3 -W ignore -m scripts.research.short_universe_scan \
    --split 2026-02-01 --sl 0.2 --tp 0.3 --hold 30 \
    > /tmp/universe_scan.log 2>&1
SCAN_RC=$?
log "스캔 종료 (exit=${SCAN_RC})"

# 4) 요약
{
    echo "═══ 야간 연쇄 결과 $(TZ='Asia/Seoul' date '+%Y-%m-%d %H:%M KST') ═══"
    echo
    echo "── 일봉 테이블 ──"
    python3 - <<'PY' 2>/dev/null
from sqlalchemy import text
from app.db.session import engine
with engine.connect() as c:
    n, s, d0, d1, p = c.execute(text(
        "SELECT count(*), count(distinct symbol), min(date), max(date), "
        "count(*) FILTER (WHERE is_partial) FROM ohlcv_daily")).one()
    print(f"  {n:,}행 · 종목 {s} · {d0} ~ {d1} · 부분봉 {p:,}")
PY
    echo
    echo "── 스캔 (exit=${SCAN_RC}) ──"
    tail -24 /tmp/universe_scan.log
} > "$SUMMARY" 2>&1

log "요약 → ${SUMMARY}"
cat "$SUMMARY"

# 5) 텔레그램 — 실패해도 연쇄를 망치지 않는다
python3 - <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "scripts/binance")
try:
    from lifecycle_live_signal_driver import _telegram_notify
    body = open("/tmp/overnight_summary.txt").read()[:3500]
    _telegram_notify(8, f"🌙 <b>야간 연쇄 완료</b>\n<pre>{body}</pre>")
    print("텔레그램 발송")
except Exception as exc:
    print(f"텔레그램 실패(무시): {type(exc).__name__}: {exc}")
PY

log "연쇄 종료"
