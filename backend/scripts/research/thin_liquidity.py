"""**유동성 얇음** — 가설이 형성된 뒤의 단일 방향 검정.

## 어떻게 여기 왔나 (2026-08-31)

틱 미시구조 6종 × 5분위 = 30칸에서 **25칸이 음수**였고 p 0.160 이었다.
그런데 두 특징이 **같은 모양**이었다:

    튐강도        Q1 -0.032 → Q3 -0.121 → **Q5 +0.066**
    체결간격변동   Q1 -0.022 → Q3 -0.113 → **Q5 +0.182**

둘 다 U자이고 Q5 에서만 양수다. 그리고 둘은 같은 것을 잰다 —
**유동성이 얇고 체결이 산발적인 종목**이다.

기제: 얇은 종목은 소량 매도에도 크게 밀리고, 그 밀림에 정보가 없으니 돌아온다.

## 그래서 여기선 **뒤지지 않는다**

가설이 형성됐으므로 방향을 **사전지정**한다 — 얇을수록 좋다. 두 지표를
앵커 내 순위로 합쳐 하나로 만들고, 꼬리 세 폭만 본다.

    점수 = 튐강도 순위 + 체결간격변동 순위 (앵커 내 횡단면, 클수록 얇다)
    상위 20% · 10% · 5% (얇은 쪽)  = **3칸**

⚠ 3칸도 격자다. 위약이 3칸을 전부 뒤진다.
⚠ 방향이 사전지정이므로 **한쪽 검정**이다.
⚠ 얇으면 마찰이 커진다 — 이건 gross 측정이고, 통과하면 실행 가능성은
  **별도 문제**다. 그때 다시 재야 한다.

사용:
  python3 -m scripts.research.thin_liquidity --reps 1000
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
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("thin")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
HOLD, ANCH, DELAY, LOOK = 120, 5, 5, 60
FEE2, MIN_LIVE = 0.072, 5.0
# ⚠ 비율(5%)과 최소값(3개)이 충돌했다 — 5% 가 사실상 "3개"였다.
#   **고정 종목 수**로 바꿔 상호작용을 없앤다.
NPICK = (3, 5, 10)
# ⚠ 얇은 종목은 **호가 튐이 가장 심한 곳**이다. 지연을 함께 잰다 —
#   5분에 죽으면 튐이고 남으면 진짜다. 판정은 지연 1봉(5분)으로만 한다.
DELAYS = (1, 3, 6, 12)          # 5 · 15 · 30 · 60분
JUDGE_DELAY = 1


@dataclass(frozen=True)
class Cfg:
    min_ticks: int = 2_000
    min_cand: int = 20
    min_pick: int = 3
    reps: int = 1_000
    seed: int = 20260831


def per_minute(x):
    x = x.sort_values("ts_ms")
    p = x.price.to_numpy(np.float64)
    m = (x.ts_ms // 60_000).to_numpy()
    d = np.diff(p, prepend=p[0])
    sg = np.sign(d)
    prev = pd.Series(np.where(sg == 0, np.nan, sg)).ffill().to_numpy()
    flip = (sg != 0) & (np.roll(prev, 1) != 0) & (sg != np.roll(prev, 1))
    dt = np.diff(x.ts_ms.to_numpy(), prepend=x.ts_ms.iloc[0]).astype(float)
    g = pd.DataFrame({"m": m, "p": p, "fl": flip.astype(float), "dt": dt}).groupby("m")
    o = pd.DataFrame({"cl": g.p.last(), "n": g.p.size(), "flip": g.fl.sum(),
                      "dtm": g.dt.mean(), "dts": g.dt.std()})
    o.index = pd.to_datetime(o.index*60_000, unit="ms", utc=True)
    return o


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    t0 = time.time()
    uni = [s.strip().upper() for s in (ROOT/a.universe).read_text().split()
           if s.strip()]
    cols = {}
    for s in uni:
        d = TICKS/s
        if not d.is_dir():
            continue
        fs = sorted(d.glob("*.parquet"))
        if not fs:
            continue
        try:
            x = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        except Exception:                                      # noqa: BLE001
            continue
        x = x[(x.price > 0) & (x.qty > 0)]
        if len(x) < cfg.min_ticks:
            continue
        cols[s] = per_minute(x)
    syms = sorted(cols)
    idx = pd.date_range(min(v.index.min() for v in cols.values()),
                        max(v.index.max() for v in cols.values()),
                        freq="1min", tz="UTC")
    CL = pd.DataFrame({s: cols[s]["cl"] for s in syms}).reindex(idx).ffill()
    N = pd.DataFrame({s: cols[s]["n"] for s in syms}).reindex(idx).fillna(0.0)
    FL = pd.DataFrame({s: cols[s]["flip"] for s in syms}).reindex(idx).fillna(0.0)
    DM = pd.DataFrame({s: cols[s]["dtm"] for s in syms}).reindex(idx)
    DS = pd.DataFrame({s: cols[s]["dts"] for s in syms}).reindex(idx)
    del cols
    n = len(CL)
    log.info("틱 → 분당 %s분 × %d종목 · %.1f분", f"{n:,}", len(syms),
             (time.time()-t0)/60)

    bump = (FL.rolling(LOOK).sum()/(N.rolling(LOOK).sum()+1e-9)).shift(1).to_numpy(np.float32)
    irr = (DS.rolling(LOOK).mean()/(DM.rolling(LOOK).mean()+1e-9)).shift(1).to_numpy(np.float32)
    fw = CL.shift(-WIN_H)/CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA); accd = vel - vel.shift(DELTA)
    pr = rate.clip(0.01, 0.99); se = np.sqrt(pr*(1-pr)/(WINDOW/WIN_H))
    ZV = (vel/(se*np.sqrt(2))).to_numpy(np.float32)
    ZA = (accd/(se*2.0)).to_numpy(np.float32)
    live = (N.rolling(60).median().shift(1) >= MIN_LIVE).to_numpy()
    C = CL.to_numpy(np.float32)
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time>=:a AND funding_time<:b "
             "ORDER BY funding_time")
    CUM = np.zeros((n, len(syms)), np.float32)
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='180s'"))
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
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - HOLD - DELAY
    R[:hi_] = ((C[DELAY+HOLD:DELAY+HOLD+hi_]/C[DELAY:DELAY+hi_]-1.0)*100.0
               - (CUM[DELAY+HOLD:DELAY+HOLD+hi_]-CUM[DELAY:DELAY+hi_]))
    base = np.arange(WIN_H+WINDOW+2*DELTA, n-HOLD-DELAY-1)
    base = base[base % ANCH == 0]
    zv, za, lv, Ra = ZV[base], ZA[base], live[base], R[base]
    bmp, irb = bump[base], irr[base]
    OKL = (zv >= Z_LO)&(zv <= Z_HI)&(za < ACC_MAX)&lv&np.isfinite(zv)
    OKS = (zv >= -Z_HI)&(zv <= -Z_LO)&(za > -ACC_MAX)&lv&np.isfinite(zv)
    nph = HOLD//ANCH
    log.info("앵커 %s개 · 후보 롱 %s · 숏 %s", f"{len(base):,}",
             f"{int(OKL.sum()):,}", f"{int(OKS.sum()):,}")

    def masks(npk):
        """앵커 내 순위합으로 **가장 얇은** npk 종목."""
        out = []
        for ph in range(nph):
            per = []
            for i in range(ph, len(base)-nph-1, nph):
                ent = []
                ok = True
                for OK in (OKL, OKS):
                    ii = np.where(OK[i])[0]
                    if len(ii) < cfg.min_cand:
                        ok = False; break
                    b_, r_ = bmp[i][ii], irb[i][ii]
                    m = np.isfinite(b_) & np.isfinite(r_)
                    if m.sum() < cfg.min_cand:
                        ok = False; break
                    ii, b_, r_ = ii[m], b_[m], r_[m]
                    sc = (pd.Series(b_).rank().to_numpy()
                          + pd.Series(r_).rank().to_numpy())   # 클수록 얇다
                    if len(ii) < npk:
                        ok = False; break
                    ent.append(ii[np.argsort(-sc)[:npk]])
                if ok:
                    per.append((i, ent[0], ent[1]))
            if per:
                out.append(per)
        return out

    def stat(mk, Rm):
        tot = []
        for ph in mk:
            v = []
            for i, L, S in ph:
                r = Rm[i]
                a_, b_ = r[L], r[S]
                a_, b_ = a_[np.isfinite(a_)], b_[np.isfinite(b_)]
                if len(a_) and len(b_):
                    v.append(a_.mean() - b_.mean())
            if v:
                tot.append(np.mean(v))
        return float(np.mean(tot)) - FEE2 if tot else np.nan

    # 지연별 수익률 판 — 신호는 그대로, 진입만 늦춘다
    RD = {}
    for d in DELAYS:
        f = np.full(C.shape, np.nan, np.float32)
        h2 = n - HOLD - d
        f[:h2] = ((C[d+HOLD:d+HOLD+h2]/C[d:d+h2]-1.0)*100.0
                  - (CUM[d+HOLD:d+HOLD+h2]-CUM[d:d+h2]))
        RD[d] = f[base]
    MK = {t: masks(t) for t in NPICK}
    rng = np.random.default_rng(cfg.seed)
    shifts = rng.integers(nph*4, len(base)-nph*4, size=cfg.reps)
    rows, best = [], np.full(cfg.reps, -9e9)
    for t, mk in MK.items():
        if not mk:
            continue
        r_ = {"종목수": t, "앵커": sum(len(x) for x in mk)}
        for d in DELAYS:
            r_[f"지연{d*5}분"] = stat(mk, RD[d])
        rows.append(r_)
        for i, sh in enumerate(shifts):     # 판정은 지연 1봉만
            v = stat(mk, np.roll(RD[JUDGE_DELAY], int(sh), axis=0))
            if np.isfinite(v):
                best[i] = max(best[i], v)
        log.info("  종목 %d → 지연5분 %+.4f%% · %.1f분", t,
                 r_["지연5분"], (time.time()-t0)/60)
    R0 = pd.DataFrame(rows)
    print(f"\n■ 유동성 얇음 · **고정 종목 수** · 뒤돌아보기 {LOOK}분 "
          f"· 마찰 {FEE2}% 차감 · 위상 평균")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    print("\n  지연 감쇠 — 5분 대비 남은 비율(%)  [얇은 종목은 호가 튐이 심하다]")
    for r in R0.itertuples():
        b0 = getattr(r, "지연5분")
        print(f"    종목 {r.종목수:>2}  " + " · ".join(
            f"{d*5}분 {100*getattr(r, f'지연{d*5}분')/b0:.0f}" for d in DELAYS))
    obs = float(R0[f"지연{JUDGE_DELAY*5}분"].max())
    pm = float((best >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(R0)}칸 · **한쪽 검정**)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "thin_liquidity.csv", index=False)
    (OUT / "thin_liquidity.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
