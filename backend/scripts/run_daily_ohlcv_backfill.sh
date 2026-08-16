#!/usr/bin/env bash
# `ohlcv_daily` 꼬리 유지 — 매일 최근 10일을 아카이브에서 다시 받는다 (2026-08-16).
#
# 왜 생겼나
#     `ohlcv_daily` 는 1분봉 `ohlcv` 에서 유도하는데 **그 유도를 돌리는 크론이
#     없었다.** `build_ohlcv_daily --incremental` 은 `overnight_universe_chain.sh`
#     안에서 수동으로만 불렸다. 그래서 표가 조용히 말라갔다:
#
#         08-07  353종목 → 08-08  264 → 08-12  158 → **08-13~15  15**
#
#     남은 15종목은 정확히 신상저격수 세션 종목이었다 — 라이브 경로가 자기
#     종목 1분봉만 쌓고 있었던 것이다. 유니버스 분석과 3군 판정이 이 상태로
#     돌면 **경고 없이 종목 절반짜리 유니버스**로 판정한다.
#     (실측: 유동성 게이트 통과가 224종목인데 129종목으로 보였다.)
#
# 왜 1분봉 유도가 아니라 아카이브인가
#     1분봉 원장이 이미 뒤처져 있어 유도할 원재료가 없다. 아카이브 일봉은
#     무료·공개이고 하루치가 종목당 요청 하나다. 원장 복구와 독립적으로
#     읽기 모델을 최신으로 유지할 수 있다.
#
# ⚠ 아카이브는 **T+1** 이다 — 어제까지만 올라온다. 오늘 행은 이 잡이 못 채운다.
#   그래서 10일 창으로 매일 다시 받아 하루씩 따라 붙는다.
#
# ⚠ 완전한 1분봉 유도분은 덮지 않는다. **부분봉만** 아카이브 값으로 교체한다
#   (`ON CONFLICT ... WHERE is_partial = true`).
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1              # backend/
LOG_DIR="$(pwd)/runs/binance_paper/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_daily_ohlcv_backfill.log"

SINCE=$(date -u -d '10 days ago' +%Y-%m-%d)
echo "[daily-ohlcv] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) since=${SINCE}" \
  | tee -a "$LOG_FILE"

source venv/bin/activate
PYTHONPATH=. python3 -m scripts.backfill_ohlcv_daily_archive \
  --all --since "$SINCE" 2>&1 | tee -a "$LOG_FILE"
RC=${PIPESTATUS[0]}

# 꼬리 건강 점검 — 어제 날짜의 종목수가 무너져 있으면 크게 남긴다.
PYTHONPATH=. python3 - <<'PY' 2>&1 | tee -a "$LOG_FILE"
from datetime import date, timedelta
from sqlalchemy import text
from app.db.session import engine
d = date.today() - timedelta(days=1)
with engine.connect() as c:
    n = c.execute(text("SELECT count(*) FROM ohlcv_daily WHERE date = :d"),
                  {"d": d}).scalar() or 0
print(f"[daily-ohlcv] {d} 종목수 {n}")
if n < 200:
    print(f"[daily-ohlcv] ⚠⚠ 꼬리 결손 — {d} 가 {n}종목뿐이다. "
          f"유니버스 분석·3군 판정이 오염된다")
PY

echo "[daily-ohlcv] 완료 rc=${RC}" | tee -a "$LOG_FILE"
exit 0
