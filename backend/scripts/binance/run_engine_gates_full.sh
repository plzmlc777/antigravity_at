#!/usr/bin/env bash
# 실행기 전량 검사 (주 1회) — 파리티 게이트 154케이스 + 골든 전량.
# 매일 도는 사전 관문은 lifecycle 서브셋(67건)만 본다. 나머지는 여기서 잡는다.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
exec ./scripts/binance/run_engine_gates.sh --full
