#!/usr/bin/env bash
# 호가 수집 래퍼 — 5분마다 스냅샷 + 시간마다 집계.
#
# `bookTicker` 는 한 요청에 737종목을 주고 가중치가 5뿐이라 5분 간격이 싸다.
# 유동성 통과 190종만 저장한다(교훈 #78 — 거래도 못 할 종목의 호가는 쓸 데가 없다).
#
# ⚠ 순서: 집계 먼저, 정리 나중. 바뀌면 데이터가 사라진다.
set -u
cd "$(dirname "$0")/../.." || exit 1
source venv/bin/activate 2>/dev/null
export PYTHONPATH=.

MIN=$(date +%M)
python3 -m scripts.collect_orderbook --once >> /tmp/orderbook_collect.log 2>&1

# 정시마다 집계, 새벽 4시에 원자료 정리(집계 완료분만)
if [ "$MIN" = "00" ]; then
    python3 -m scripts.collect_orderbook --rollup >> /tmp/orderbook_collect.log 2>&1
    if [ "$(date +%H)" = "04" ]; then
        python3 -m scripts.collect_orderbook --prune 30 >> /tmp/orderbook_collect.log 2>&1
    fi
fi
