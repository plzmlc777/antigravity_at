"""주력 횡단면 격자를 **위상 평균**으로 다시 — 오늘 밤 기각들의 재판정.

## 왜 (2026-08-31 05:30)

밤의 마지막에 찾은 결함이 **기각들에도 적용된다**(교훈#111). 보유 24시간에
비겹침 블록이면 격자가 하루 중 한 시각에 고정되는데, 오늘 밤 모든 횡단면
검정이 그랬다. 어떤 축이 그 한 위상에서 나빴을 뿐 위상 평균으로는 다를 수 있다.

그리고 위상 평균은 **앵커를 24배 더 쓴다** — 단순히 더 나은 추정량이다.
한 위상은 블록 755개를 쓰고, 위상 평균은 18,120개 앵커를 전부 쓴다.

## 격자

    신호 5 × 슬롯 2 = 10칸 · 보유 24h · 진입 5분 지연 · 펀딩 포함
    되돌림1h · 되돌림4h · 되돌림24h · 변동조정되돌림1h · 거래량(관심)

⚠ 모든 수치는 위상 24개 평균. 한 위상 값은 출력하지 않는다.
⚠ 다리를 갈라 **자기 방향 위약**과 댄다(교훈#91·101).
⚠ 최대통계량으로 10칸 보정(교훈#95).

사용:
  python3 -m scripts.research.xsec_phase --reps 200
  python3 -m scripts.research.xsec_phase --cache runs/bars5m_oos --reps 200
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
log = logging.getLogger("xphase")

BAR, ANCH = 5, 12
HOLD_H, DELAY = 24, 1
FEE1 = 0.036
SLOTS = (10, 20)


@dataclass(frozen=True)
class Cfg:
    min_bars_in_5: float = 3.0
    reps: int = 200
    seed: int = 20260831


def load(files):
    cl, nb, vv = {}, {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True); s = f.stem
        cl[s] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[s] = pd.Series(d.n.to_numpy(np.float32), index=ts)
        vv[s] = pd.Series(d.v.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0),
            pd.DataFrame(vv).reindex(idx).fillna(0.0), idx)


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


def phase_legs(XA, Rm, N, na):
    """위상 24개 평균의 (스프레드, 롱, 숏). 한 위상 값은 쓰지 않는다."""
    L, S = [], []
    for ph in range(HOLD_H):
        pos = np.arange(ph, na - HOLD_H - 1, HOLD_H)
        ls, ss = [], []
        for i in pos:
            x, r = XA[i], Rm[i]
            m = np.isfinite(x) & np.isfinite(r)
            if m.sum() < 2*N + 10:
                continue
            ii = np.where(m)[0]
            o = ii[np.argsort(x[ii])]
            ls.append(float(r[o[-N:]].mean()))
            ss.append(float(r[o[:N]].mean()))
        if ls:
            L.append(np.mean(ls)); S.append(np.mean(ss))
    if not L:
        return np.nan, np.nan, np.nan
    Lm, Sm = float(np.mean(L)), float(np.mean(S))
    return Lm - Sm - 2*FEE1, Lm - FEE1, -Sm - FEE1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="")
    p.add_argument("--limit-to", default="")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    cache = (ROOT / a.cache) if a.cache else CACHE
    fs = sorted(cache.glob("*.parquet"))
    if a.limit_to:
        keep = {x.stem for x in (ROOT / a.limit_to).glob("*.parquet")}
        fs = [x for x in fs if x.stem in keep]
    t0 = time.time()
    CL, NB, V, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    lr = np.log(CL).diff()

    SIG = {}
    for nm, k in (("되돌림1h", 12), ("되돌림4h", 48), ("되돌림24h", 288)):
        r = np.full(C.shape, np.nan, np.float32)
        r[k:] = (C[k:] / C[:-k] - 1.0) * 100.0
        SIG[nm] = np.where(live, -r, np.nan)
    r1 = np.full(C.shape, np.nan, np.float32)
    r1[12:] = (C[12:] / C[:-12] - 1.0) * 100.0
    sd = (lr.rolling(288).std() * np.sqrt(12) * 100.0).to_numpy(np.float32)
    SIG["변동조정되돌림1h"] = np.where(live, -(r1 / (sd + 1e-9)), np.nan)
    v1 = V.rolling(12).sum()
    v24 = V.rolling(288).sum().shift(12) / 24.0
    SIG["거래량"] = np.where(live, -(v1 / (v24 + 1e-9)).to_numpy(np.float32), np.nan)

    kk, d = HOLD_H*12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - kk - d
    R[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
               - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
    base = np.arange(300, n - kk - d - 1)
    base = base[base % ANCH == 0]
    XA = {nm: v[base] for nm, v in SIG.items()}
    RA = R[base]
    na = len(base)
    del SIG
    log.info("판 %s봉 × %d종목 · 앵커 %s (위상 24개) · %s ~ %s · %.1f분",
             f"{n:,}", len(syms), f"{na:,}", idx[base].min().date(),
             idx[base].max().date(), (time.time()-t0)/60)

    CELLS = [(nm, N) for nm in XA for N in SLOTS]
    rows = []
    for (nm, N) in CELLS:
        sp, lg, st = phase_legs(XA[nm], RA, N, na)
        rows.append({"신호": nm, "슬롯": N, "스프레드": sp, "롱다리": lg, "숏다리": st})
    R0 = pd.DataFrame(rows).sort_values("스프레드", ascending=False)
    print(f"\n■ 주력 격자 · **위상 24개 평균** (보유{HOLD_H}h · 지연 {DELAY*BAR}분 "
          f"· 왕복 {2*FEE1}% · 펀딩 포함 · 종목 {len(syms)})")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    obs = float(R0.스프레드.max()); obsL = float(R0.롱다리.max())
    obsS = float(R0.숏다리.max())
    nl = np.empty(cfg.reps); nL = np.empty(cfg.reps); nS = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(HOLD_H, na - HOLD_H))
        Rr = np.roll(RA, sh, axis=0)
        b = bl = bs = -9e9
        for (nm, N) in CELLS:
            sp, lg, st = phase_legs(XA[nm], Rr, N, na)
            if np.isfinite(sp):
                b = max(b, sp); bl = max(bl, lg); bs = max(bs, st)
        nl[i], nL[i], nS[i] = b, bl, bs
        if (i+1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(CELLS)}칸 · 위상 평균)")
    print(f"  스프레드 관측 {obs:+.4f}% · 귀무 중앙 {np.median(nl):+.4f}% "
          f"· 95분위 {np.quantile(nl,.95):+.4f}%  **p = {(nl>=obs).mean():.3f}**")
    print(f"  롱 다리  관측 {obsL:+.4f}% · 귀무 중앙 {np.median(nL):+.4f}% "
          f"· 95분위 {np.quantile(nL,.95):+.4f}%  **p = {(nL>=obsL).mean():.3f}**")
    print(f"  숏 다리  관측 {obsS:+.4f}% · 귀무 중앙 {np.median(nS):+.4f}% "
          f"· 95분위 {np.quantile(nS,.95):+.4f}%  **p = {(nS>=obsS).mean():.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if a.cache else ("is125" if a.limit_to else "is")
    R0.to_csv(OUT / f"xsec_phase_{tag}.csv", index=False)
    (OUT / f"xsec_phase_{tag}.null.json").write_text(json.dumps(
        {"obs": obs, "p": float((nl >= obs).mean()),
         "p_long": float((nL >= obsL).mean()),
         "p_short": float((nS >= obsS).mean()),
         "reps": cfg.reps, "symbols": len(syms), "anchors": int(na)},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
