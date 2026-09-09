"""`imp` 5분봉 근사의 충실도 — 6년 검정을 돌려도 되는가 (2026-09-09).

## 왜 먼저 재나

`imp` 는 1분 |수익|/거래대금 이라 5분봉으로 접으면 **다른 양이 된다**
(교훈#108 — 5분봉 imp vs 1분봉 imp 최저3 겹침 2.01/3, imp 판정 4건 무효).
6년 아카이브(`bars5m_ext`)로 검정하려면 근사가 얼마나 어긋나는지 먼저 알아야
결과를 해석할 수 있다.

## 어떻게

같은 `runs/bars1m` 에서 **두 판본을 다 만든다**:

    1분판  ar = |Δln c| (1분) · ai = (ar/qv).rolling(60).mean()
           med = ai.rolling(1440, min_periods=360).median().shift(1)
    5분판  1분봉을 5분으로 접은 뒤 같은 수식 (창 60분=12봉 · 24h=288봉)

5분 격자에서 두 판본의 **최저 3 겹침**과 **순위 상관**을 잰다.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("imp5m")


def imp_series(cl, qv, win, med_win, med_min):
    ar = np.abs(np.diff(np.log(np.maximum(cl, 1e-12)), prepend=np.nan)) * 100.0
    ai = pd.Series(ar / np.maximum(qv, 1e-9)).rolling(win).mean()
    med = ai.rolling(med_win, min_periods=med_min).median().shift(1)
    return (ai / med.where(med > 0)).to_numpy(np.float32)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=6)
    ap.add_argument("--symbols", type=int, default=0)
    a = ap.parse_args()
    B = ROOT / "runs" / "bars1m"
    syms = sorted(p.name for p in B.iterdir() if p.is_dir())
    if a.symbols:
        syms = syms[:a.symbols]
    log.info("종목 %d · 최근 %d일", len(syms), a.days)

    G1, G5, names = {}, {}, []
    for s in syms:
        fs = sorted((B / s).glob("*.parquet"))[-a.days:]
        if len(fs) < 3:
            continue
        try:
            d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        except Exception:                                       # noqa: BLE001
            continue
        if "qv" not in d or len(d) < 2000:
            continue
        d = d.sort_values("ts_ms").drop_duplicates("ts_ms")
        t = pd.to_datetime(d.ts_ms, unit="ms", utc=True)
        x = pd.DataFrame({"cl": d.cl.to_numpy(float),
                          "qv": d.qv.to_numpy(float)}, index=t)
        x = x.resample("1min").agg({"cl": "last", "qv": "sum"})
        x["cl"] = x.cl.ffill()
        x["qv"] = x.qv.fillna(0.0)
        i1 = imp_series(x.cl.to_numpy(), x.qv.to_numpy(), 60, 1440, 360)
        # 5분판 — 1분봉을 접는다
        y = x.resample("5min").agg({"cl": "last", "qv": "sum"})
        y["cl"] = y.cl.ffill()
        i5 = imp_series(y.cl.to_numpy(), y.qv.to_numpy(), 12, 288, 72)
        s1 = pd.Series(i1, index=x.index).reindex(y.index)
        G1[s] = s1.to_numpy(np.float32)
        G5[s] = i5
        names.append(s)
    if len(names) < 20:
        raise SystemExit("종목이 너무 적다")
    idx = pd.Series(0, index=pd.DatetimeIndex([])) 
    grid = None
    for s in names:
        pass
    A1 = np.vstack([G1[s] for s in names]).T
    A5 = np.vstack([G5[s] for s in names]).T
    log.info("격자 %d × 종목 %d", *A1.shape)

    ov, rho, n_ok = [], [], 0
    for t in range(A1.shape[0]):
        m = np.isfinite(A1[t]) & np.isfinite(A5[t])
        if m.sum() < 50:
            continue
        i = np.flatnonzero(m)
        a1 = i[np.argsort(A1[t][i])][:3]
        a5 = i[np.argsort(A5[t][i])][:3]
        ov.append(len(set(a1) & set(a5)))
        r1 = pd.Series(A1[t][i]).rank()
        r5 = pd.Series(A5[t][i]).rank()
        rho.append(float(r1.corr(r5)))
        n_ok += 1
    ov = np.array(ov, float)
    rho = np.array(rho, float)
    print(f"\n■ imp 5분봉 근사 충실도 — 격자 {n_ok}개 · 종목 {len(names)}")
    print(f"  최저3 겹침   평균 {ov.mean():.3f}/3  (0겹침 {100*(ov==0).mean():.1f}% · "
          f"3겹침 {100*(ov==3).mean():.1f}%)")
    print(f"  순위 상관    중앙 {np.nanmedian(rho):+.3f} · "
          f"25~75% [{np.nanpercentile(rho,25):+.3f}, {np.nanpercentile(rho,75):+.3f}]")
    print(f"\n※ 교훈#108 의 기록은 겹침 2.01/3 이었다. 이보다 낮으면 6년 결과를"
          f" 'imp 의 6년 성적'으로 읽으면 안 된다.")


if __name__ == "__main__":
    main()
