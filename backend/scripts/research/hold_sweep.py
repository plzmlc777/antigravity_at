"""롱숏 밴드 — **보유 시간**을 쓸어본다. 통행료가 문제라면 여기가 손댈 곳이다.

## 왜 (2026-08-31, 비대칭 슬롯 격자 뒤)

표본밖 2022-2024 · 125종목 · 보유 120분에서 열한 칸을 재고 나온 그림:

    위약(무작위 시각)  -0.0646%   ≈ 왕복 수수료 0.072% 그 자체
    실측(z_vel 선별)   -0.0317%   위약 대비 **+0.0329%p** · 최대통계량 p 0.007

**신호에 정보는 있는데 통행료의 절반 크기다.** 슬롯 배분을 바꿔도 칸 열한 개의
폭이 0.037%p 라 0.072% 를 못 넘는다. 그러면 남은 손잡이는 **보유 시간**이다 —
엣지가 시간에 따라 쌓이면 고정된 왕복 수수료를 언젠가 넘는다.

그래서 재는 것은 순액이 아니라 **총(gross) 엣지의 시간 곡선**이다:

    gross(H) = 위상평균[ 롱평균 - 숏평균 ]        수수료 前
    net(H)   = gross(H) - 0.072%

⚠ 위상(교훈#111) — 보유 H 봉이면 비겹침 앵커의 위상이 H 가지다. 판정값은
  **위상 평균**. H 가 크면 위상마다 표본이 줄어 최대 24개만 고르게 뽑는다
  (편향 없는 부분추출 — 위상 하나를 고르면 그게 곧 시각 고정이다).
⚠ 펀딩 — 보유가 길수록 8h 정산이 여러 번 낀다. 종목별 `r - f` 로 한 번만
  정의하고 롱은 그대로, 숏은 부호를 뒤집는다(더하지 않는다).
⚠ 위약 이동은 신호 기억(창 72 + 델타 72 + 지평 12 = 156봉)과 보유를 넘겨야
  한다(교훈#108).

사용:
  python3 -m scripts.research.hold_sweep --reps 200
  python3 -m scripts.research.hold_sweep --cache runs/bars5m_oos --reps 200
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("hold")

BAR = 5
WIN_H, WINDOW, DELTA = 12, 72, 36
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
DELAY, FEE1, MIN_BARS, MIN_SIDE = 1, 0.036, 3.0, 12
MEMORY = WIN_H + WINDOW + 2*DELTA          # 신호 기억 156봉
HOLDS = [6, 12, 24, 48, 96, 192, 288]      # 30분 1h 2h 4h 8h 16h 24h
STRUCT = [(3, 3), (5, 5)]                  # 표본밖 최선 · 현행
MAX_PHASE = 24


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--reps", type=int, default=200)
    p.add_argument("--holds", default="",
                   help="예비비행용 — 쉼표로 봉 수 (예 24,48)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    holds = ([int(x) for x in a.holds.split(",") if x.strip()]
             if a.holds else HOLDS)
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
    live = (NB.rolling(12).median().shift(1) >= MIN_BARS).to_numpy()
    del NB, nb, cl
    fw = CL.shift(-WIN_H)/CL - 1.0
    win = (fw > 0).astype(np.float32).where(fw.notna()); del fw, CL
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H); del win
    vel = (rate - rate.shift(DELTA)).to_numpy(np.float32)
    accd = (vel - np.roll(vel, DELTA, axis=0)).astype(np.float32)
    accd[:DELTA] = np.nan
    pr = np.clip(rate.to_numpy(np.float32), 0.01, 0.99); del rate
    se = np.sqrt(pr*(1-pr)/(WINDOW/WIN_H), dtype=np.float32); del pr
    ZV = (vel/(se*np.float32(np.sqrt(2)))).astype(np.float32); del vel
    ZA = (accd/(se*np.float32(2.0))).astype(np.float32); del accd, se

    OKL_f = (ZV >= Z_LO) & (ZV <= Z_HI) & (ZA < ACC_MAX) & live & np.isfinite(ZV)
    OKS_f = (ZV >= -Z_HI) & (ZV <= -Z_LO) & (ZA > -ACC_MAX) & live & np.isfinite(ZV)
    log.info("신호 준비 · %.1f분", (time.time()-t0)/60)

    rng = np.random.default_rng(20260831)
    rows, nulls = [], {}
    for H in holds:
        hi_ = n - H - DELAY
        R = np.full(C.shape, np.nan, np.float32)
        R[:hi_] = ((C[DELAY+H:DELAY+H+hi_]/C[DELAY:DELAY+hi_]-1.0)*100.0
                   - (CUM[DELAY+H:DELAY+H+hi_]-CUM[DELAY:DELAY+hi_]))
        base = np.arange(MEMORY, n - H - DELAY - 1)
        zv, Ra = ZV[base], R[base]
        OKL, OKS = OKL_f[base], OKS_f[base]
        nb_ = len(base)
        # 위상 — H 가지 중 최대 24개를 고르게
        phases = (np.arange(H) if H <= MAX_PHASE
                  else np.unique(np.linspace(0, H-1, MAX_PHASE).astype(int)))
        for nl, ns in STRUCT:
            mk, ntr = [], 0
            for ph in phases:
                rows_ = np.arange(ph, nb_ - H - 1, H)
                kk, L, S = [], [], []
                for i in rows_:
                    li = np.where(OKL[i])[0]; si = np.where(OKS[i])[0]
                    if len(li) < max(nl, MIN_SIDE) or len(si) < max(ns, MIN_SIDE):
                        continue
                    kk.append(i)
                    L.append(li[np.argsort(zv[i][li])[:nl]])
                    S.append(si[np.argsort(-zv[i][si])[:ns]])
                if kk:
                    mk.append((np.asarray(kk), L, S)); ntr += len(kk)

            def stat(Rm, _mk=mk):
                per = []
                for kk, L, S in _mk:
                    v = []
                    for j, i in enumerate(kk):
                        x, y = Rm[i][L[j]], Rm[i][S[j]]
                        x, y = x[np.isfinite(x)], y[np.isfinite(y)]
                        if len(x) and len(y):
                            v.append(x.mean() - y.mean())
                    if v:
                        per.append(np.mean(v))
                return float(np.mean(per)) if per else np.nan

            g = stat(Ra)
            key = f"{nl}/{ns}"
            lo = max(MEMORY, H) + 10
            sh = rng.integers(lo, nb_ - lo, size=a.reps)
            nl_ = np.asarray([stat(np.roll(Ra, int(s), axis=0)) for s in sh])
            nl_ = nl_[np.isfinite(nl_)]
            rows.append({"보유분": H*BAR, "구조": key, "위상": len(mk),
                         "앵커": ntr, "총엣지": g, "위약중앙": float(np.median(nl_)),
                         "초과": g - float(np.median(nl_)),
                         "순액": g - 2*FEE1,
                         "p": float((nl_ >= g).mean())})
            nulls[f"{H}_{key}"] = [float(np.median(nl_)), float(np.quantile(nl_, .95))]
            log.info("  보유%4d분 · %s → 총 %+.4f · 위약 %+.4f · 초과 %+.4f · "
                     "순 %+.4f · p %.3f · %.1f분", H*BAR, key, g,
                     float(np.median(nl_)), g-float(np.median(nl_)),
                     g-2*FEE1, float((nl_ >= g).mean()), (time.time()-t0)/60)
        del R, Ra
    T = pd.DataFrame(rows)
    print(f"\n■ 보유 시간 곡선 — 종목 {len(syms)} · 지연 {DELAY*BAR}분 · "
          f"왕복 {2*FEE1}% · 펀딩 · 위상 평균")
    print(T.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    pos = T[T["순액"] > 0]
    print("\n  순액 양수 칸: " + ("없음" if pos.empty else
          ", ".join(f"{int(r.보유분)}분 {r.구조} {r.순액:+.4f}%"
                    for r in pos.itertuples())))
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if "oos" in a.cache else "is"
    T.to_csv(OUT / f"hold_sweep_{tag}.csv", index=False)
    (OUT / f"hold_sweep_{tag}.null.json").write_text(
        json.dumps(nulls, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
