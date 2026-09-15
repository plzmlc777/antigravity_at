# -*- coding: utf-8 -*-
"""라이브 신규 진입 문지기 — **전고점 대비 낙폭**으로 여닫는다.

2026-09-14 대표님 지시 이력:
  ① "엣지기울기가 플러스로 이동할 때까지 라이브 신규 진입을 막아줘"
  ② "페이퍼 모드 기울기가 플러스가 되는 시점에 라이브 신규 진입을 시작해줘"
  ③ "400 으로 시작해서 480 까지 벌다가 원금 밑까지 왔는데 이런 흐름을
     캐치 할 수 없냐"  → **①② 의 기울기 기준을 철회하고 낙폭 기준으로 교체**
  ④ "-10% 로 적용해줘"

왜 기울기를 버렸나 (실측, 2026-09-14):
  · 거래당 손익의 자기상관이 8갈래 평균 **+0.011** — 기억이 없다.
    그래서 "최근 N 개 평균 > 0" 관문은 차단율이 높을수록 손해였고
    (차단율 vs 개선 상관 **-0.831**), 갈래 하나를 빼면 부호가 뒤집혔다.
  · 기울기는 **"더 나빠지나"**를 재지 **"벌고 있나"**를 재지 않는다.
    계좌15 는 거래당 -1.456% 로 꾸준히 잃는데 기울기는 +0.0165 였다.
    꾸준히 잃으면 기울기는 평평하다 — 그래서 문지기가 계속 열어 뒀다.

왜 낙폭인가:
  · 낙폭은 **이미 일어난 일**이라 예측도 지속성도 필요 없다.
  · 알파 주장이 아니라 **손실 상한**이다. 일반화를 증명할 필요가 없다.
  · 실측 재생(계좌15 원장 117건): 문턱 -3%~-15% 어디든 실제보다 나았다.
    -10%/-3% 는 최종 423.70 (실제 376.16 대비 **+47.54**), 최대 낙폭
    -10.24% (실제 -21.78%).

⚠ 이력현상(hysteresis) — 정지 -10%, 재개 -3%. 문턱 하나로 하면 경계에서
  열렸다 닫혔다 떨린다.
⚠ 전고점은 **거래소 지갑** 기준이다(실제로 쓸 수 있는 돈). 재기동에 잃지
  않도록 파일에 남긴다 — 메모리에만 두면 재기동이 전고점을 오늘로 리셋해
  낙폭이 0 이 되고 관문이 통째로 풀린다(교훈#113).
⚠ 조회 실패는 0 이 아니다(교훈#106). 못 읽으면 **상태를 바꾸지 않는다**.
"""
import json
import logging
import pathlib
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = pathlib.Path("/home/mint/auto_trading/backend")
# ⚠ pm2 가 스크립트 경로로 띄우면 sys.path[0] 은 scripts/binance 다 —
#   `scripts.binance...` 를 못 찾는다. 백엔드 뿌리를 직접 넣는다.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LIVE = ROOT / "runs" / "kinematics_live"
PAPER = ROOT / "runs" / "kinematics_paper"
START = pd.Timestamp("2026-09-09 02:00", tz="UTC")

HALT_DD = -10.0          # 이 아래로 내려가면 정지
RESUME_DD = -3.0         # 참고용 표시값 — **자동 재개에는 쓰지 않는다**
# ⚠ **자동 재개 없음** (2026-09-14 14:06 대표님 지시)
#   "다음 재개 시작은 수동으로 진행했으면 해."
#   문지기는 **막기만** 한다. 푸는 것은 사람이다 — HALT_ENTRY 를 지우면 열린다.
#   오늘 하루에 기울기 관문·최근N 관문이 차례로 기각됐다. **자동으로 다시 켤
#   조건을 이 자료로는 세울 수 없다**는 것이 그 결론이다. 그래서 안 켠다.
#   재개 문턱을 회복하면 로그·보고로 **알리기만** 한다.
MANUAL_RESUME_ONLY = True
PERIOD_S = 60
HEARTBEAT_S = 600

