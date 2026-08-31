"""z_acc 필터를 대체할 것 찾기 — 틱 5일.

## 왜 (2026-08-31 확인)

동결 규칙의 `z_acc < +0.5` 는 밴드 통과 후보의 **1.86%** 만 거른다(숏 1.59%).
z_acc 분포가 중앙 -0.408 · 95분위 +0.297 이라 문턱이 꼬리에 걸려 있다.
구조적이다 — 밴드가 z_vel < -0.25 를 요구하니 가속도도 음수이기 쉽다.
**필터가 밴드와 거의 중복이다.**

## 대체 후보 (전부 앵커 **이전** 자료 · 틱에서만 되는 것 포함)

    실현변동성60    위험
    거래활성비      최근 1h 체결수 ÷ 24h 평균
    체결방향60      is_buyer_maker 불균형 — **틱 전용**
    고저폭60        분 내 고저 / 종가 (스프레드 대리)
    되돌림60        최근 1시간 수익률 (밴드와 별개의 축)
    z_acc           현행 (대조군)

## 설계

앵커마다 **횡단면 백분위**로 자른다(전역 문턱이 아니라). 절반을 남기고
그중 z_vel 낮은 순으로 슬롯을 채운다. 방향 둘(상위 절반 / 하위 절반).

⚠ 6필터 × 2방향 + 무필터 = 13칸. **명시적 탐색이므로** 위약도 13칸을 뒤진다.
⚠ 위상 24개 평균(교훈#111) · 진입 5분 지연 · 왕복 0.072% · 펀딩 포함
⚠ 단조성을 본다 — 한 칸만 튀면 잡음이다

사용:
  python3 -m scripts.research.filter_search --reps 500
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
log = logging.getLogger("filt")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI = -1.25, -0.25
HOLD, ANCH, DELAY = 120, 5, 5
SLOT, FEE1, MIN_LIVE = 10, 0.036, 5.0
KEEP = 0.5                       # 후보의 절반을 남긴다


@dataclass(frozen=True)
class Cfg:
    min_ticks: int = 2_000
    reps: int = 500
    seed: int = 20260831


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
    cl, nt, hi, lo, bq, tq = {}, {}, {}, {}, {}, {}
    for s in uni:
        d = TICKS / s
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
        m = x.ts_ms // 60_000
        qv = x.price * x.qty
        g = x.sort_values("ts_ms").groupby(m)
        c, n_, h_, l_ = g.price.last(), g.price.size(), g.price.max(), g.price.min()
        b_ = qv.where(~x.is_buyer_maker, 0.0).groupby(m).sum()
        a_ = qv.groupby(m).sum()
        ix = pd.to_datetime(c.index*60_000, unit="ms", utc=True)
        for dd, v in ((cl, c), (nt, n_), (hi, h_), (lo, l_), (bq, b_), (tq, a_)):
            v.index = ix; dd[s] = v
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq="1min", tz="UTC")
    CL = pd.DataFrame(cl).reindex(idx).ffill()
    NT = pd.DataFrame(nt).reindex(idx).fillna(0.0)
    HI = pd.DataFrame(hi).reindex(idx).ffill()
    LO = pd.DataFrame(lo).reindex(idx).ffill()
    BQ = pd.DataFrame(bq).reindex(idx).fillna(0.0)
    TQ = pd.DataFrame(tq).reindex(idx).fillna(0.0)
    syms, n = list(CL.columns), len(CL)
    log.info("틱 → 1분봉 %s분 × %d종목 · %.1f분", f"{n:,}", len(syms),
             (time.time()-t0)/60)

    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
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
            v = np.asarray([float(x[1]) for x in r]) * 100.0
            pos = np.clip(idx.searchsorted(t_, side="left"), 0, n-1)
            acc_ = np.zeros(n); np.add.at(acc_, pos, v)
            CUM[:, j] = np.cumsum(acc_).astype(np.float32)

    C = CL.to_numpy(np.float32)
    lr = np.log(CL).diff()
    fw = CL.shift(-WIN_H)/CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    accd = vel - vel.shift(DELTA)
    pr = rate.clip(0.01, 0.99)
    se = np.sqrt(pr*(1-pr)/(WINDOW/WIN_H))
    ZV = (vel/(se*np.sqrt(2))).to_numpy()
    ZA = (accd/(se*2.0)).to_numpy()
    live = (NT.rolling(60).median().shift(1) >= MIN_LIVE).to_numpy()

    # ── 대체 후보 — 전부 **앵커 이전** (shift(1))
    F = {
        "실현변동성60": (lr.rolling(60).std()*np.sqrt(60)*100.0).shift(1),
        "거래활성비": (NT.rolling(60).mean()
                     / (NT.rolling(1440).mean()+1e-9)).shift(1),
        "체결방향60": ((2*BQ - TQ)/(TQ+1e-9)).rolling(60).mean().shift(1),
        "고저폭60": (((HI.rolling(60).max()-LO.rolling(60).min())
                    / CL)*100.0).shift(1),
        "되돌림60": ((CL/CL.shift(60) - 1.0)*100.0).shift(1),
        "z_acc": pd.DataFrame(ZA, index=idx, columns=syms),
    }
    F = {k: v.to_numpy(np.float32) for k, v in F.items()}

    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - HOLD - DELAY
    R[:hi_] = ((C[DELAY+HOLD:DELAY+HOLD+hi_]/C[DELAY:DELAY+hi_] - 1.0)*100.0
               - (CUM[DELAY+HOLD:DELAY+HOLD+hi_] - CUM[DELAY:DELAY+hi_]))
    base = np.arange(WIN_H+WINDOW+2*DELTA, n - HOLD - DELAY - 1)
    base = base[base % ANCH == 0]
    zv, za, lv = ZV[base], ZA[base], live[base]
    Ra = R[base]
    OKL = (zv >= Z_LO) & (zv <= Z_HI) & lv & np.isfinite(zv)
    OKS = (zv >= -Z_HI) & (zv <= -Z_LO) & lv & np.isfinite(zv)
    nph, half = HOLD // ANCH, SLOT // 2
    log.info("앵커 %s개 · 위상 %d · %.1f분", f"{len(base):,}", nph,
             (time.time()-t0)/60)

    def build(fname, upper):
        """앵커마다 후보를 **횡단면 백분위**로 절반 자른 뒤 z_vel 순으로."""
        fv = F[fname][base] if fname else None
        out = []
        for ph in range(nph):
            k = np.arange(ph, len(base) - nph - 1, nph)
            L, S, kk = [], [], []
            for i in k:
                li, si = np.where(OKL[i])[0], np.where(OKS[i])[0]
                if fv is not None:
                    for arr in (0, 1):
                        ii = li if arr == 0 else si
                        x = fv[i][ii]
                        m = np.isfinite(x)
                        if m.sum() < half*2:
                            ii = ii[:0]
                        else:
                            thr = np.quantile(x[m], 1-KEEP if upper else KEEP)
                            sel = (x >= thr) if upper else (x <= thr)
                            ii = ii[m & sel] if len(ii) == len(m) else ii[sel[m]]
                        if arr == 0:
                            li = ii
                        else:
                            si = ii
                if len(li) < half or len(si) < half:
                    continue
                L.append(li[np.argsort(zv[i][li])[:half]])
                S.append(si[np.argsort(-zv[i][si])[:half]])
                kk.append(i)
            if kk:
                out.append((np.asarray(kk), np.asarray(L), np.asarray(S)))
        return out

    def stat(mk, Rm):
        per = []
        for kk, L, S in mk:
            r = Rm[kk]
            with np.errstate(invalid="ignore"):
                v = (np.nanmean(np.take_along_axis(r, L, 1), 1)
                     - np.nanmean(np.take_along_axis(r, S, 1), 1))
            v = v[np.isfinite(v)]
            if len(v):
                per.append(v.mean())
        return float(np.mean(per)) - 2*FEE1 if per else np.nan

    CELLS = [(None, None)] + [(f, u) for f in F for u in (True, False)]
    rng = np.random.default_rng(cfg.seed)
    shifts = rng.integers(nph*4, len(base) - nph*4, size=cfg.reps)
    rows, best = [], np.full(cfg.reps, -9e9)
    for (fname, upper) in CELLS:
        mk = build(fname, upper)
        if not mk:
            continue
        blocks = sum(len(k) for k, _, _ in mk)
        if blocks < 200:
            continue
        o = stat(mk, Ra)
        rows.append({"필터": fname or "**없음**",
                     "남기는쪽": "—" if fname is None else ("상위" if upper else "하위"),
                     "블록": blocks, "수수료후": o})
        for i, sh in enumerate(shifts):
            v = stat(mk, np.roll(Ra, int(sh), axis=0))
            if np.isfinite(v):
                best[i] = max(best[i], v)
        log.info("  %-12s %s → %+.4f%% · 블록 %s · %.1f분",
                 fname or "없음", "상위" if upper else ("하위" if fname else "—"),
                 o, f"{blocks:,}", (time.time()-t0)/60)
    R0 = pd.DataFrame(rows).sort_values("수수료후", ascending=False)
    print(f"\n■ 필터 대체 탐색 (틱 5일 · 앵커마다 후보 절반 유지 · 슬롯{SLOT} "
          f"롱숏 · 보유{HOLD}분 · 지연{DELAY}분 · 왕복 {2*FEE1}% · 위상 평균)")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(R0.수수료후.max())
    pm = float((best >= obs).mean())
    base_v = float(R0[R0.필터 == "**없음**"].수수료후.iloc[0])
    print(f"\n  무필터 {base_v:+.4f}% · 최고 {obs:+.4f}% · 개선 {obs-base_v:+.4f}%p")
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(R0)}칸 전부 뒤짐)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "filter_search.csv", index=False)
    (OUT / "filter_search.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "baseline": base_v, "reps": cfg.reps,
         "cells": len(R0)}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
