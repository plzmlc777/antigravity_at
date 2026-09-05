#!/usr/bin/env bash
# 1분봉 갱신 — 3분마다. 틱을 **한 번만** 접어 두고 페이퍼 갈래들이 읽는다.
#
# 왜 (2026-09-01 · 민트 정지 사고)
#     갈래 14개가 각자 521종목의 틱을 5분마다 풀었다. 실측 2 CPU분/전량이니
#     14 × 2 / 5분 = **약 5.6코어**를 상시 태우고 있었다. 여기로 옮기면
#     3분마다 2 CPU분 = **0.67코어**다.
#
# ⚠ 겹쳐 돌면 같은 파일을 동시에 쓴다. flock 으로 막는다.
# ⚠ 이게 멈추면 갈래들이 틱으로 되돌아가 부하가 다시 오른다. 갈래 로그에
#   "1분봉이 없거나 낡아 틱에서 접는다" 경고가 뜨면 여기부터 보라.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1           # backend/

LOG="$(pwd)/runs/bars1m.log"
exec /usr/bin/flock -n /tmp/bars1m.lock -c "
  ./venv/bin/python3 -m scripts.binance.build_bars1m --days 1 --workers 2 \
    >> '$LOG' 2>&1
  tail -c 2000000 '$LOG' > '$LOG.t' && mv '$LOG.t' '$LOG'
"
