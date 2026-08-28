#!/usr/bin/env bash
# 위약 승률 운동학 — 전진 페이퍼 (System-2 시뮬레이션)
#
# 실계좌를 건드리지 않는다. 틱 파일에서 신호를 계산하고 봉 종가로 체결한다 —
# 연구 하네스와 **완전히 같은 경로**다. 경로가 갈리면 페이퍼가 연구를 검증하지
# 못한다.
#
# 규칙은 runs/research_track/tick_placebo_kinematics_frozen.md (개정 2) 에
# 동결돼 있다. 러너 안의 파라미터 블록을 고치면 전진 검정이 아니라 새 탐색이다.
#
# 상태는 runs/kinematics_paper/state.json 에 원자적으로 저장된다. PM2 재시작
# 한 번에 열린 포지션을 잃지 않는다.
#
# 원장: runs/kinematics_paper/trades.csv
set -uo pipefail
# ⚠ 이 파일은 리포 루트의 scripts/binance/ 에 있다 — 두 단계 올라가야
#   backend 가 나온다. 한 단계면 scripts/backend 를 찾아 죽는다.
cd "$(dirname "$0")/../../backend" || exit 1
[ -f venv/bin/activate ] || { echo "[kine] venv 없음"; exit 1; }
source venv/bin/activate
exec env PYTHONPATH=. nice -n 15 ionice -c3 \
  python3 -m scripts.binance.kinematics_paper
