"""회전 위약 귀무의 꼬리가 어디서 오나 — **추측하지 말고 찍는다**.

보유×신호 격자에서 귀무 최대 |t| 가 42 까지 나왔다. 자유도 21 에서 나올 수
없는 값이다. 마스크 짝을 의심해 고쳤는데 그대로였다(42.13). 그러면 원인이
다른 데 있다는 뜻이다.

이 스크립트는 위약 각 회차마다 **최대 칸의 (평균, 표준편차, 시각수, 시프트)** 를
전부 남긴다. 상위 몇 개를 눈으로 보면 원인이 드러난다.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
WIN_H, WINDOW, DELTA, Q = 60, 360, 180, 0.2
HOLDS = (60, 120, 240)
MIN_LIVE_TR, MIN_TIMES = 5.0, 20
log = logging.getLogger("diag")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    uni = [s.strip().upper() for s in
           (ROOT / "configs/rsi_live_universe.txt").read_text().split() if s.strip()]
    CLs, NTs = {}, {}
    for s in uni[:200]:
        fs = sorted((TICKS / s).glob("*.parquet"))
        if not fs:
            continue
        try:
            t = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        except Exception:                                       # noqa: BLE001
            continue
        t = t[(t.price > 0) & (t.qty > 0)]
        if len(t) < 2000:
            continue
        g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
        c, n = g.price.last(), g.price.size()
        ix = pd.to_datetime(c.index * 60_000, unit="ms", utc=True)
        c.index = ix; n.index = ix; CLs[s] = c; NTs[s] = n
    idx = pd.date_range(min(c.index.min() for c in CLs.values()),
                        max(c.index.max() for c in CLs.values()), freq="1min", tz="UTC")
    CL = pd.DataFrame(CLs).reindex(idx).ffill()
    NT = pd.DataFrame(NTs).reindex(idx).fillna(0.0)
    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    lvm = (NT.rolling(60).median().shift(1) >= MIN_LIVE_TR).to_numpy()
    X0 = -(vel / (np.sqrt(p_*(1-p_)/(WINDOW/WIN_H)) * np.sqrt(2))).to_numpy()
    X0 = np.where(lvm, X0, np.nan)
    RM = {h: np.where(lvm, ((CL.shift(-h)/CL - 1.0)*100.0).to_numpy(), np.nan)
          for h in HOLDS}
    need = WINDOW + 2*DELTA + WIN_H
    rng = np.random.default_rng(7)
    recs = []
    for i in range(300):
        sh = int(rng.integers(1, len(CL) - 240 - 1))
        for h in HOLDS:
            pos = np.arange(need, len(CL) - h, h)
            X, R = X0[pos], np.roll(RM[h], sh, axis=0)[pos]
            per, ns = [], []
            for k in range(len(pos)):
                x, r = X[k], R[k]
                m = np.isfinite(x) & np.isfinite(r)
                if m.sum() < 20:
                    continue
                lo, hi = np.quantile(x[m], [Q, 1-Q])
                if hi <= lo:
                    continue
                per.append(float(r[m][x[m] >= hi].mean() - r[m][x[m] <= lo].mean()))
                ns.append(int(m.sum()))
            v = np.asarray([p for p in per if np.isfinite(p)])
            if len(v) < MIN_TIMES or v.std(ddof=1) <= 0:
                continue
            recs.append({"sh": sh, "h": h, "n": len(v), "mean": v.mean(),
                         "sd": v.std(ddof=1), "cells_med": int(np.median(ns)),
                         "t": v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))})
    D = pd.DataFrame(recs)
    D["at"] = D.t.abs()
    print("\n■ 귀무 상위 12 (|t| 큰 순)")
    print(D.sort_values("at", ascending=False).head(12).to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))
    print("\n■ |t| 분포")
    print(D.at.describe(percentiles=[.5, .9, .99]).to_string())
    print(f"\n■ |t|>10 인 회차 {int((D.at>10).sum())}/{len(D)}")
    big = D[D.at > 10]
    if len(big):
        print("  그때 평균 %.5f · 표준편차 %.6f · 시각수 중앙 %d · 셀수 중앙 %d"
              % (big["mean"].mean(), big.sd.mean(), big.n.median(),
                 big.cells_med.median()))
        print("  시프트 값들:", sorted(big.sh.unique())[:20])
        print("  보유별:", big.h.value_counts().to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
