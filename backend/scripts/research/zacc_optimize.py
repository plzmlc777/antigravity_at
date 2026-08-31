"""z_acc 필터 최적화 — 틱 5일. **격자 탐색이므로 위약으로 보정한다.**

## 현행

동결 규칙은 z_acc 를 필터로만 쓴다:
    롱  z_acc < +0.5 · 숏 z_acc > -0.5   (거울)

## 왜 다시 보나 (2026-08-31, 대표님 지시)

페이퍼 원장 실측에서 롱숏10 **두 다리 모두** z_acc 가 **낮을수록** 성공했다
(롱 차 -0.117 t -1.27 · 숏 차 -0.111 t -1.69). 숏은 3분위가 단조였다
(하 +0.34 → 상 -0.25). 거울이 아니다 — 방향과 무관하게 낮은 쪽이 좋았다.

다만 23시각이고 표본이 큰 롱20 에서는 부호가 반대(+0.56)였다. 그래서 잰다.

## 규약

⚠ **격자 탐색이다.** 7개 문턱을 뒤지므로 위약도 7개를 전부 뒤진 최고가 기준선.
⚠ 보유 120분 · 앵커 5분 → 비겹침 격자가 **한 시각에 고정**된다(교훈#111).
  위상 24개 전부 평균.
⚠ 5일이면 위상당 비겹침 블록이 **58개**다. 최적값은 결론이 아니라 후보다.
⚠ 진입 5분 지연 · 왕복 마찰 0.072% · 펀딩 포함

사용:
  python3 -m scripts.research.zacc_optimize --reps 500
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
log = logging.getLogger("zacc")

WIN_H, WINDOW, DELTA = 60, 360, 180        # 동결 (분)
Z_LO, Z_HI = -1.25, -0.25                  # 동결 밴드
HOLD, ANCH, DELAY = 120, 5, 5              # 보유 · 앵커 · 지연 (분)
SLOT, FEE1 = 10, 0.036
ACC_GRID = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 9.9)   # 9.9 = 필터 없음
MIN_LIVE = 5.0


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
    cl, nt = {}, {}
    for s in uni:
        d = TICKS / s
        if not d.is_dir():
            continue
        fs = sorted(d.glob("*.parquet"))
        if not fs:
            continue
        try:
            x = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                           for f in fs], ignore_index=True)
        except Exception:                                      # noqa: BLE001
            continue
        x = x[(x.price > 0) & (x.qty > 0)]
        if len(x) < cfg.min_ticks:
            continue
        g = x.sort_values("ts_ms").groupby(x.ts_ms // 60_000)
        c, n_ = g.price.last(), g.price.size()
        ix = pd.to_datetime(c.index*60_000, unit="ms", utc=True)
        c.index = ix; n_.index = ix
        cl[s], nt[s] = c, n_
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq="1min", tz="UTC")
    CL = pd.DataFrame(cl).reindex(idx).ffill()
    NT = pd.DataFrame(nt).reindex(idx).fillna(0.0)
    syms, n = list(CL.columns), len(CL)
    log.info("틱 → 1분봉 %s분 × %d종목 · %s ~ %s · %.1f분", f"{n:,}", len(syms),
             idx.min().strftime("%m-%d %H:%M"), idx.max().strftime("%m-%d %H:%M"),
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
            acc = np.zeros(n); np.add.at(acc, pos, v)
            CUM[:, j] = np.cumsum(acc).astype(np.float32)

    C = CL.to_numpy(np.float32)
    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    accd = vel - vel.shift(DELTA)
    pr = rate.clip(0.01, 0.99)
    se = np.sqrt(pr*(1-pr) / (WINDOW/WIN_H))
    ZV = (vel / (se*np.sqrt(2))).to_numpy()
    ZA = (accd / (se*2.0)).to_numpy()
    live = (NT.rolling(60).median().shift(1) >= MIN_LIVE).to_numpy()
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - HOLD - DELAY
    R[:hi_] = ((C[DELAY+HOLD:DELAY+HOLD+hi_] / C[DELAY:DELAY+hi_] - 1.0)*100.0
               - (CUM[DELAY+HOLD:DELAY+HOLD+hi_] - CUM[DELAY:DELAY+hi_]))
    base = np.arange(WIN_H+WINDOW+2*DELTA, n - HOLD - DELAY - 1)
    base = base[base % ANCH == 0]
    ZVa, ZAa, Ra = ZV[base], ZA[base], R[base]
    nph = HOLD // ANCH
    log.info("앵커 %s개 · 위상 %d개 · %.1f분", f"{len(base):,}", nph,
             (time.time()-t0)/60)

    def masks(A):
        """문턱 A: 롱 z_acc<A · 숏 z_acc>-A. 위상별 상·하위 SLOT/2."""
        okL = (ZVa >= Z_LO) & (ZVa <= Z_HI) & (ZAa < A) & np.isfinite(ZVa)
        okS = (ZVa >= -Z_HI) & (ZVa <= -Z_LO) & (ZAa > -A) & np.isfinite(ZVa)
        okL &= live[base]; okS &= live[base]
        half = SLOT // 2
        out = []
        for ph in range(nph):
            k = np.arange(ph, len(base) - nph - 1, nph)
            L, S, kk = [], [], []
            for i in k:
                li = np.where(okL[i])[0]; si = np.where(okS[i])[0]
                if len(li) < half or len(si) < half:
                    continue
                L.append(li[np.argsort(ZVa[i][li])[:half]])          # z_vel 낮은 순
                S.append(si[np.argsort(-ZVa[i][si])[:half]])         # 거울
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

    rng = np.random.default_rng(cfg.seed)
    shifts = rng.integers(nph*4, len(base) - nph*4, size=cfg.reps)
    rows, best = [], np.full(cfg.reps, -9e9)
    for A in ACC_GRID:
        mk = masks(A)
        if not mk:
            continue
        blocks = sum(len(k) for k, _, _ in mk)
        o = stat(mk, Ra)
        rows.append({"z_acc문턱": ("없음" if A > 9 else A), "위상": len(mk),
                     "블록합": blocks, "위상당": blocks/max(len(mk), 1),
                     "수수료후": o})
        for i, sh in enumerate(shifts):
            v = stat(mk, np.roll(Ra, int(sh), axis=0))
            if np.isfinite(v):
                best[i] = max(best[i], v)
        log.info("  문턱 %-6s → %+.4f%% · 블록 %s · %.1f분",
                 "없음" if A > 9 else f"{A:+.1f}", o, f"{blocks:,}",
                 (time.time()-t0)/60)
    R0 = pd.DataFrame(rows)
    print(f"\n■ z_acc 필터 최적화 (틱 5일 · 슬롯{SLOT} 롱숏 · 보유{HOLD}분 "
          f"· 지연{DELAY}분 · 왕복 {2*FEE1}% · 펀딩 포함 · 위상 평균)")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(R0.수수료후.max())
    pm = float((best >= obs).mean())
    cur = R0[R0.z_acc문턱 == 0.5].수수료후
    print(f"\n  현행(+0.5) {float(cur.iloc[0]):+.4f}% · 최적 {obs:+.4f}% "
          f"· 개선 {obs - float(cur.iloc[0]):+.4f}%p")
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(R0)}칸 전부 뒤짐)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "zacc_optimize.csv", index=False)
    (OUT / "zacc_optimize.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(R0)},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
