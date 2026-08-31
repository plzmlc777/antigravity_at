"""세션 이월 — **종목 수를 줄이면 어떻게 되나**. 배치 판단용.

## 왜 (2026-08-31)

세션 이월(아시아→미주)이 4년에서 샤프 0.77~1.04 로 나왔는데 t 가 1.6~2.0 이다.
샤프 0.9 면 t 2 에 5년이 필요한데 자료가 4년이라 **기질을 늘려 해결하려** 했다.
막혔다 — 1분봉이 2021년부터 있지만 **그때 종목이 34개뿐**이다(2022-08 이전
36개). 240종목 중 상위 3개(상위 1.25%)와 34종목 중 상위 3개(상위 9%)는 같은
전략이 아니다([[교훈#110]]).

그러면 남는 질문은 배치 쪽이다: **이 전략은 종목이 몇 개 필요한가.**

    80종목에서도 같은 크기면   유니버스 축소에 강건
    240에서만 나오면           상위 1% 를 뽑는 게 본질 — 유니버스를 지켜야 한다

⚠ 무작위 부분집합을 여러 번 뽑아 **평균과 흩어짐**을 본다. 한 번 뽑아 비교하면
  어느 종목이 뽑혔나에 좌우된다.
⚠ 칸은 고정이다 — 아시아→미주 · 추세스프레드3 · 미주 13-17. 여기서 다시
  뒤지지 않는다.

사용:
  python3 -m scripts.research.session_universe_scale --draws 20
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.session_combined import (Cfg, SESS_B,      # noqa: E402
                                               leg_daily, sess_returns)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "session_2026_08_31"
log = logging.getLogger("sessscale")
SIZES = [20, 40, 80, 160, 240]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--draws", type=int, default=20)
    p.add_argument("--seed", type=int, default=20260831)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg()
    t0 = time.time()
    RET, dates, syms = sess_returns(["runs/bars5m_oos", "runs/bars5m"], SESS_B, cfg)
    log.info("판 날짜 %d · 종목 %d · %.1f분", len(dates), len(syms),
             (time.time()-t0)/60)
    A = RET["아시아"].to_numpy(np.float32)
    U = RET["미주"].to_numpy(np.float32)
    rng = np.random.default_rng(a.seed)
    rows = []
    for n in SIZES:
        if n > len(syms):
            continue
        vals = []
        for k in range(a.draws if n < len(syms) else 1):
            j = (rng.choice(len(syms), n, replace=False) if n < len(syms)
                 else np.arange(len(syms)))
            # ⚠ min_alive 를 종목 수에 맞춰 낮춘다. 안 그러면 작은 부분집합이
            #   전부 "살아있는 종목 부족"으로 걸러져 **0 일이 남는다**.
            c2 = Cfg(min_alive=max(10, n//3))
            v = leg_daily(A[:, j], U[:, j], 3, "추세스프레드", c2)
            v = v[np.isfinite(v)]
            if len(v) < 200:
                continue
            m, sd = float(v.mean()), float(v.std(ddof=1))
            vals.append((m, m/(sd/np.sqrt(len(v))), m/sd*np.sqrt(365.25), len(v)))
        if not vals:
            continue
        V = np.asarray(vals)
        rows.append({"종목": n, "뽑기": len(V), "일평균": V[:, 0].mean(),
                     "일평균SD": V[:, 0].std(ddof=1) if len(V) > 1 else 0.0,
                     "날짜t": V[:, 1].mean(), "샤프": V[:, 2].mean(),
                     "양수뽑기%": 100.0*float((V[:, 0] > 0).mean()),
                     "날짜": int(V[:, 3].mean())})
        log.info("  종목 %3d → 일평균 %+.4f (±%.4f) · t %+.2f · 샤프 %.2f "
                 "· 양수뽑기 %.0f%% · %.1f분", n, V[:, 0].mean(),
                 V[:, 0].std(ddof=1) if len(V) > 1 else 0.0, V[:, 1].mean(),
                 V[:, 2].mean(), 100.0*float((V[:, 0] > 0).mean()),
                 (time.time()-t0)/60)
    T = pd.DataFrame(rows)
    print("\n■ 세션 이월 — 유니버스 크기별 (아시아→미주 · 추세스프레드3 · "
          f"미주 13-17 · 4년 · 뽑기 {a.draws}회)")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    if len(T) > 1:
        r = float(np.corrcoef(T.종목, T.일평균)[0, 1])
        print(f"\n  종목 수와 일평균의 상관 {r:+.3f}")
        print("  판정: " + ("종목이 많을수록 커진다 — **상위 1% 를 뽑는 것이 본질**"
                          if r > 0.5 else
                          "종목 수에 둔감 — 유니버스 축소에 강건" if abs(r) <= 0.5
                          else "종목이 적을수록 커진다 — 확인 필요"))
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "universe_scale.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
