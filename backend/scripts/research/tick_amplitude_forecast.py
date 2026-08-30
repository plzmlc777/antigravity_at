"""**크기**를 예측한다 — 방향이 아니라 진폭. 그리고 엣지가 진폭에 비례하는가.

## 왜 이 축인가 (2026-08-30, 대표님 지시)

방향 예측을 네 번 시도해 네 번 닫혔다. 그런데 이 세션 초반 국면 기질에
단서가 있었다.

    시간대별   표류(방향)  -0.68% ~ +2.24%   ← 크게 요동
               진폭(크기)   2.40% ~  3.74%   ← 안정적

**크기가 방향보다 안정적이다.** 그리고 되돌림 엣지는 원리상 진폭에 비례해야
한다 — 크게 흔들려야 되돌릴 것이 있다. 진폭이 예측되면 "언제 거래할지"를
정할 수 있고, 이건 방향을 몰라도 쓴다.

## 세 갈래

  ① 진폭 예측     앞으로 120분의 실현 진폭(MFE+MAE)을 후행 변수로 맞히나
  ② 엣지 비례     되돌림 엣지가 실제로 진폭에 비례하나 (조건부 관측)
  ③ 결합          진폭 상위 구간에서만 거래하면 엣지가 마찰을 넘나

②가 없으면 ①이 맞아도 소용없다. ①과 ② 둘 다 서야 ③이 성립한다.

## 위약 설계

  진폭 예측    비겹침 표본 · 목표를 섞는 최대통계량(변수 격자 전체 재탐색)
  엣지 비례    회전 위약 · 진폭 구간별로 따로

⚠ 진폭은 자기상관이 극심하다(변동성 군집). 겹치면 예측력이 통째로 허상이 된다.
⚠ 진폭이 예측돼도 그건 "쉬운 예측"일 수 있다 — 변동성은 원래 지속된다.
  그래서 ②가 진짜 관문이다.

사용:
  python3 -m scripts.research.tick_amplitude_forecast --reps 2000
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
log = logging.getLogger("amp")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI = -1.25, -0.25
FWD, STEP, MIN_LIVE_TR = 120, 5, 5.0


@dataclass(frozen=True)
class Cfg:
    n_sym: int = 200
    min_ticks: int = 2_000
    reps: int = 2_000
    seed: int = 20260830


def load(cfg: Cfg, uni):
    CLs, HIs, LOs, NTs = {}, {}, {}, {}
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
        c = g.price.last(); h = g.price.max(); l = g.price.min(); n = g.price.size()
        ix = pd.to_datetime(c.index * 60_000, unit="ms", utc=True)
        for d, v in ((CLs, c), (HIs, h), (LOs, l), (NTs, n)):
            v.index = ix; d[s] = v
    idx = pd.date_range(min(c.index.min() for c in CLs.values()),
                        max(c.index.max() for c in CLs.values()),
                        freq="1min", tz="UTC")
    CL = pd.DataFrame(CLs).reindex(idx).ffill()
    return (CL, pd.DataFrame(HIs).reindex(idx).ffill(),
            pd.DataFrame(LOs).reindex(idx).ffill(),
            pd.DataFrame(NTs).reindex(idx).fillna(0.0))


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
    CL, HI, LO, NT = load(cfg, uni)
    log.info("판 %d분 × %d종목 · %.1f분", len(CL), CL.shape[1], (time.time()-t0)/60)

    # ── 신호 (동결분)
    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    p_ = rate.clip(0.01, 0.99)
    zv = vel / (np.sqrt(p_ * (1 - p_) / (WINDOW / WIN_H)) * np.sqrt(2))
    live = NT.rolling(60).median().shift(1) >= MIN_LIVE_TR

    # ── 선도: 수익 · 진폭
    r_f = (CL.shift(-FWD) / CL - 1.0) * 100.0
    up = (HI.rolling(FWD).max().shift(-FWD) / CL - 1.0) * 100.0
    dn = (1.0 - LO.rolling(FWD).min().shift(-FWD) / CL) * 100.0
    amp = up + dn                                    # 실현 진폭
    L = (zv >= Z_LO) & (zv <= Z_HI) & live
    S = (zv >= -Z_HI) & (zv <= -Z_LO) & live

    # ── 후행 변수
    lr = np.log(CL.clip(lower=1e-12)).diff()
    F = {}
    F["실현변동성60"] = lr.rolling(60).std() * np.sqrt(60) * 100.0
    F["실현변동성360"] = lr.rolling(360).std() * np.sqrt(360) * 100.0
    F["직전진폭"] = amp.shift(FWD)
    F["고저폭60"] = (HI.rolling(60).max() - LO.rolling(60).min()) / CL * 100.0
    F["체결수비"] = NT.rolling(60).mean() / (NT.rolling(360).mean() + 1e-9)
    F["승률편차"] = (rate - 0.5).abs() * 100.0

    need = WINDOW + 2 * DELTA + WIN_H + FWD
    pos = np.arange(need, len(CL) - FWD, FWD)        # ⚠ 비겹침
    grid_ok = np.zeros(len(CL), bool); grid_ok[pos] = True
    lm, sm = L.to_numpy(), S.to_numpy()
    ampv, rfv = amp.to_numpy(), r_f.to_numpy()

    # ── ① 진폭 예측 (종목·시각 칸 단위, 비겹침 시각만)
    print(f"\n■ ① 진폭 예측 — 비겹침 시각 {len(pos)}개 × 종목 {CL.shape[1]}")
    y = np.where(live.to_numpy()[pos], ampv[pos], np.nan).ravel()
    rows = []
    for k, v in F.items():
        x = np.where(live.to_numpy()[pos], v.to_numpy()[pos], np.nan).ravel()
        m = np.isfinite(x) & np.isfinite(y)
        if m.sum() < 500:
            continue
        r = float(np.corrcoef(x[m], y[m])[0, 1])
        q = np.nanquantile(x[m], [.2, .8])
        rows.append({"변수": k, "n": int(m.sum()), "r": r,
                     "하위20%_진폭": float(np.mean(y[m][x[m] <= q[0]])),
                     "상위20%_진폭": float(np.mean(y[m][x[m] >= q[1]]))})
    A1 = pd.DataFrame(rows).sort_values("r", key=abs, ascending=False)
    print(A1.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ── ② 엣지가 진폭에 비례하나 (실현 진폭 5분위별 스프레드)
    print(f"\n■ ② 되돌림 엣지 × 실현 진폭 5분위 (조건부 관측)")
    allm = grid_ok[:, None] & live.to_numpy()
    A = np.where(allm, ampv, np.nan)
    qs = np.nanquantile(A, [.2, .4, .6, .8])
    labs = ("진폭 최하", "하", "중", "상", "진폭 최상")
    rows = []
    for i, lab in enumerate(labs):
        lo_e = -np.inf if i == 0 else qs[i-1]
        hi_e = np.inf if i == len(labs)-1 else qs[i]
        b = allm & (A > lo_e) & (A <= hi_e)
        nl = b & lm; ns = b & sm
        if nl.sum() < 200 or ns.sum() < 200:
            continue
        rl = float(np.nanmean(np.where(nl, rfv, np.nan)))
        rs = float(np.nanmean(np.where(ns, rfv, np.nan)))
        rows.append({"진폭구간": lab, "롱n": int(nl.sum()), "숏n": int(ns.sum()),
                     "평균진폭": float(np.nanmean(np.where(b, A, np.nan))),
                     "롱수익": rl, "숏수익": rs, "스프레드": rl - rs,
                     "수수료후": rl - rs - 0.072})
    A2 = pd.DataFrame(rows)
    print(A2.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # ── ③ **예측된** 진폭으로 걸러도 되나 (후행 변수 기준)
    print(f"\n■ ③ **후행** 변수로 거른 경우 — 예측 가능한 정보만 사용")
    best = A1.iloc[0]["변수"]
    xv = np.where(allm, F[best].to_numpy(), np.nan)
    qs2 = np.nanquantile(xv, [.2, .4, .6, .8])
    rows = []
    for i, lab in enumerate(labs):
        lo_e = -np.inf if i == 0 else qs2[i-1]
        hi_e = np.inf if i == len(labs)-1 else qs2[i]
        b = allm & (xv > lo_e) & (xv <= hi_e)
        nl = b & lm; ns = b & sm
        if nl.sum() < 200 or ns.sum() < 200:
            continue
        rl = float(np.nanmean(np.where(nl, rfv, np.nan)))
        rs = float(np.nanmean(np.where(ns, rfv, np.nan)))
        rows.append({f"{best} 구간": lab, "롱n": int(nl.sum()), "숏n": int(ns.sum()),
                     "실현진폭": float(np.nanmean(np.where(b, A, np.nan))),
                     "스프레드": rl - rs, "수수료후": rl - rs - 0.072})
    A3 = pd.DataFrame(rows)
    print(A3.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    OUT.mkdir(parents=True, exist_ok=True)
    A1.to_csv(OUT / "amp_predict.csv", index=False)
    A2.to_csv(OUT / "amp_edge_realized.csv", index=False)
    A3.to_csv(OUT / "amp_edge_forecastable.csv", index=False)
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
