#!/usr/bin/env bash
# 실거래 유니버스 일일 갱신 — 거래소에서 죽은 종목을 걷어낸다.
#
# 왜 (2026-08-27)
#   틱 수집기가 377종목 중 360개만 받았다. 빠진 17개는 전부 거래소에서 죽은
#   것이었다(SETTLING 15 · 목록삭제 2). 수집기 결함이 아니라 **목록이 낡은 것**.
#   실거래도 같은 파일을 쓰고 있었다 — 신호가 나면 주문 단계에서 거부된다.
#
# 두 파일을 가른다
#   configs/rsi_paper_universe.txt  연구용 — **얼린다**. 과거 격자가 여기 묶여 있다
#   configs/rsi_live_universe.txt   실거래·수집용 — 매일 여기서 다시 만든다
#
# ⚠ 바뀌었을 때 무엇을 재시작하나
#   틱 수집기  → 자동. 포지션이 없으니 안전하고, 어차피 24시간마다 재연결한다
#   실거래     → **건드리지 않는다**. 보유 중일 수 있다. 소리내어 알리고 끝낸다.
#                죽은 종목은 시세가 실패해 걸러지므로 하루 미뤄도 주문은 안 나간다
#
# 일정: 매일 02:00 UTC (11:00 KST) — ohlcv-1m-daily(02:30) 앞
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1
LOG_DIR="$(pwd)/backend/runs/binance_paper/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/$(date -u +%Y%m%d_%H%M%S)_live_universe.log"

cd backend || exit 1
[ -f venv/bin/activate ] || { echo "[uni] venv 없음" | tee -a "${LOG_FILE}"; exit 1; }
source venv/bin/activate

# 2026-08-31 개정 — **두 파일**을 만든다.
#   rsi_live_universe.txt        실계좌(rsi-30m-LIVE 계좌8)가 읽는다.
#                                신규 편입 **안 함**(--no-add). 검증된 종목만.
#   binance_collect_universe.txt 틱 수집·페이퍼가 읽는다. 여문 신규를 편입한다.
# 왜: 세션 이월 실측에서 뽑힌 종목의 60.8%가 1년 미만이고, 젊은 종목이 적게
#     뽑힌 날은 일평균이 -0.097%로 부호가 뒤집혔다. 유니버스가 늙으면 죽는다.
#     그런데 실계좌 전략은 그 377종목에서 검증됐다 — 확대는 별도 결정 사안.
COLLECT="configs/binance_collect_universe.txt"
# ⚠ 재시작 판정은 **수집기가 실제로 읽는 파일**로 한다. 실계좌 파일을 보고
#   판정하면 수집 유니버스가 늘어도 재시작이 안 걸린다(2026-08-31 배선 개정).
C_BEFORE=$(sort "${COLLECT}" 2>/dev/null | md5sum | cut -d' ' -f1)
PYTHONPATH=. nice -n 10 python3 -m scripts.binance.build_live_universe \
  --out "${COLLECT}" --write 2>&1 | tee -a "${LOG_FILE}"
N_COLLECT=$(wc -l < "${COLLECT}" 2>/dev/null || echo 0)
echo "[uni] 수집 유니버스 ${N_COLLECT}종목" | tee -a "${LOG_FILE}"
C_AFTER=$(sort "${COLLECT}" | md5sum | cut -d' ' -f1)
if [ "${C_BEFORE}" != "${C_AFTER}" ]; then
  echo "[uni] 수집 유니버스 **변경** — 틱 수집기 재시작" | tee -a "${LOG_FILE}"
  pm2 restart tick-collector --update-env >/dev/null 2>&1 \
    && echo "[uni] 틱 수집기 재시작함" | tee -a "${LOG_FILE}" \
    || echo "[uni] ⚠ 틱 수집기 재시작 실패 — pm2 list 확인하라" | tee -a "${LOG_FILE}"
  # 세션 페이퍼 갈래도 같은 파일을 읽는다. 포지션은 state.json 에 남으므로 안전.
  pm2 restart kinematics-paper-sess240 kinematics-paper-sess480 \
      kinematics-paper-sess240n5 >/dev/null 2>&1 \
    && echo "[uni] 세션 페이퍼 3갈래 재시작함" | tee -a "${LOG_FILE}"
else
  echo "[uni] 수집 유니버스 변화 없음 — 재시작 안 함" | tee -a "${LOG_FILE}"
fi

OUT="configs/rsi_live_universe.txt"
BEFORE=$(sort "${OUT}" 2>/dev/null | md5sum | cut -d' ' -f1)
N_BEFORE=$(wc -l < "${OUT}" 2>/dev/null || echo 0)

echo "[uni] ts=$(date -u +%Y-%m-%dT%H:%M:%SZ) before=${N_BEFORE}종목" | tee -a "${LOG_FILE}"
PYTHONPATH=. nice -n 10 python3 -m scripts.binance.build_live_universe \
  --out "${OUT}" --no-add --write 2>&1 | tee -a "${LOG_FILE}"
EC="${PIPESTATUS[0]}"
if [ "${EC}" -ne 0 ]; then
  # ⚠ 실패하면 옛 파일이 그대로 남는다 — 조용히 빈 파일이 되는 것보다 낫다
  echo "[uni] 갱신 실패(exit ${EC}) — 옛 목록 ${N_BEFORE}종목 유지" | tee -a "${LOG_FILE}"
  exit "${EC}"
fi

AFTER=$(sort "${OUT}" | md5sum | cut -d' ' -f1)
N_AFTER=$(wc -l < "${OUT}")
if [ "${BEFORE}" = "${AFTER}" ]; then
  echo "[uni] 변화 없음 — ${N_AFTER}종목. 재시작 안 함" | tee -a "${LOG_FILE}"
  exit 0
fi

echo "[uni] **변경** ${N_BEFORE} → ${N_AFTER}종목" | tee -a "${LOG_FILE}"
# (수집기 재시작은 위 수집 유니버스 블록에서 한다 — 2026-08-31)

# 실거래는 자동 재시작하지 않는다. 다음 무포지션 구간에 사람이 올린다.
echo "[uni] ⚠ 실거래(rsi-30m-LIVE·shadow)는 아직 옛 ${N_BEFORE}종목으로 돈다." \
     "보유 0 일 때 재시작하라:" | tee -a "${LOG_FILE}"
echo "[uni]    pm2 restart rsi-30m-LIVE rsi-30m-shadow" | tee -a "${LOG_FILE}"
exit 0
