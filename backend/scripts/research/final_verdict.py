"""최종 판정 — 격자 전체를 **하나의 최대통계량**으로.

## 왜 이 스크립트가 필요한가 (2026-08-31 03:12)

같은 전략이 두 하네스에서 다른 p 를 냈다:

    xsec_funding   분위(≈슬롯48) 스프레드   **p 0.369**  ← 12칸 최대통계량
    persist_realize 슬롯48 복리              **p 0.007**  ← 슬롯별 단일 검정

원인은 다중검정이다. 슬롯 5개를 보고 3개가 통과한 건 보정 안 된 값이다.
이 세션에서 이미 두 번 같은 자리에 걸렸다(교훈#95).

## 그래서 한 번에 잰다

    격자 = 슬롯 4 × 지연 3 × 게이트 2 = **24칸**
    통계량 = 복리 총손익(왕복 마찰 0.072% = 지정가 양다리)
    귀무 = 회전 위약에서 **같은 24칸을 전부 뒤진 최고**

⚠ 회전은 **블록 단위**로 하되 시프트 하한을 신호 기억 이상으로 둔다(교훈#108).
  신호가 1시간이고 블록이 24시간이라 1블록만 밀어도 기억을 넘지만, 0 은 막는다.
⚠ 복리는 변동성 손실을 포함한다 — 귀무 중앙이 -50% 인 것은 그 탓이다.
  그래서 **산술 평균 판정도 나란히** 낸다. 둘이 갈리면 지표 탓이다.

사용:
  python3 -m scripts.research.final_verdict --reps 1000
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
log = logging.getLogger("final")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H = 12, 24
K_GATE, LAG_GATE = 13, 2
FEE1 = 0.036                       # 한 다리 · 왕복 두 다리 = 0.072%
SLOTS = (5, 10, 20, 48)
DELAYS = (1, 2, 6)
GATES = (False, True)


@dataclass(frozen=True)
class Cfg:
    min_bars_in_5: float = 3.0
    reps: int = 1_000
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


def rank_order(XA):
    """블록마다 유한한 종목의 신호 오름차순 색인. 위약에서 재사용한다."""
    out = []
    for i in range(XA.shape[0]):
        ii = np.where(np.isfinite(XA[i]))[0]
        out.append(ii[np.argsort(XA[i][ii])] if len(ii) else ii)
    return out


def spread(ORD, R, N):
    v = np.full(len(ORD), np.nan)
    for i, o in enumerate(ORD):
        if len(o) < 2*N + 10:
            continue
        r = R[i]
        lo_, hi_ = o[:N], o[-N:]
        if not (np.isfinite(r[lo_]).all() and np.isfinite(r[hi_]).all()):
            lo_ = lo_[np.isfinite(r[lo_])]; hi_ = hi_[np.isfinite(r[hi_])]
            if len(lo_) < N//2 or len(hi_) < N//2:
                continue
        v[i] = float(r[hi_].mean() - r[lo_].mean()) - 2*FEE1
    return v


def gate_mask(v):
    prev = pd.Series(v).rolling(K_GATE).mean().shift(LAG_GATE).to_numpy()
    return np.isfinite(prev) & (prev > 0) & np.isfinite(v)


def compound(v, m):
    e = 1.0
    for i in range(len(v)):
        if m[i]:
            e *= (1.0 + v[i]/100.0)
    return (e - 1.0)*100.0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--cache", default="", help="다른 구간 캐시로 표본 밖 검정")
    p.add_argument("--limit-to", default="",
                   help="⚠ 이 경로에 있는 종목만 쓴다. 표본 밖 구간은 종목이 적은데"
                        "(125 대 240) **종목 수도 표본**이다 — 오늘 밤 네 번 봤다. "
                        "같은 종목으로 맞춰야 사과 대 사과가 된다")
    p.add_argument("--only", default="",
                   help="'슬롯,지연,게이트0|1' — **사전지정 단일칸**. 표본 밖에서는 "
                        "격자를 다시 뒤지면 안 된다. 그러면 다중검정이 되고 "
                        "표본 밖의 의미가 사라진다")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    if a.only:
        N_, d_, g_ = a.only.split(",")
        CELLS = [(int(N_), int(d_), bool(int(g_)))]
        log.info("**사전지정 단일칸** 슬롯%s · 지연%s · 게이트%s — 다중검정 없음",
                 N_, d_, g_)
    else:
        CELLS = [(N, d, g) for N in SLOTS for d in DELAYS for g in GATES]
    cache = (ROOT / a.cache) if a.cache else CACHE
    fs = sorted(cache.glob("*.parquet"))
    if a.limit_to:
        keep = {x.stem for x in (ROOT / a.limit_to).glob("*.parquet")}
        fs = [x for x in fs if x.stem in keep]
        log.info("종목 제한 — %s 에 있는 %d종목만", a.limit_to, len(fs))
    if not fs:
        raise SystemExit(f"캐시가 비었다: {cache}")
    t0 = time.time()
    CL, NB, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    X = np.where(live, -r, np.nan)
    kk = HOLD_H*12
    anc = np.arange(SIG_BARS+12, n - kk - max(DELAYS) - 1)
    _ = a.only
    anc = anc[anc % ANCH == 0]
    pos = np.arange(0, len(anc) - HOLD_H - 1, HOLD_H)
    XA = X[anc][pos]
    ORD = rank_order(XA)
    RA = {}
    for d in sorted({c[1] for c in CELLS} if a.only else set(DELAYS)):
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - kk - d
        f[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
                   - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
        RA[d] = f[anc][pos]
    nb_ = len(pos)
    log.info("블록 %d개 · 종목 %d · %s ~ %s · %.1f분", nb_, len(syms),
             idx[anc[pos]].min().date(), idx[anc[pos]].max().date(),
             (time.time()-t0)/60)

    rows, OBS_C, OBS_M = [], {}, {}
    for (N, d, g) in CELLS:
        v = spread(ORD, RA[d], N)
        m = gate_mask(v) if g else np.isfinite(v)
        c_ = compound(v, m)
        mu = float(np.nanmean(v[m]))
        OBS_C[(N, d, g)] = c_; OBS_M[(N, d, g)] = mu
        rows.append({"슬롯": N, "지연": d, "게이트": "예" if g else "아니오",
                     "블록": int(m.sum()), "복리": c_, "산술평균": mu})
    R0 = pd.DataFrame(rows).sort_values("복리", ascending=False)
    print(f"\n■ 격자 24칸 — 1h 되돌림 · 보유{HOLD_H}h · 왕복 마찰 {2*FEE1}% · 펀딩 포함")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.3f}"))

    rng = np.random.default_rng(cfg.seed)
    nc = np.empty(cfg.reps); nm = np.empty(cfg.reps)
    for i in range(cfg.reps):
        # ⚠ 시프트 하한 1블록(24h) — 신호 기억 1시간을 넘는다. 0 은 막는다.
        sh = int(rng.integers(1, nb_ - 1))
        bc, bm = -9e9, -9e9
        for (N, d, g) in CELLS:
            v = spread(ORD, np.roll(RA[d], sh, axis=0), N)
            m = gate_mask(v) if g else np.isfinite(v)
            if m.sum() < 50:
                continue
            bc = max(bc, compound(v, m)); bm = max(bm, float(np.nanmean(v[m])))
        nc[i], nm[i] = bc, bm
        if (i+1) % 50 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    oc, om = max(OBS_C.values()), max(OBS_M.values())
    pc = float((nc >= oc).mean()); pmu = float((nm >= om).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · **{len(CELLS)}칸 전체 보정**)")
    print(f"  복리     관측 {oc:+.2f}% · 귀무 중앙 {np.median(nc):+.2f}% "
          f"· 95분위 {np.quantile(nc,.95):+.2f}%  **p = {pc:.3f}**")
    print(f"  산술평균 관측 {om:+.4f}% · 귀무 중앙 {np.median(nm):+.4f}% "
          f"· 95분위 {np.quantile(nm,.95):+.4f}%  **p = {pmu:.3f}**")
    print("\n  ⚠ 둘이 갈리면 지표 탓이다 — 복리는 변동성 손실을 포함한다")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "final_verdict.csv", index=False)
    (OUT / "final_verdict.null.json").write_text(json.dumps(
        {"obs_compound": oc, "p_compound": pc, "obs_mean": om,
         "p_mean": pmu, "reps": cfg.reps, "cells": len(CELLS),
         "blocks": nb_, "null_c_median": float(np.median(nc)),
         "null_m_median": float(np.median(nm))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
