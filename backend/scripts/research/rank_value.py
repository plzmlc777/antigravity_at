"""z_vel 순위가 밴드 안에서 값을 더하나 — 2년/4년으로.

## 왜 (2026-08-31, 대표님 질문에서)

"필터 없이 어떻게 진입하나, 랜덤인가?" — 랜덤이 아니다. 밴드로 약 100종목을
남기고 **z_vel 낮은 순** 5종목을 잡는다. 틱 5일에서 그 순위가 무작위를
**20/20** 으로 이겼다(+0.0944%p, 단조: 극단 > 무작위 > 덜극단).

그런데 그 5일은 전략이 마침 양수였던 창이다. 2년 평균은 음수다.
**순위의 값어치가 음수 구간에서도 유지되나?** 그게 이 검정이다.

    A 가장 극단   z_vel 낮은 순 (현행)
    B 무작위      밴드 안에서 아무거나 (씨앗 20개)
    C 가장 덜 극단 z_vel 높은 순

⚠ 위상 24개 평균(교훈#111) · 진입 5분 지연 · 왕복 0.072% · 펀딩 포함
⚠ **연도별로도 쪼갠다** — 값어치가 창에 의존하는지 본다

사용:
  python3 -m scripts.research.rank_value --reps 20
  python3 -m scripts.research.rank_value --cache runs/bars5m_oos
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("rankv")

BAR = 5
WIN_H, WINDOW, DELTA = 12, 72, 36        # 60 · 360 · 180분
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
HOLD, DELAY, SLOT, FEE1 = 24, 1, 10, 0.036
MIN_BARS = 3.0


@dataclass(frozen=True)
class Cfg:
    seeds: int = 20
    seed0: int = 20260831


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"seeds": a.reps} if a.reps is not None else {}))
    t0 = time.time()
    cl, nb = {}, {}
    for f in sorted((ROOT/a.cache).glob("*.parquet")):
        d = pd.read_parquet(f, columns=["ts", "c", "n"])
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    CL = pd.DataFrame(cl).reindex(idx).ffill()
    NB = pd.DataFrame(nb).reindex(idx).fillna(0.0)
    syms, n = list(CL.columns), len(CL)
    log.info("판 %s봉 × %d종목 · %s ~ %s · %.1f분", f"{n:,}", len(syms),
             idx.min().date(), idx.max().date(), (time.time()-t0)/60)

    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time>=:a AND funding_time<:b "
             "ORDER BY funding_time")
    CUM = np.zeros((n, len(syms)), np.float32)
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c_.execute(q, {"s": s, "a": idx.min().tz_convert(None),
                               "b": idx.max().tz_convert(None)}).all()
            if not r:
                continue
            t_ = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r])*100.0
            pos = np.clip(idx.searchsorted(t_, side="left"), 0, n-1)
            acc_ = np.zeros(n); np.add.at(acc_, pos, v)
            CUM[:, j] = np.cumsum(acc_).astype(np.float32)

    C = CL.to_numpy(np.float32)
    fw = CL.shift(-WIN_H)/CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA); accd = vel - vel.shift(DELTA)
    pr = rate.clip(0.01, 0.99); se = np.sqrt(pr*(1-pr)/(WINDOW/WIN_H))
    ZV = (vel/(se*np.sqrt(2))).to_numpy(np.float32)
    ZA = (accd/(se*2.0)).to_numpy(np.float32)
    live = (NB.rolling(12).median().shift(1) >= MIN_BARS).to_numpy()
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - HOLD - DELAY
    R[:hi_] = ((C[DELAY+HOLD:DELAY+HOLD+hi_]/C[DELAY:DELAY+hi_]-1.0)*100.0
               - (CUM[DELAY+HOLD:DELAY+HOLD+hi_]-CUM[DELAY:DELAY+hi_]))
    warm = WIN_H + WINDOW + 2*DELTA
    base = np.arange(warm, n - HOLD - DELAY - 1)
    OKL = (ZV[base] >= Z_LO) & (ZV[base] <= Z_HI) & (ZA[base] < ACC_MAX) \
        & live[base] & np.isfinite(ZV[base])
    OKS = (ZV[base] >= -Z_HI) & (ZV[base] <= -Z_LO) & (ZA[base] > -ACC_MAX) \
        & live[base] & np.isfinite(ZV[base])
    zvb, Rb = ZV[base], R[base]
    yr = idx[base].year.to_numpy()
    half = SLOT // 2
    log.info("앵커 %s개 · 밴드 후보 롱 중앙 %d · 숏 중앙 %d · %.1f분",
             f"{len(base):,}", int(np.median(OKL.sum(1))),
             int(np.median(OKS.sum(1))), (time.time()-t0)/60)

    def pick(keyL, keyS, rows):
        """행마다 유효 후보 중 key 작은 순 half 개. 없으면 제외."""
        kL = np.where(OKL[rows], keyL[rows], np.inf)
        kS = np.where(OKS[rows], keyS[rows], np.inf)
        okr = (OKL[rows].sum(1) >= half) & (OKS[rows].sum(1) >= half)
        if not okr.any():
            return None
        r2 = rows[okr]
        L = np.argpartition(kL[okr], half-1, axis=1)[:, :half]
        S = np.argpartition(kS[okr], half-1, axis=1)[:, :half]
        return r2, L, S

    def run(mode, seed=0):
        rng = np.random.default_rng(seed)
        if mode == "무작위":
            kk = rng.random(zvb.shape).astype(np.float32)
            keyL = keyS = kk
        elif mode == "극단":
            keyL, keyS = zvb, -zvb
        else:
            keyL, keyS = -zvb, zvb
        per, peryr = [], {}
        for ph in range(HOLD):
            rows = np.arange(ph, len(base) - HOLD - 1, HOLD)
            got = pick(keyL, keyS, rows)
            if got is None:
                continue
            r2, L, S = got
            rr = Rb[r2]
            with np.errstate(invalid="ignore"):
                v = (np.nanmean(np.take_along_axis(rr, L, 1), 1)
                     - np.nanmean(np.take_along_axis(rr, S, 1), 1))
            m = np.isfinite(v)
            if m.sum():
                per.append(v[m].mean())
                for y in np.unique(yr[r2][m]):
                    peryr.setdefault(int(y), []).append(v[m][yr[r2][m] == y].mean())
        tot = float(np.mean(per)) - 2*FEE1 if per else np.nan
        byy = {y: float(np.mean(z)) - 2*FEE1 for y, z in peryr.items()}
        return tot, byy

    A, Ay = run("극단")
    Cc, Cy = run("덜극단")
    B, By = [], {}
    for s in range(cfg.seeds):
        b, by = run("무작위", cfg.seed0 + s)
        B.append(b)
        for y, v in by.items():
            By.setdefault(y, []).append(v)
    B = np.asarray(B)
    print(f"\n■ 선별 방식 비교 (위상 24 평균 · 슬롯{SLOT} 롱숏 · 보유{HOLD*BAR}분 "
          f"· 지연{DELAY*BAR}분 · 왕복 {2*FEE1}% · 펀딩 · 종목 {len(syms)})")
    print(f"  A 가장 극단 (현행)   {A:+.4f}%")
    print(f"  B 무작위 {cfg.seeds}회       중앙 {np.median(B):+.4f}% "
          f"· 5~95분위 [{np.quantile(B,.05):+.4f}, {np.quantile(B,.95):+.4f}]")
    print(f"  C 가장 덜 극단       {Cc:+.4f}%")
    print(f"\n  **A − B(중앙) = {A-np.median(B):+.4f}%p** "
          f"· A 가 무작위 {cfg.seeds}개 중 상위 {int((B < A).sum())}/{cfg.seeds}")
    print(f"  단조성 — 극단 {A:+.4f} · 무작위 {np.median(B):+.4f} · 덜극단 {Cc:+.4f} "
          f"→ {'단조' if A > np.median(B) > Cc else '**비단조**'}")

    print("\n■ 연도별 (값어치가 창에 의존하나)")
    ys = sorted(set(Ay) & set(Cy) & set(By))
    rows = [{"연도": y, "A 극단": Ay[y], "B 무작위중앙": float(np.median(By[y])),
             "C 덜극단": Cy[y], "A−B": Ay[y]-float(np.median(By[y])),
             "A승/20": int((np.asarray(By[y]) < Ay[y]).sum())} for y in ys]
    print(pd.DataFrame(rows).to_string(index=False,
                                       float_format=lambda z: f"{z:+.4f}"))
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if "oos" in a.cache else "is"
    (OUT / f"rank_value_{tag}.json").write_text(json.dumps(
        {"A": A, "B_median": float(np.median(B)), "C": Cc,
         "A_minus_B": A-float(np.median(B)),
         "A_beats": int((B < A).sum()), "seeds": cfg.seeds,
         "by_year": {str(y): {"A": Ay[y], "B": float(np.median(By[y])),
                              "C": Cy[y]} for y in ys}},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
