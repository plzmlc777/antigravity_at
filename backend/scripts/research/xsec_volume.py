"""거래량 × 되돌림 — 같은 하락이라도 대량이면 정보, 소량이면 공백.

## 왜 (2026-08-31 04:31)

오늘 밤 열 축을 닫았는데 **거래량을 한 번도 안 썼다**. 5분봉 캐시에 `v` 가
2년치 들어 있는데 생존 필터로 `n`(봉 개수)만 썼다.

가설:

    1시간 급락 + **대량** 거래 → 정보에 의한 매도 → 지속
    1시간 급락 + **소량** 거래 → 유동성 공백      → 되돌림

되돌림을 무차별로 걸면 둘이 상쇄된다. 전체 평균이 0 이어도 소량 쪽에만
있을 수 있다. 오늘 밤 이 구분을 한 번도 안 했다.

미결제약정은 자료로 닫혔다 — 바이낸스 공개 API 가 **30일만** 준다
(DB 실사: BTCUSDT 30행뿐).

## 설계

    ① 조건부   상대거래량 3분위 **안에서** 되돌림 스프레드
    ② 신호     거래량 급증 자체를 횡단면 신호로 (부호 양쪽 다)
    ③ 결합     되돌림 × 거래량 순위의 곱

⚠ 상대거래량 = 최근 1시간 거래량 ÷ 직전 24시간 시간당 평균. **비율**이라
  종목 크기가 빠진다. 절대 거래량을 쓰면 대형주 판별기가 된다.
⚠ 전부 앵커 **이전** 자료. 진입 5분 지연 · 보유 24h · 펀딩 포함 · 왕복 0.072%
⚠ 최대통계량으로 격자 전체 보정(교훈#95). 통과하면 **사전지정하고
  표본 밖 2022-08~2024-08 에서 확인**(교훈: 표본 내 통과는 절반이다)

사용:
  python3 -m scripts.research.xsec_volume --smoke 60 --reps 30
  python3 -m scripts.research.xsec_volume --reps 1000
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
log = logging.getLogger("xvol")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H, DELAY = 12, 24, 1
FEE1 = 0.036
SLOTS = (10, 20, 48)
VBINS = ("소량", "중간", "대량")


@dataclass(frozen=True)
class Cfg:
    min_syms_bin: int = 25
    min_bars_in_5: float = 3.0
    reps: int = 1_000
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


def build_masks(SIG, COND, b, pos, N, cfg):
    """조건 3분위 중 b칸 **안에서** 상·하위 N종목."""
    x, c = SIG[pos], (COND[pos] if COND is not None else None)
    if c is None:
        sel = np.isfinite(x)
    else:
        okc = np.isfinite(c)
        with np.errstate(invalid="ignore"):
            e1, e2 = np.nanquantile(np.where(okc, c, np.nan), [1/3, 2/3], axis=1)
        sel = okc & ((c <= e1[:, None]) if b == 0 else
                     (c > e2[:, None]) if b == 2 else
                     ((c > e1[:, None]) & (c <= e2[:, None])))
        sel &= np.isfinite(x)
    rows, tops, bots = [], [], []
    for i in range(len(pos)):
        ii = np.where(sel[i])[0]
        if len(ii) < max(2*N + 10, cfg.min_syms_bin):
            continue
        o = ii[np.argsort(x[i][ii])]
        rows.append(pos[i]); bots.append(o[:N]); tops.append(o[-N:])
    return (np.asarray(rows, int), tops, bots)


def spread(mk, R):
    rows, tops, bots = mk
    out = np.empty(len(rows))
    for k, i in enumerate(rows):
        r = R[i]
        t_, b_ = tops[k], bots[k]
        t_ = t_[np.isfinite(r[t_])]; b_ = b_[np.isfinite(r[b_])]
        out[k] = (float(r[t_].mean() - r[b_].mean()) - 2*FEE1
                  if len(t_) and len(b_) else np.nan)
    return out[np.isfinite(out)]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--cache", default="")
    p.add_argument("--limit-to", default="")
    p.add_argument("--only", default="", help="'슬롯,조건,분위' 사전지정 단일칸")
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
    if a.smoke:
        fs = fs[:a.smoke]
    t0 = time.time()
    CL, NB, V, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    # 상대거래량 — 최근 1h ÷ 직전 24h 시간당 평균. **비율**이라 종목 크기가 빠진다
    v1 = V.rolling(SIG_BARS).sum()
    v24 = V.rolling(288).sum().shift(SIG_BARS) / (288/SIG_BARS)
    RV = np.where(live, (v1 / (v24 + 1e-9)).to_numpy(np.float32), np.nan)
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    REV = np.where(live, -r, np.nan)                    # 큰 값 = 롱(되돌림)
    kk, d = HOLD_H*12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - kk - d
    R[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
               - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
    anc = np.arange(288 + SIG_BARS, n - kk - d - 1)
    anc = anc[anc % ANCH == 0]
    pos = np.arange(0, len(anc) - HOLD_H - 1, HOLD_H)
    REVa, RVa, Ra = REV[anc], RV[anc], R[anc]
    log.info("판 %s봉 × %d종목 · 블록 %d · %s ~ %s · %.1f분", f"{n:,}", len(syms),
             len(pos), idx[anc[pos]].min().date(), idx[anc[pos]].max().date(),
             (time.time()-t0)/60)

    CELLS = []
    if a.only:
        N_, cond_, b_ = a.only.split(",")
        CELLS = [(int(N_), cond_, int(b_))]
        log.info("**사전지정 단일칸** %s", a.only)
    else:
        for N in SLOTS:
            CELLS.append((N, "무조건", -1))
            for b in range(3):
                CELLS.append((N, "상대거래량", b))
            CELLS.append((N, "거래량신호", -1))     # 거래량 자체를 신호로
    MSK, rows = {}, []
    for (N, cond, b) in CELLS:
        if cond == "거래량신호":
            mk = build_masks(-RVa, None, -1, pos, N, cfg)   # 소량이 위 = 롱
        elif cond == "무조건":
            mk = build_masks(REVa, None, -1, pos, N, cfg)
        else:
            mk = build_masks(REVa, RVa, b, pos, N, cfg)
        if len(mk[0]) < 100:
            continue
        MSK[(N, cond, b)] = mk
        v = spread(mk, Ra)
        rows.append({"슬롯": N, "조건": cond,
                     "분위": VBINS[b] if b >= 0 else "—", "블록": len(v),
                     "평균": float(v.mean()),
                     "t": float(v.mean()/(v.std(ddof=1)/np.sqrt(len(v))))})
    R0 = pd.DataFrame(rows).sort_values("평균", ascending=False)
    print(f"\n■ 거래량 × 되돌림 (보유{HOLD_H}h · 지연{DELAY}봉 · 왕복 {2*FEE1}% · 펀딩 포함)")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    nb_ = len(pos)
    obs = float(R0.평균.max())
    null = np.empty(cfg.reps)
    keys = list(MSK)
    for i in range(cfg.reps):
        sh = int(rng.integers(1, nb_ - 1)) * HOLD_H
        Rr = np.roll(Ra, sh, axis=0)
        best = -9e9
        for k in keys:
            v = spread(MSK[k], Rr)
            if len(v) >= 100:
                best = max(best, float(v.mean()))
        null[i] = best
        if (i+1) % 100 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pm = float((null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(keys)}칸)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(null):+.4f}% "
          f"· 95분위 {np.quantile(null,.95):+.4f}%  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if a.cache else ("is125" if a.limit_to else "is")
    R0.to_csv(OUT / f"xsec_volume_{tag}.csv", index=False)
    (OUT / f"xsec_volume_{tag}.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(keys),
         "blocks": int(nb_), "symbols": len(syms),
         "null_median": float(np.median(null))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
