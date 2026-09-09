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
# 슬롯 수는 인자로 받는다. 슬롯마다 상태·원장이 runs/kinematics_paper/s{N}/ 로
# 분리되므로 여러 인스턴스가 서로 안 덮는다.
# ⚠ 앞의 위치 인자는 **최대 세 개**이고, `-` 로 시작하는 것이 나오면 거기서
#   멈춘다. 예전엔 무조건 `shift 3` 이라 위치 인자가 둘뿐인 갈래에 플래그를
#   붙이면 **플래그를 먹었다** — 2026-09-09 `10 both --stop-cooldown-min 120`
#   이 `--stop-cooldown-min` 을 DELAY 로 읽고 `120` 만 남겨 argparse 가 죽었다
#   (재시작 122회). 2026-08-31 에도 같은 자리에서 다섯 갈래가 801회 돌았다.
SLOTS="10"; SIDE="long"; DELAY="0"
_n=0
while [ "$#" -gt 0 ] && [ "$_n" -lt 3 ]; do
  case "$1" in -*) break ;; esac
  case "$_n" in
    0) SLOTS="$1" ;;
    1) SIDE="$1" ;;          # long | short | both
    2) DELAY="$1" ;;         # 진입 지연(분). 0 이면 기존 동작 그대로
  esac
  shift; _n=$((_n + 1))
done
EXTRA=""
[ "${SIDE}" = "short" ] && EXTRA="--short"
[ "${SIDE}" = "both" ]  && EXTRA="--both"
[ "${DELAY}" != "0" ]   && EXTRA="${EXTRA} --delay-min ${DELAY}"
# 4번째 인자부터는 그대로 넘긴다 — 변형 갈래용
#   예) 6 both 5 --pick noise --tag noise
#       10 both 5 --signal rev --hold-min 1440 --entry-hour 1 --tag utc01
# ⚠ `shift 3` 는 인자가 3개 미만이면 **아무것도 안 밀고 실패**한다.
#   `|| true` 가 그걸 삼켜 원래 인자가 "$@" 에 남고 파이썬에
# ⚠ 우선순위. 페이퍼·연구는 15(양보), **실거래는 0** 이어야 한다 —
#   실거래가 연구 8갈래와 같은 nice 로 돌면 봉 마감 직후 신호 계산이 밀린다.
#   PM2 앱에 KINE_NICE=0 을 주고 띄운다(교훈#102 체크리스트 9).
KINE_NICE="${KINE_NICE:-15}"
if [ "${KINE_NICE}" = "0" ]; then
  exec env PYTHONPATH=. \
    python3 -m scripts.binance.kinematics_paper --slots "${SLOTS}" ${EXTRA} "$@"
fi
exec env PYTHONPATH=. nice -n "${KINE_NICE}" ionice -c3 \
  python3 -m scripts.binance.kinematics_paper --slots "${SLOTS}" ${EXTRA} "$@"