# 라이브 원장 → (계좌번호, 이름, 참고용 페이퍼 쌍, 전고점 씨앗)
ACCTS = {
    # 계좌15 — 2026-09-15 09:12 규칙 교체: 충격240냉 → **방향숏3**
    #   교체 근거(지금 국면 실측): 48h 자본% +15.94% vs 현행 -10.55%,
    #   09-13 참사 구간에서 **유일하게 플러스**(+1.06%), 통행료 잠식 8%.
    #   ⚠ 전고점 씨앗을 교체 시점 지갑으로 다시 잡았다 — 낙폭 관문은
    #     **현행 규칙이 낸 손실**을 재는 장치다. 옛 규칙의 -21.57% 를
    #     물리면 새 규칙이 시작하자마자 정지한다.
    # 2026-09-15 15:2x 교체 — 방향숏3 → s6양다리. 보유 3건 강제청산 후 전환.
    #   전고점 씨앗은 **교체 시점 지갑**이다. 옛 -6.03% 를 물리면 안 된다.
    "s6b240":   (15, "계좌15 s6양다리", "s6both_h240", 360.58),
    # 계좌8 — 2026-09-15 09:20 규칙 교체: 충격숏3 → **역확인3**
    #   계좌15(방향숏3)와 반대 선별이라 같이 안 무너진다(상관 +0.084).
    #   ⚠ 전고점 씨앗을 교체 시점 지갑으로 다시 잡았다 — 옛 규칙의 -13.26%
    #     를 물리면 새 규칙이 시작하자마자 정지한다.
    "anti3s":   (8,  "계좌8 역확인3",   "s3short_anti", 367.14),
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("halt-gate")


def peak_path(d):
    return LIVE / d / "PEAK.json"


def load_peak(d, seed):
    p = peak_path(d)
    try:
        return float(json.loads(p.read_text())["peak"])
    except Exception:
        p.write_text(json.dumps({"peak": seed, "src": "seed"}), encoding="utf-8")
        return seed


def save_peak(d, v):
    peak_path(d).write_text(
        json.dumps({"peak": v, "at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8")


def paper_slope(tag):
    """참고용. **판정에 쓰지 않는다** — 2026-09-14 에 기준에서 내렸다."""
    p = PAPER / tag / "trades.csv"
    if not p.exists():
        return None, 0
    d = pd.read_csv(p)
    d["entry_ts"] = pd.to_datetime(d.entry_ts, utc=True, format="mixed")
    y = d[d.entry_ts >= START].sort_values("entry_ts").net_pct.to_numpy()
    if len(y) < 10:
        return None, len(y)
    return float(np.polyfit(np.arange(len(y), dtype=float), y, 1)[0]), len(y)


def main():
    from scripts.binance.kine_live_broker import KineLiveBroker
    log.info("문지기 시작 — **낙폭 기준** 정지 %.1f%% · 재개 **수동 전용**"
             " (참고 문턱 %.1f%%) · 주기 %d초",
             HALT_DD, RESUME_DD, PERIOD_S)
    brokers = {}
    for d, (aid, nm, _, _) in ACCTS.items():
        b = KineLiveBroker(account_id=aid, leverage=1)
        b.connect()
        brokers[d] = b
        log.info("  %s 연결 — 계좌 %d", nm, aid)
    last_beat = 0.0
    while True:
        beat = time.time() - last_beat >= HEARTBEAT_S
        for d, (aid, nm, tag, seed) in ACCTS.items():
            if not (LIVE / d).exists():
                continue
            halt_p = LIVE / d / "HALT_ENTRY"
            halted = halt_p.exists()
            try:
                w = brokers[d].wallet_balance()
            except Exception as exc:                       # noqa: BLE001
                log.error("%s 지갑 조회 예외 — 상태를 바꾸지 않는다: %s", nm, exc)
                continue
            if not w or w <= 0:
                log.error("%s 지갑 조회 실패 — 상태를 바꾸지 않는다", nm)
                continue
            peak = load_peak(d, seed)
            if w > peak:
                peak = w
                save_peak(d, peak)
                log.info("%s 전고점 갱신 %.2f", nm, peak)
            dd = 100.0 * (w / peak - 1.0)
            sl, n = paper_slope(tag)
            ref = ("페이퍼 %s 기울기 %+.4f(%d건·참고용)" % (tag, sl, n)
                   if sl is not None else "페이퍼 표본부족(참고용)")
            if not halted and dd <= HALT_DD:
                halt_p.write_text(
                    "%s 문지기 자동 정지 — 낙폭 %.2f%% (문턱 %.1f%%) · "
                    "지갑 %.2f / 전고점 %.2f · 재개 문턱 %.1f%%\n"
                    % (datetime.now(timezone.utc).astimezone()
                       .strftime("%Y-%m-%d %H:%M KST"),
                       dd, HALT_DD, w, peak, RESUME_DD), encoding="utf-8")
                log.warning("🛑 %s 신규 진입 **정지** — 낙폭 %.2f%% ≤ %.1f%% "
                            "(지갑 %.2f / 전고점 %.2f) | %s",
                            nm, dd, HALT_DD, w, peak, ref)
            elif halted and dd >= RESUME_DD and not MANUAL_RESUME_ONLY:
                halt_p.unlink()
                log.warning("🟢 %s 신규 진입 **재개** — 낙폭 %.2f%% ≥ %.1f%% "
                            "(지갑 %.2f / 전고점 %.2f) | %s",
                            nm, dd, RESUME_DD, w, peak, ref)
            elif halted and dd >= RESUME_DD:
                log.warning("🔔 %s 낙폭 %.2f%% — 참고 문턱 %.1f%% 를 회복했다. "
                            "**자동 재개하지 않는다(수동 전용)** — 사람이 "
                            "HALT_ENTRY 를 지워야 열린다 (지갑 %.2f / "
                            "전고점 %.2f) | %s",
                            nm, dd, RESUME_DD, w, peak, ref)
            elif beat:
                log.info("· %s %s — 낙폭 %.2f%% (지갑 %.2f / 전고점 %.2f · "
                         "정지 %.1f%% / 재개 %.1f%%) | %s",
                         nm, "정지" if halted else "열림", dd, w, peak,
                         HALT_DD, RESUME_DD, ref)
        if beat:
            last_beat = time.time()
        time.sleep(PERIOD_S)


if __name__ == "__main__":
    main()
