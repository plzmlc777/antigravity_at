"""변동성 필터 검증 — 시각 클러스터 t · 회전 위약 최대통계량 · 사후선택 점검.

## 검증할 주장 (2026-08-30)

    실현변동성60 상위 20% 구간에서만 거래하면 수수료 후 +0.2126%,
    나머지 구간은 +0.03~0.06%.

기제도 있다 — 스프레드는 변동성에 비례하는데 **수수료는 고정**이라 고변동성
에서만 남는다. 그럴듯하지만 아직 아무것도 검증되지 않았다.

## 세 관문

  ① 시각 클러스터 t   비겹침 시각이 43개뿐이다. 칸 수(수천)로 세면 안 된다.
  ② 회전 위약        5분위 격자 전체를 다시 훑은 최댓값이 귀무(교훈#95).
  ③ 사후선택 점검     "5분위 중 최상만 좋다"가 우연일 수 있다. 위약에서도
                     최상 분위가 자주 최고로 나오는지 본다.

⚠ 통과해도 표본은 43시각이다. 확정이 아니라 "후보 자격"이다.

사용:
  python3 -m scripts.research.tick_volfilter_verify --reps 2000
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
log = logging.getLogger("volver")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI = -1.25, -0.25
FWD, MIN_LIVE_TR, FEE2 = 120, 5.0, 0.072
LABS = ("최하", "하", "중", "상", "최상")


@dataclass(frozen=True)
class Cfg:
    n_sym: int = 200
    min_ticks: int = 2_000
    reps: int = 2_000
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
    p_ = rate.clip(0.01, 0.99)
    zv = vel / (np.sqrt(p_ * (1 - p_) / (WINDOW / WIN_H)) * np.sqrt(2))
    live = NT.rolling(60).median().shift(1) >= MIN_LIVE_TR
    lr = np.log(CL.clip(lower=1e-12)).diff()
    rv = (lr.rolling(60).std() * np.sqrt(60) * 100.0).to_numpy()
    rf = ((CL.shift(-FWD) / CL - 1.0) * 100.0).to_numpy()
    lm = ((zv >= Z_LO) & (zv <= Z_HI) & live).to_numpy()
    sm = ((zv >= -Z_HI) & (zv <= -Z_LO) & live).to_numpy()

    need = WINDOW + 2 * DELTA + WIN_H
    pos = np.arange(need, len(CL) - FWD, FWD)          # ⚠ 비겹침 시각
    log.info("비겹침 시각 %d개", len(pos))
    RV, LM, SM = rv[pos], lm[pos], sm[pos]
    qs = np.nanquantile(np.where(LM | SM, RV, np.nan), [.2, .4, .6, .8])

    def spreads(R):
        """분위별 (시각당 스프레드 배열)."""
        out = {}
        for i, lab in enumerate(LABS):
            lo = -np.inf if i == 0 else qs[i-1]
            hi = np.inf if i == 4 else qs[i]
            b = (RV > lo) & (RV <= hi)
            per = []
            for k in range(len(pos)):
                l = LM[k] & b[k]; s = SM[k] & b[k]
                if l.sum() < 2 or s.sum() < 2:
                    continue
                per.append(np.nanmean(R[k][l]) - np.nanmean(R[k][s]))
            out[lab] = np.asarray([x for x in per if np.isfinite(x)])
        return out

    obs = spreads(rf[pos])
    print(f"\n■ ① 시각 클러스터 t (비겹침 시각 {len(pos)}개)")
    print(f"  {'구간':>6}{'시각수':>7}{'스프레드':>10}{'수수료후':>10}{'표준편차':>10}{'t':>8}")
    rows = []
    for lab in LABS:
        v = obs[lab]
        if len(v) < 5:
            continue
        t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
        print(f"  {lab:>6}{len(v):>7}{v.mean():>+9.4f}%{v.mean()-FEE2:>+9.4f}%"
              f"{v.std(ddof=1):>9.4f}%{t:>+8.2f}")
        rows.append({"구간": lab, "n_time": len(v), "spread": v.mean(),
                     "net": v.mean()-FEE2, "sd": v.std(ddof=1), "t": t})

    # ── ② 회전 위약: 선도수익만 돌린다. 분위 라벨·밴드는 그대로
    rng = np.random.default_rng(cfg.seed)
    n = len(CL)
    obs_max = max(abs(np.mean(obs[l])/(np.std(obs[l],ddof=1)/np.sqrt(len(obs[l]))))
                  for l in LABS if len(obs[l]) >= 5)
    null = np.empty(cfg.reps); top_is_best = 0
    for i in range(cfg.reps):
        sh = int(rng.integers(1, n - FWD - 1))
        R = np.roll(rf, sh, axis=0)[pos]
        sp = spreads(R)
        ts_ = {}
        for l in LABS:
            v = sp[l]
            ts_[l] = (abs(v.mean()/(v.std(ddof=1)/np.sqrt(len(v))))
                      if len(v) >= 5 and v.std(ddof=1) > 0 else 0.0)
        null[i] = max(ts_.values())
        if max(ts_, key=ts_.get) == "최상":
            top_is_best += 1
        if (i+1) % 500 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pmax = float((null >= obs_max).mean())
    print(f"\n■ ② 회전 위약 최대통계량 ({cfg.reps}회 · 5분위 재탐색)")
    print(f"  관측 최대 |t| {obs_max:.2f} · 위약 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {pmax:.3f}**")
    print(f"\n■ ③ 사후선택 점검 — 위약에서 '최상' 분위가 최고로 나온 비율 "
          f"{100*top_is_best/cfg.reps:.1f}% (우연이면 20%)")
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "volfilter_verify.csv", index=False)
    (OUT / "volfilter_verify.null.json").write_text(json.dumps(
        {"obs_max_t": float(obs_max), "p_max": pmax, "reps": cfg.reps,
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95)),
         "top_is_best_pct": 100*top_is_best/cfg.reps}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
