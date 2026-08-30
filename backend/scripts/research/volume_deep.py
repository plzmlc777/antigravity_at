"""거래량(관심) 신호를 깊이 판다 — 위상 평균 기준으로.

## 지금까지 (2026-08-31 04:47)

    신호   상대거래량 = 최근 1h 거래량 ÷ 직전 24h 시간당 평균
           **조용한 종목을 롱 · 급증한 종목을 숏** · 보유 24h · 지연 5분

    위상 평균 +0.0544 · 귀무 중앙 -0.0484 · 95분위 +0.0384   **p 0.030**
    24위상 중 14개 양수 (슬롯20 은 18개)

같은 위상 검사에서 되돌림 축은 죽었다(위상평균 -0.0873 · 6/24 · p 0.780).
[[교훈#111]]

기제도 말이 된다 — 거래량 급증은 **관심의 대리변수**이고, 관심을 받는 자산이
못하는 것은 주식에서 알려진 효과다.

## 남은 네 관문

    ① 진입 지연   급증 종목은 극단 이동 종목이다 → 호가 튐 (5·10·30·60분)
    ② 다리 분해   숏 다리가 급증 종목 → **알트 하락 표류**일 수 있다.
                  다리마다 **자기 방향 위약**과 대라(교훈#91·101).
                  오늘 밤 이 관문이 되돌림 축을 죽였다.
    ③ 표본 밖     2022-08~2024-08 (같은 종목으로 맞춰서)
    ④ 종목 수     240 에서만 봤다 (교훈#110)

⚠ **모든 수치는 위상 24개 평균**이다. 한 위상 값은 보고하지 않는다.

사용:
  python3 -m scripts.research.volume_deep --reps 300
  python3 -m scripts.research.volume_deep --cache runs/bars5m_oos --reps 300
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
log = logging.getLogger("vdeep")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H = 12, 24
FEE1 = 0.036
SLOTS = (10, 20)
DELAYS = (1, 2, 6, 12)          # 5 · 10 · 30 · 60분


@dataclass(frozen=True)
class Cfg:
    min_bars_in_5: float = 3.0
    reps: int = 300
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
    """**위상 24개 평균**의 롱·숏 다리. 한 위상 값은 쓰지 않는다."""
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
            ls.append(float(r[o[-N:]].mean()))     # 신호 큰 쪽 = 조용한 종목 = 롱
            ss.append(float(r[o[:N]].mean()))      # 급증 종목 = 숏
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
    v1 = V.rolling(SIG_BARS).sum()
    v24 = V.rolling(288).sum().shift(SIG_BARS) / (288/SIG_BARS)
    X = np.where(live, -(v1 / (v24 + 1e-9)).to_numpy(np.float32), np.nan)
    kk = HOLD_H*12
    base = np.arange(300, n - kk - max(DELAYS) - 1)
    base = base[base % ANCH == 0]
    XA = X[base]
    RA = {}
    for d in DELAYS:
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - kk - d
        f[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
                   - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
        RA[d] = f[base]
    na = len(base)
    log.info("판 %s봉 × %d종목 · 앵커 %s · %s ~ %s · %.1f분", f"{n:,}", len(syms),
             f"{na:,}", idx[base].min().date(), idx[base].max().date(),
             (time.time()-t0)/60)

    CELLS = [(N, d) for N in SLOTS for d in DELAYS]
    rows = []
    for (N, d) in CELLS:
        sp, lg, st = phase_legs(XA, RA[d], N, na)
        rows.append({"슬롯": N, "지연분": d*BAR, "위상평균스프레드": sp,
                     "롱다리": lg, "숏다리": st})
    R0 = pd.DataFrame(rows)
    print(f"\n■ 거래량 신호 · **위상 24개 평균** (보유{HOLD_H}h · 왕복 {2*FEE1}% · 펀딩 포함)")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    piv = R0.pivot_table(index="슬롯", columns="지연분", values="위상평균스프레드")
    print("\n■ 지연 감쇠 — 5분 대비 남은 비율(%)")
    print((piv.div(piv[5], axis=0)*100).to_string(float_format=lambda z: f"{z:.0f}"))

    rng = np.random.default_rng(cfg.seed)
    obs = float(R0.위상평균스프레드.max())
    obsL = float(R0.롱다리.max()); obsS = float(R0.숏다리.max())
    nl = np.empty(cfg.reps); nL = np.empty(cfg.reps); nS = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(HOLD_H, na - HOLD_H))
        b = bl = bs = -9e9
        for (N, d) in CELLS:
            sp, lg, st = phase_legs(XA, np.roll(RA[d], sh, axis=0), N, na)
            if np.isfinite(sp):
                b = max(b, sp); bl = max(bl, lg); bs = max(bs, st)
        nl[i], nL[i], nS[i] = b, bl, bs
        if (i+1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(CELLS)}칸 · 위상 평균 기준)")
    print(f"  스프레드 관측 {obs:+.4f}% · 귀무 중앙 {np.median(nl):+.4f}% "
          f"· 95분위 {np.quantile(nl,.95):+.4f}%  **p = {(nl>=obs).mean():.3f}**")
    print(f"  롱 다리  관측 {obsL:+.4f}% · 귀무 중앙 {np.median(nL):+.4f}% "
          f"· 95분위 {np.quantile(nL,.95):+.4f}%  **p = {(nL>=obsL).mean():.3f}**")
    print(f"  숏 다리  관측 {obsS:+.4f}% · 귀무 중앙 {np.median(nS):+.4f}% "
          f"· 95분위 {np.quantile(nS,.95):+.4f}%  **p = {(nS>=obsS).mean():.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if a.cache else ("is125" if a.limit_to else "is")
    R0.to_csv(OUT / f"volume_deep_{tag}.csv", index=False)
    (OUT / f"volume_deep_{tag}.null.json").write_text(json.dumps(
        {"obs": obs, "p": float((nl >= obs).mean()),
         "obs_long": obsL, "p_long": float((nL >= obsL).mean()),
         "obs_short": obsS, "p_short": float((nS >= obsS).mean()),
         "reps": cfg.reps, "symbols": len(syms), "anchors": int(na)},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
