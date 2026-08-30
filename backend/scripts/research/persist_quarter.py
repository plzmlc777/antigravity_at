"""게이트 전략의 **분기별** 안정성 — 감쇠가 추세인가 잡음인가.

## 왜 (2026-08-31 03:00)

슬롯 실현이 위약을 뚫었다(슬롯10 p 0.010 · 슬롯20 p 0.007). 그런데

    슬롯10  전반 +0.405 → 후반 +0.256   (-37%)
    슬롯20  전반 +0.327 → 후반 +0.075   (-77%)

반토막이 추세면 지금(2026-08)은 이미 없다. 잡음이면 반절씩 잘라 본 우연이다.
분기로 쪼개면 갈린다.

그리고 **현실적 사이징**을 함께 낸다. 전액 투입 낙폭이 -60% 라 그대로는
못 쓴다. 자본의 몇 %를 넣어야 견딜 만한지 보여야 판단이 된다.

⚠ 분기는 8개뿐이다. 분기별 t 를 믿지 마라 — **부호와 크기의 흐름**만 본다.
⚠ 위약도 같은 분기로 잘라 나란히 놓는다. 안 그러면 아무 추세나 보인다.

사용:
  python3 -m scripts.research.persist_quarter --reps 200
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
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("pq")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H, DELAY = 12, 24, 1
K_GATE, LAG_GATE = 13, 2
FEE1 = 0.036
SIZES = (1.0, 0.5, 0.25, 0.10)     # 자본 대비 투입 비율


@dataclass(frozen=True)
class Cfg:
    min_bars_in_5: float = 3.0
    reps: int = 200
    seed: int = 20260831


def load(files):
    cl, nb = {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0), idx)


def funding_cum(syms, idx):
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
             "ORDER BY funding_time")
    a = idx.min().tz_convert(None); b = idx.max().tz_convert(None)
    cum = np.zeros((len(idx), len(syms)), np.float32)
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c.execute(q, {"s": s, "a": a, "b": b}).all()
            if not r:
                continue
            t = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r], np.float64) * 100.0
            pos = np.clip(idx.searchsorted(t, side="left"), 0, len(idx)-1)
            acc = np.zeros(len(idx)); np.add.at(acc, pos, v)
            cum[:, j] = np.cumsum(acc).astype(np.float32)
    return cum


def blocks(X, R, N, fee=FEE1):
    out = np.full(X.shape[0], np.nan)
    for i in range(X.shape[0]):
        x, r = X[i], R[i]
        m = np.isfinite(x) & np.isfinite(r)
        if m.sum() < 2*N + 10:
            continue
        ii = np.where(m)[0]
        o = ii[np.argsort(x[ii])]
        out[i] = float(r[o[-N:]].mean() - r[o[:N]].mean()) - 2*fee
    return out


def gated(v):
    prev = pd.Series(v).rolling(K_GATE).mean().shift(LAG_GATE).to_numpy()
    return np.isfinite(prev) & (prev > 0) & np.isfinite(v)


def eq(v, g, size):
    e, path = 1.0, []
    for i in range(len(v)):
        if g[i]:
            e *= (1.0 + size * v[i] / 100.0)
        path.append(e)
    p = np.asarray(path)
    return (e - 1.0)*100.0, float((p/np.maximum.accumulate(p) - 1.0).min()*100.0)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--slots", type=int, default=10)
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    N = a.slots
    fs = sorted(CACHE.glob("*.parquet"))
    t0 = time.time()
    CL, NB, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    X = np.where(live, -r, np.nan)
    kk, d = HOLD_H*12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - kk - d
    R[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
               - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
    anc = np.arange(SIG_BARS+12, n - kk - d - 1)
    anc = anc[anc % ANCH == 0]
    pos = np.arange(0, len(anc) - HOLD_H - 1, HOLD_H)
    XA, RA = X[anc][pos], R[anc][pos]
    ts = idx[anc[pos]]
    v = blocks(XA, RA, N)
    g = gated(v)
    log.info("슬롯 %d · 블록 %d · 거래 %d · %.1f분", N, len(v), int(g.sum()),
             (time.time()-t0)/60)

    print(f"\n■ 사이징 — 슬롯 {N} · 게이트 k{K_GATE} 여유{LAG_GATE} · 마찰 {2*FEE1}%")
    rr = []
    for s in SIZES:
        t_, dd = eq(v, g, s)
        ta, dda = eq(v, np.isfinite(v), s)
        rr.append({"투입비율": s, "게이트총손익": t_, "게이트낙폭": dd,
                   "항상총손익": ta, "항상낙폭": dda,
                   "손익/낙폭": t_/abs(dd) if dd else np.nan})
    print(pd.DataFrame(rr).to_string(index=False,
                                     float_format=lambda z: f"{z:+.2f}"))

    q = ts.to_period("Q").astype(str)
    D = pd.DataFrame({"q": q, "v": v, "g": g})
    obs = D[D.g].groupby("q").v.agg(["mean", "size", "sum"])
    rng = np.random.default_rng(cfg.seed)
    na = len(anc)
    mem = HOLD_H*2 + SIG_BARS
    PL = []
    for i in range(cfg.reps):
        sh = int(rng.integers(mem, na - mem))
        vv = blocks(XA, np.roll(RA, sh % len(pos), axis=0), N)
        gg = gated(vv)
        dd2 = pd.DataFrame({"q": q, "v": vv, "g": gg})
        PL.append(dd2[dd2.g].groupby("q").v.mean())
        if (i+1) % 50 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    P = pd.DataFrame(PL)
    obs["위약중앙"] = P.median().reindex(obs.index).to_numpy()
    obs["위약p05"] = P.quantile(.05).reindex(obs.index).to_numpy()
    obs["위약p95"] = P.quantile(.95).reindex(obs.index).to_numpy()
    obs["밖"] = np.where(obs["mean"] > obs["위약p95"], "↑",
                        np.where(obs["mean"] < obs["위약p05"], "↓", ""))
    print(f"\n■ 분기별 게이트 블록 평균(%) — 위약 {cfg.reps}계열 나란히")
    print(obs.to_string(float_format=lambda z: f"{z:+.4f}"))
    nout = int((obs["밖"] == "↑").sum())
    print(f"\n  분기 {len(obs)}개 중 위약 95분위 위: **{nout}개** "
          f"(우연이면 {0.05*len(obs):.1f}개)")
    m = obs["mean"].to_numpy()
    xq = np.arange(len(m))
    sl = np.polyfit(xq, m, 1)[0]
    psl = [np.polyfit(xq, P[c].reindex(obs.index).to_numpy(), 1)[0]
           for c in [0] if False]
    slnull = np.array([np.polyfit(xq, P.iloc[i].reindex(obs.index).to_numpy(), 1)[0]
                       for i in range(len(P))
                       if np.isfinite(P.iloc[i].reindex(obs.index).to_numpy()).all()])
    print(f"  분기 추세 기울기 {sl:+.4f}%p/분기 · 귀무 중앙 "
          f"{np.median(slnull):+.4f} · 5분위 {np.quantile(slnull,.05):+.4f} "
          f"· p(감쇠) {float((slnull <= sl).mean()):.3f}")
    OUT.mkdir(parents=True, exist_ok=True)
    obs.to_csv(OUT / f"persist_quarter_s{N}.csv")
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
