"""**엣지 자체**를 예측한다 — 방향이 아니라 켜고 끄기.

## 왜 목표를 바꾸나 (2026-08-30)

국면 예측을 세 번 시도해 세 번 닫혔다. 전부 "**시장이 어디로 갈까**"였다.

    과거 시장 방향 → 앞으로 120분        부호 불일치 · p >= 0.11
    승률 추세로 방향 결정                 백분위 0% (부호 반대)
    시장 폭·속도·가속 → 앞으로            r -0.10~-0.14 · p >= 0.47

그런데 정작 필요한 건 방향이 아니다. 롱숏 동시로 돌면 방향은 상쇄된다.
알아야 할 것은 **"앞으로 2시간 동안 이 신호의 엣지가 살아 있나"** — 즉
거래를 **켤지 끌지**다. 이건 한 번도 안 쟀다.

## 예측 대상 (새로움 ①)

    y(t) = 앞으로 120분 동안 실현된 **횡단면 엣지**
         = (하단 밴드 종목들의 선도수익 평균) − (상단 밴드 종목들의 평균)

시장이 어디로 가든 이 값은 시장 성분이 상쇄된 순수 엣지다. 롱숏 동시가
실제로 벌어들이는 것이 바로 이 값이다.

## 예측 변수 (새로움 ②) — 전부 **후행**, 1차 모멘트 밖으로

지금까지는 중앙값만 봤다. 분포의 **모양**이 남아 있다.

    분산    z_vel 의 횡단면 표준편차 — 종목들이 흩어져 있나 몰려 있나
    꼬리    |z_vel| >= 1 인 종목 비율 — 극단이 얼마나 많나
    치우침  z_vel 분포의 왜도
    지속성  승률의 자기상관(직전 창 대비) — 국면이 이어지나 끊기나
    폭      전 종목 위약 승률 (기존 지표 · 대조용)
    변동성  시장 실현변동성
    엣지    **직전** 120분의 실현 엣지 — 엣지 자체가 이어지나

⚠ 비겹침 표본만 쓴다. 겹치면 자기상관을 예측력으로 읽는다.
⚠ 격자를 뒤지므로 최대통계량 위약(교훈#95).
⚠ 5일치면 비겹침 120분 구간이 60개뿐이다. **강한 결론은 못 낸다.**

사용:
  python3 -m scripts.research.tick_edge_forecast --reps 2000
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
log = logging.getLogger("edgefc")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI = -1.25, -0.25
FWD = 120
MIN_LIVE_TR = 5.0


@dataclass(frozen=True)
class Cfg:
    n_sym: int = 180
    min_ticks: int = 2_000
    reps: int = 2_000
    seed: int = 20260830


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

    uni = [s.strip().upper() for s in
           (ROOT / a.universe).read_text().split() if s.strip()]
    t0 = time.time()
    CLs, NTs = {}, {}
    for i, s in enumerate(uni[::max(len(uni)//cfg.n_sym, 1)][:cfg.n_sym], 1):
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
        c.index = pd.to_datetime(c.index * 60_000, unit="ms", utc=True)
        n.index = c.index
        CLs[s] = c; NTs[s] = n
        if i % 60 == 0:
            log.info("[%d] %.1f분", i, (time.time()-t0)/60)
    idx = pd.date_range(min(c.index.min() for c in CLs.values()),
                        max(c.index.max() for c in CLs.values()),
                        freq="1min", tz="UTC")
    CL = pd.DataFrame(CLs).reindex(idx).ffill()
    NT = pd.DataFrame(NTs).reindex(idx).fillna(0.0)
    log.info("판 %d분 × %d종목 · %.1f분", len(CL), CL.shape[1], (time.time()-t0)/60)

    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    neff = WINDOW / WIN_H
    p_ = rate.clip(0.01, 0.99)
    zv = vel / (np.sqrt(p_ * (1 - p_) / neff) * np.sqrt(2))
    live = NT.rolling(60).median().shift(1) >= MIN_LIVE_TR
    r_f = (CL.shift(-FWD) / CL - 1.0) * 100.0

    # ── 예측 대상: 앞으로 120분의 횡단면 엣지
    lo = (zv >= Z_LO) & (zv <= Z_HI) & live
    hi = (zv >= -Z_HI) & (zv <= -Z_LO) & live
    edge = (r_f.where(lo).mean(axis=1) - r_f.where(hi).mean(axis=1))

    # ── 예측 변수 (전부 후행)
    F = pd.DataFrame(index=CL.index)
    zl = zv.where(live)
    F["분산"] = zl.std(axis=1)
    F["꼬리"] = (zl.abs() >= 1.0).sum(axis=1) / live.sum(axis=1).replace(0, np.nan)
    F["치우침"] = zl.skew(axis=1)
    F["폭"] = rate.where(live).mean(axis=1) * 100.0
    F["지속성"] = rate.where(live).corrwith(rate.shift(DELTA).where(live), axis=1)
    lr = np.log(CL.clip(lower=1e-12)).diff()
    F["변동성"] = lr.median(axis=1).rolling(360).std() * np.sqrt(360) * 100.0
    F["직전엣지"] = edge.shift(FWD)          # ⚠ 이미 확정된 것만

    need = WINDOW + 2 * DELTA + WIN_H + FWD
    pos = np.arange(need, len(CL) - FWD, FWD)      # ⚠ **비겹침**
    y = edge.to_numpy()[pos]
    ok = np.isfinite(y)
    rows = []
    for c in F.columns:
        x = F[c].to_numpy()[pos]
        m = ok & np.isfinite(x)
        if m.sum() < 20:
            continue
        xx, yy = x[m], y[m]
        r = float(np.corrcoef(xx, yy)[0, 1])
        med = float(np.median(xx))
        rows.append({"변수": c, "n": int(m.sum()), "r": r,
                     "상위절반_엣지": float(yy[xx > med].mean()),
                     "하위절반_엣지": float(yy[xx <= med].mean()),
                     "차이": float(yy[xx > med].mean() - yy[xx <= med].mean())})
    R = pd.DataFrame(rows)

    # ── 최대통계량 위약: y 를 섞어 같은 격자를 다시
    rng = np.random.default_rng(cfg.seed)
    yy0 = y[ok]
    null = np.empty(cfg.reps)
    Xs = {c: F[c].to_numpy()[pos][ok] for c in F.columns}
    for i in range(cfg.reps):
        yp = rng.permutation(yy0)
        best = 0.0
        for c, x in Xs.items():
            m = np.isfinite(x)
            if m.sum() < 20:
                continue
            best = max(best, abs(float(np.corrcoef(x[m], yp[m])[0, 1])))
        null[i] = best
    obs = float(R.r.abs().max())
    pmax = float((null >= obs).mean())

    R = R.sort_values("r", key=abs, ascending=False)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_edge_forecast.csv"
    R.to_csv(path, index=False)
    print(f"\n■ 예측 대상: 앞으로 {FWD}분 횡단면 엣지 · 비겹침 표본 {int(ok.sum())}개")
    print(f"  엣지 평균 {np.mean(yy0):+.4f}% · 표준편차 {np.std(yy0,ddof=1):.4f}%")
    print(f"\n■ 최대통계량 위약 ({cfg.reps}회 · {len(R)}변수)")
    print(f"  관측 최대 |r| {obs:.3f} · 위약 중앙 {np.median(null):.3f} "
          f"· 95분위 {np.quantile(null,.95):.3f} · **p = {pmax:.3f}**")
    print()
    print(R.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    log.info("저장 %s · %.1f분", path, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
