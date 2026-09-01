"""세션 이월 — **240종목 기질 대 521종목 기질**. 나이 가설의 독립 검정.

## 왜 (2026-09-01)

어제 확인한 것: 세션 이월 전략이 뽑는 종목의 중앙 나이는 0.95년(유니버스 1.49년)
이고, **젊은 종목이 많이 뽑힌 날 +0.270% · 적게 뽑힌 날 -0.097%** 로 부호가
갈렸다(t 2.22).

오늘 유니버스에 신규 상장 162종목을 편입했다. 그중 114종목이 상장 90일~1년이라
**확장 기질에서는 뽑히는 종목이 통째로 젊어진다**.

    나이 가설이 맞다면   확장 기질에서 성과가 **올라가야** 한다
    안 올라가면          그 관계는 허상이었다

어제 발견을 오늘 자료로 검정하는 셈이라 **독립 검정**이다. 다만 완전히
독립은 아니다 — 같은 4년 구간이고 240종목은 양쪽에 다 들어 있다.

## 규약

⚠ 칸은 고정 — 아시아→미주 · 추세스프레드 · 미주 13-17 UTC. 다시 안 뒤진다.
⚠ 종목 수가 다르면 상위 N 의 **백분위**가 달라진다(교훈#110, 2026-08-31 실측:
  80종목에서 3개는 3.75%, 240종목에서 3개는 1.25% — 다른 전략이다).
  그래서 **고정 개수와 백분위 둘 다** 잰다.
⚠ 판정 주축은 **날짜 군집 t**(교훈#112).
⚠ 확장 기질은 신규 종목이 상장일부터라 **앞 구간은 종목이 적다**. 연도별
  종목 수를 같이 찍는다 — 안 찍으면 "구간 효과"로 오독한다.

사용:
  python3 -m scripts.research.session_ext_compare
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
log = logging.getLogger("sessext")


def run(caches, label, cfg, picks, pcts, window=None):
    """window=(a,b) 로 **날짜 창을 같게** 맞춘다.

    ⚠ 확장 캐시는 상장일부터라 2020년까지 거슬러 올라간다. 창을 안 맞추면
      기질 비교가 아니라 **기간 비교**가 된다(2026-09-01: 1489일 대 2429일).
    """
    RET, dates, syms = sess_returns(caches, SESS_B, cfg)
    di = pd.DatetimeIndex(dates)
    if window is not None:
        m = (di >= pd.Timestamp(window[0], tz="UTC")) & \
            (di <= pd.Timestamp(window[1], tz="UTC"))
        di = di[m]
        RET = {k: v.loc[m] for k, v in RET.items()}
    # ⚠ 펀딩을 반드시 뺀다. 안 빼면 어제 판정(+0.1161)과 수준이 안 맞고,
    #   **신규 상장은 펀딩이 극단적**이라 확장 기질에 다르게 작용한다.
    from sqlalchemy import text
    from app.db.session import engine
    FUND = pd.DataFrame(0.0, index=di, columns=syms)
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='300s'"))
        rr = c_.execute(text(
            "SELECT symbol, funding_time, funding_rate FROM binance_funding_rate "
            "WHERE funding_time>=:a AND funding_time<:b"),
            {"a": di.min().tz_convert(None), "b": di.max().tz_convert(None)}).all()
    cs, nf = set(syms), 0
    a_, b_ = SESS_B["미주"]
    for sym, t_, v in rr:
        if sym not in cs:
            continue
        ts = pd.Timestamp(t_, tz="UTC")
        if not (a_ <= ts.hour < b_):
            continue
        d0 = ts.normalize()
        if d0 in FUND.index:
            FUND.at[d0, sym] += float(v)*100.0
            nf += 1
    log.info("[%s] 펀딩 %s건 반영", label, f"{nf:,}")
    A = RET["아시아"].to_numpy(np.float32)
    U = (RET["미주"] - FUND).to_numpy(np.float32)
    alive = np.isfinite(A) & np.isfinite(U)
    yr = pd.Series(alive.sum(1), index=di).groupby(di.year).median()
    log.info("[%s] 날짜 %d · 종목 %d · 연도별 유효종목 중앙 %s", label,
             len(dates), len(syms), {int(k): int(v) for k, v in yr.items()})
    rows = []
    for N in picks:
        for pct in pcts:
            v = leg_daily(A, U, N, "추세스프레드", cfg, pct=pct)
            v = v[np.isfinite(v)]
            if len(v) < 200:
                continue
            m, sd = float(v.mean()), float(v.std(ddof=1))
            rows.append({"기질": label, "종목수": len(syms),
                         "선별": "백분위" if pct else "고정", "N": N,
                         "날짜": len(v), "일평균": m,
                         "일중앙": float(np.median(v)),
                         "날짜t": m/(sd/np.sqrt(len(v))),
                         "샤프": m/sd*np.sqrt(365.25),
                         "양수일%": float(100*(v > 0).mean()),
                         "연환산%": m*365.25})
            log.info("  %s %s N=%d → %+.4f · t %+.2f · 샤프 %.2f", label,
                     "백분위" if pct else "고정", N, m,
                     m/(sd/np.sqrt(len(v))), m/sd*np.sqrt(365.25))
    return rows, yr


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--picks", default="3,5")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg()
    picks = [int(x) for x in a.picks.split(",")]
    t0 = time.time()
    rows = []
    W = ("2022-08-01", "2026-08-28")      # 기본 캐시가 덮는 구간
    r1, y1 = run(["runs/bars5m_oos", "runs/bars5m"], "기본 240", cfg,
                 picks, (False, True), W)
    rows += r1
    r2, y2 = run(["runs/bars5m_oos", "runs/bars5m_ext"], "확장 521", cfg,
                 picks, (False, True), W)
    rows += r2
    T = pd.DataFrame(rows)
    print("\n■ 세션 이월 — 기질 확장 전후 (아시아→미주 · 추세스프레드 · "
          "미주 13-17 · 날짜 t)")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    print("\n■ 연도별 유효 종목 수 (구간 효과와 종목 효과를 가르려면 필요하다)")
    print(pd.DataFrame({"기본 240": y1, "확장 521": y2}).to_string())
    print("\n■ 같은 칸끼리 차이 (확장 − 기본)")
    for pct in ("고정", "백분위"):
        for N in picks:
            a_ = T[(T.기질 == "기본 240") & (T.선별 == pct) & (T.N == N)]
            b_ = T[(T.기질 == "확장 521") & (T.선별 == pct) & (T.N == N)]
            if len(a_) and len(b_):
                d = float(b_.일평균.iloc[0]) - float(a_.일평균.iloc[0])
                print(f"  {pct} N={N}:  {float(a_.일평균.iloc[0]):+.4f} → "
                      f"{float(b_.일평균.iloc[0]):+.4f}  ({d:+.4f}%p) · "
                      f"t {float(a_.날짜t.iloc[0]):+.2f} → "
                      f"{float(b_.날짜t.iloc[0]):+.2f}")
    print("\n  판정 기준(사전 선언): 확장에서 **올라가면** 나이 가설 지지, "
          "떨어지면 어제 관계는 허상")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "ext_compare.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
