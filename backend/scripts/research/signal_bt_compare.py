"""충격숏 · 방향숏 · 역확인숏 백테스트 비교 — **한 커널** (2026-09-09).

## 왜 이 형태인가

원장끼리 비교하면 체결 가정·구간·슬롯이 달라 못 쓴다. 같은 1분봉 패널 ·
같은 진입/손절/만기/수수료 커널에 태우고 **신호만** 바꾼다(하네스 규칙 ⑤).

⚠ 3슬롯 장부는 **경로 혼돈**이다(교훈#109). 진입 격자를 1분만 밀어도 이후
  거래 목록이 통째로 갈린다 — 위상 하나로는 못 믿는다. 0~4분으로 다섯 번
  돌려 **분포로** 본다.

⚠ **총손익이 판정 주축**이다. 빈도(거래 수)와 거래당을 같이 낸다 —
  거래당만 보면 결론이 뒤집힌다.

⚠ 14일이다. `imp_direction_grid` 의 최대통계량이 p 0.105 로 통과 못 했다.
  **순위 참고용이지 엣지의 근거가 아니다.**

사용:
    python3 -m scripts.research.signal_bt_compare --hold 240
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np

from scripts.research.imp_vs_kine import Cfg, run, tstat

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("sigbt")

CASES = [("충격숏  imp (기준)", "imp",     0.0),
         ("방향숏  dir",        "dir",     0.0),
         ("역확인  impanti>0",  "impanti", 0.0),
         ("확인숏  impconf<0",  "impconf", 0.0)]


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=240)
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--offsets", default="0,1,2,3,4")
    a = ap.parse_args()
    c = Cfg()
    OFF = [int(x) for x in a.offsets.split(",")]
    z = np.load(ROOT / c.panel, allow_pickle=True)
    M = {kk: z[kk] for kk in ("C", "H", "L", "IMP", "LIVE", "AGE")}
    M["grid"] = z["grid"]
    log.info("패널 %d분 × %d종목 · 보유 %d분 · 창 k=%d · 위상 %s · 슬롯 3 숏 "
             "· 손절 %.1f%% · 통행료 %.3f%%", *M["C"].shape, a.hold, a.k, OFF,
             c.stop_pct, c.fee_rt)

    print(f"\n■ 같은 커널 · 14일 · 슬롯3 숏 · 보유 {a.hold}분 · 손절 5% "
          f"— **신호만 다르다**\n")
    print(f"{'갈래':20s}{'위상별 일평균%':>32s}{'평균':>8}{'최저':>8}"
          f"{'최고':>8}{'t중앙':>7}{'거래':>7}{'거래당%':>9}")
    print("─" * 99)
    for name, sig, thr in CASES + [("무작위 대조군", "random", 0.0)]:
        ms, ts_, ns = [], [], []
        rng = np.random.default_rng(20260909)
        for o in OFF:
            MM = M
            if sig == "random":
                MM = dict(M)
                MM["IMP"] = rng.standard_normal(M["IMP"].shape).astype(np.float32)
            r, dy, n = run(MM, c, "imp" if sig == "random" else sig,
                           3, a.hold, False, a.k, None, o, thr)
            if len(r) < 5:
                continue
            ms.append(r.mean()); ts_.append(tstat(r)); ns.append(n)
        if not ms:
            print(f"{name:20s} 거래 부족")
            continue
        ndays = len(dy)
        per_tr = np.mean(ms) * 3 * ndays / max(np.mean(ns), 1)
        print(f"{name:20s}{' '.join(f'{x:+6.2f}' for x in ms):>32s}"
              f"{np.mean(ms):>+8.3f}{min(ms):>+8.3f}{max(ms):>+8.3f}"
              f"{np.median(ts_):>+7.2f}{np.mean(ns):>7.0f}{per_tr:>+9.3f}")
    print("\n※ 14일 5위상 = 사실상 관측 5개. t 는 유의하지 않다 — 순위 참고용.")
    print("※ 총손익이 판정 주축이다(빈도 × 거래당).")


if __name__ == "__main__":
    main()
