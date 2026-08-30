"""지속성 게이트 — 전진 검정과 변동성 정규화. 죽이러 간다.

## 지금까지 (2026-08-31 02:26)

    충격12봉 · k13 · 여유2
      차 +0.4706%p · 게이트합 +113.69% 대 항상 +44.94%
      전반 +0.4895 / 후반 +0.4982
      최대통계량(30칸 보정) **p 0.006**

여유를 늘리면 오히려 강해져 미래참조는 아니다. k 에 단조롭고 10/10 양수다.

## 그래도 남은 두 구멍

  ① **전반/후반 일치는 전체에서 고른 칸을 나눠 본 것**이다. 진짜 전진 검정은
     전반에서 칸을 **고르고** 후반에서 그 칸만 써야 한다.

  ② 상위 5% 블록을 빼면 효과가 68% 줄었다(+0.471 → +0.150). 변동성은 뭉친다.
     "최근 양수"가 실제로는 **고변동 구간을 고르고** 있고, 고변동에서 (양수인)
     평균이 확대되는 것뿐일 수 있다. 변동성으로 나눈 계열에서도 살면
     **부호가 지속**되는 것이고, 죽으면 **변동성 타기**다. 서술이 완전히 다르다.

⚠ 전진 검정의 위약은 **같은 선택 절차를 위약에서도 돌려야** 한다. 후반만
  비교하면 선택의 이득이 빠진다.

사용:
  python3 -m scripts.research.persist_wf --reps 500
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("pwf")

BAR, ANCH, Q = 5, 12, 0.2
FEE2 = 0.072
SIGS = {"충격12봉": 12, "충격72봉": 72, "되돌림24h": 288}
HOLD_H, DELAY = 24, 1
KS = (2, 3, 5, 8, 13)
LAGS = (1, 2)
VOLW = 20            # 변동성 정규화 창(블록)


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20
    min_bars_in_5: float = 3.0
    min_per_side: int = 30
    reps: int = 500
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


def gate(x, k, lag, cfg, ref=None):
    """`ref` 로 부호를 판정하고 `x` 로 성과를 잰다(정규화 판본용)."""
    src = x if ref is None else ref
    prev = pd.Series(src).rolling(k).mean().shift(lag).to_numpy()
    m = np.isfinite(prev) & np.isfinite(x)
    p_, n_ = m & (prev > 0), m & (prev <= 0)
    if p_.sum() < cfg.min_per_side or n_.sum() < cfg.min_per_side:
        return None
    return float(x[p_].mean() - x[n_].mean()), float(x[p_].sum()), int(p_.sum())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--smoke", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    fs = sorted(CACHE.glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    t0 = time.time()
    CL, NB, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    kk, d = HOLD_H * 12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - kk - d
    R[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0) * 100.0
               - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
    warm = max(SIGS.values()) + 12
    anc = np.arange(warm, n - kk - d - 1)
    anc = anc[anc % ANCH == 0]
    RA = R[anc]
    MK = {}
    for nm, sb in SIGS.items():
        r = np.full(C.shape, np.nan, np.float32)
        r[sb:] = (C[sb:] / C[:-sb] - 1.0) * 100.0
        XA = np.where(live, -r, np.nan)[anc]
        pos = np.arange(0, len(anc) - HOLD_H - 1, HOLD_H)
        x = XA[pos]
        good = np.isfinite(x).sum(1) >= cfg.min_syms
        x = x[good]
        with np.errstate(invalid="ignore"):
            qs = np.nanquantile(x, [Q, 1-Q], axis=1)
        ok = qs[1] > qs[0]
        x = x[ok]
        MK[nm] = (pos[good][ok], x >= qs[1][ok][:, None], x <= qs[0][ok][:, None])
    na = len(anc)

    def ser(nm, Rm):
        rows, top, bot = MK[nm]
        r = Rm[rows]
        with np.errstate(invalid="ignore"):
            v = (np.nanmean(np.where(top, r, np.nan), axis=1)
                 - np.nanmean(np.where(bot, r, np.nan), axis=1)) - FEE2
        return v[np.isfinite(v)]

    CELLS = [(nm, k, lg) for nm in SIGS for k in KS for lg in LAGS]

    def walkforward(Rm):
        """전반에서 **고르고** 후반에서 그 칸만 쓴다. 선택까지 포함한 절차."""
        S = {nm: ser(nm, Rm) for nm in SIGS}
        h = min(len(v) for v in S.values()) // 2
        best, bv = None, -9e9
        for (nm, k, lg) in CELLS:
            g = gate(S[nm][:h], k, lg, cfg)
            if g and g[0] > bv:
                bv, best = g[0], (nm, k, lg)
        if best is None:
            return None
        nm, k, lg = best
        g2 = gate(S[nm][h:], k, lg, cfg)
        return (best, bv, g2[0] if g2 else np.nan,
                g2[1] if g2 else np.nan, float(S[nm][h:].sum()))

    def volnorm(Rm):
        """변동성으로 나눈 계열에서도 게이트가 사나 — 부호 지속 대 변동성 타기."""
        out = []
        for (nm, k, lg) in CELLS:
            x = ser(nm, Rm)
            sd = pd.Series(x).rolling(VOLW).std().shift(1).to_numpy()
            z = np.where(np.isfinite(sd) & (sd > 0), x / sd, np.nan)
            g0 = gate(x, k, lg, cfg)                       # 원계열
            g1 = gate(z, k, lg, cfg, ref=z)                # 정규화 계열
            if g0 and g1:
                out.append((nm, k, lg, g0[0], g1[0]))
        return out

    W = walkforward(RA)
    print(f"\n■ 전진 검정 — 전반에서 고르고 후반에서 쓴다")
    if W:
        (nm, k, lg), bv, oos, oos_sum, always = W
        print(f"  전반 최고 칸: {nm} · k{k} · 여유{lg} · 전반차 {bv:+.4f}%p")
        print(f"  **후반차 {oos:+.4f}%p** · 후반 게이트합 {oos_sum:+.2f}% "
              f"· 후반 항상합 {always:+.2f}%")

    V = volnorm(RA)
    VD = pd.DataFrame(V, columns=["신호", "k", "여유", "원계열차", "정규화차"])
    print("\n■ 변동성 정규화 — 부호가 지속되나, 변동성을 타는 것뿐인가")
    print(VD.sort_values("원계열차", ascending=False).head(12).to_string(
        index=False, float_format=lambda z: f"{z:+.4f}"))
    print(f"  원계열 최고 {VD.원계열차.max():+.4f} → 그 칸의 정규화차 "
          f"{VD.loc[VD.원계열차.idxmax(), '정규화차']:+.4f}")
    print(f"  정규화 최고 {VD.정규화차.max():+.4f} "
          f"({VD.loc[VD.정규화차.idxmax(), '신호']} · "
          f"k{VD.loc[VD.정규화차.idxmax(), 'k']} · "
          f"여유{VD.loc[VD.정규화차.idxmax(), '여유']})")

    rng = np.random.default_rng(cfg.seed)
    mem = HOLD_H * 2 + max(SIGS.values())
    nw = np.full(cfg.reps, np.nan); nv = np.full(cfg.reps, np.nan)
    for i in range(cfg.reps):
        sh = int(rng.integers(mem, na - mem))
        Rr = np.roll(RA, sh, axis=0)
        w = walkforward(Rr)
        if w:
            nw[i] = w[2]
        vv = volnorm(Rr)
        if vv:
            nv[i] = max(z[4] for z in vv)
        if (i+1) % 50 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    nw_ = nw[np.isfinite(nw)]; nv_ = nv[np.isfinite(nv)]
    pw = float((nw_ >= W[2]).mean()) if W and len(nw_) else np.nan
    vobs = float(VD.정규화차.max())
    pv = float((nv_ >= vobs).mean()) if len(nv_) else np.nan
    print(f"\n■ 회전 위약 ({cfg.reps}회 · **같은 선택 절차를 위약에서도**)")
    print(f"  전진 후반차  관측 {W[2]:+.4f} · 귀무 중앙 {np.median(nw_):+.4f} "
          f"· 95분위 {np.quantile(nw_,.95):+.4f}  **p = {pw:.3f}**")
    print(f"  정규화 최고  관측 {vobs:+.4f} · 귀무 중앙 {np.median(nv_):+.4f} "
          f"· 95분위 {np.quantile(nv_,.95):+.4f}  **p = {pv:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    VD.to_csv(OUT / "persist_wf_volnorm.csv", index=False)
    (OUT / "persist_wf.null.json").write_text(json.dumps(
        {"wf_cell": list(W[0]), "wf_is": W[1], "wf_oos": W[2], "p_wf": pw,
         "vol_obs": vobs, "p_vol": pv, "reps": cfg.reps}, ensure_ascii=False,
        indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
