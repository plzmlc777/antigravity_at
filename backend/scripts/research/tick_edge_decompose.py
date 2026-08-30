"""엣지가 왜 5분의 1인가 — 감쇠인가 측정 차이인가.

## 문제 (2026-08-30)

    집단 검정(08-27~28, 24h)   롱 밴드 초과 +0.192%p · 숏 밴드 +0.257%p
    실현 엣지(5일, 비겹침 43)  횡단면 스프레드 **+0.037%**
    페이퍼 롱숏10(150거래)      거래당 **+0.040%**

12배 차이다. 둘 중 하나다.

    ① 감쇠   초기 24시간엔 있었고 지금은 없다
    ② 측정   두 방식이 같은 물건을 안 재고 있다

집단 검정은 **회전 위약 대비 초과**, 실현은 **상·하단 밴드 차이**다. 회전
위약은 같은 종목의 다른 시각이고, 밴드 차이는 같은 시각의 다른 종목이다.
두 기준선이 다르면 값도 다르다.

## 그래서 같은 자료에 두 방식을 나란히

    A. 회전 위약 대비 초과 (집단 검정 방식)
    B. 상·하단 밴드 스프레드 (실현 방식)

그리고 **구간을 쪼개** 감쇠도 같이 본다.

사용:
  python3 -m scripts.research.tick_edge_decompose --reps 300
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "regime"
log = logging.getLogger("decomp")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
FWD, STEP, MIN_LIVE_TR = 120, 5, 5.0


@dataclass(frozen=True)
class Cfg:
    n_sym: int = 200
    min_ticks: int = 2_000
    reps: int = 300
    seed: int = 20260830


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

    uni = [s.strip().upper() for s in
           (ROOT / a.universe).read_text().split() if s.strip()]
    t0 = time.time()
    CLs, NTs = {}, {}
    for s in uni[::max(len(uni)//cfg.n_sym, 1)][:cfg.n_sym]:
        fs = sorted((TICKS / s).glob("*.parquet"))
        if not fs:
            continue
        try:
            t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                           for f in fs], ignore_index=True)
        except Exception:                                       # noqa: BLE001
            continue
        t = t[(t.price > 0) & (t.qty > 0)]
        if len(t) < cfg.min_ticks:
            continue
        g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
        c = g.price.last(); n = g.price.size()
        c.index = pd.to_datetime(c.index * 60_000, unit="ms", utc=True); n.index = c.index
        CLs[s] = c; NTs[s] = n
    idx = pd.date_range(min(c.index.min() for c in CLs.values()),
                        max(c.index.max() for c in CLs.values()), freq="1min", tz="UTC")
    CL = pd.DataFrame(CLs).reindex(idx).ffill()
    NT = pd.DataFrame(NTs).reindex(idx).fillna(0.0)
    log.info("판 %d분 × %d종목 · %.1f분", len(CL), CL.shape[1], (time.time()-t0)/60)

    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_ * (1 - p_) / (WINDOW / WIN_H))
    zv = vel / (se * np.sqrt(2)); za = acc / (se * 2.0)
    live = NT.rolling(60).median().shift(1) >= MIN_LIVE_TR
    r_f = (CL.shift(-FWD) / CL - 1.0) * 100.0
    grid = np.asarray(CL.index.minute % STEP == 0)

    L = ((zv >= Z_LO) & (zv <= Z_HI) & (za < ACC_MAX) & live)
    S = ((zv >= -Z_HI) & (zv <= -Z_LO) & (za > -ACC_MAX) & live)
    need = WINDOW + 2 * DELTA + WIN_H
    valid = np.zeros(len(CL), bool); valid[need:len(CL)-FWD] = True
    valid &= grid

    days = (CL.index[-1] - CL.index[0]).total_seconds() / 86400
    half = CL.index[0] + (CL.index[-1] - CL.index[0]) / 2
    # ⚠ `CL.index <= half` 는 이미 ndarray 다 — .to_numpy() 가 없다
    segs = [("전체", valid),
            ("전반부", valid & np.asarray(CL.index <= half)),
            ("후반부", valid & np.asarray(CL.index > half))]

    rng = np.random.default_rng(cfg.seed)
    print(f"\n■ 자료 {days:.2f}일 · 종목 {CL.shape[1]} · 앵커 {int(valid.sum()):,}")
    print(f"\n{'구간':>7}{'방식':>26}{'n':>9}{'값':>10}{'위약':>10}{'초과':>10}")
    print('  ' + '─' * 70)
    rows = []
    for lab, m in segs:
        rf = r_f.to_numpy(); Lm = L.to_numpy(); Sm = S.to_numpy()
        mk = np.nanmedian(np.where(np.isfinite(rf), rf, np.nan), axis=1)
        # ── B. 상·하단 밴드 스프레드
        lo_r = np.nanmean(np.where(Lm, rf, np.nan), axis=1)
        hi_r = np.nanmean(np.where(Sm, rf, np.nan), axis=1)
        sp = (lo_r - hi_r)[m]
        sp = sp[np.isfinite(sp)]
        # ── A. 회전 위약 대비 (롱 밴드)
        obs_l = np.nanmean(np.where(Lm[m], rf[m], np.nan))
        obs_s = np.nanmean(np.where(Sm[m], -rf[m], np.nan))
        pl_l, pl_s = [], []
        n = len(CL)
        for _ in range(cfg.reps):
            sh = int(rng.integers(1, n - FWD - 1))
            rr = np.roll(rf, sh, axis=0)
            pl_l.append(np.nanmean(np.where(Lm[m], rr[m], np.nan)))
            pl_s.append(np.nanmean(np.where(Sm[m], -rr[m], np.nan)))
        for nm, o, pl in (("A. 회전위약 대비 · 롱", obs_l, pl_l),
                          ("A. 회전위약 대비 · 숏", obs_s, pl_s)):
            print(f"{lab:>7}{nm:>26}{int(m.sum()):>9,}{o:>+9.4f}%"
                  f"{np.mean(pl):>+9.4f}%{o-np.mean(pl):>+9.4f}%")
            rows.append({"구간": lab, "방식": nm, "값": o, "위약": float(np.mean(pl)),
                         "초과": o - float(np.mean(pl))})
        print(f"{lab:>7}{'B. 밴드 스프레드(하−상)':>26}{len(sp):>9,}"
              f"{sp.mean():>+9.4f}%{'':>10}{sp.mean():>+9.4f}%")
        rows.append({"구간": lab, "방식": "B. 밴드 스프레드", "값": float(sp.mean()),
                     "위약": 0.0, "초과": float(sp.mean())})
        print(f"{'':>7}{'  (시장 중앙)':>26}{'':>9}{np.nanmean(mk[m]):>+9.4f}%")
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "tick_edge_decompose.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
