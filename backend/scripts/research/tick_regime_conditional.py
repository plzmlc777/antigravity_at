"""신호의 엣지가 **국면에 따라 달라지나** — 예측이 아니라 조건부 관측.

## 앞선 검정과 무엇이 다른가 (2026-08-29, 대표님 질문)

앞서 세 번 닫힌 것은 "**과거 방향이 앞으로를 맞히나**"였다(전부 실패).
여기서 묻는 건 다르다 — "**신호의 초과분이 국면마다 다른가**".

    예측    지금 하락이니 앞으로도 하락일 것이다        ⛔ 오늘 세 번 실패
    조건부  지금 하락 국면에서는 롱 밴드가 특히 나쁘다   ← 이건 관측 가능

그럴 이유도 있다. 롱 밴드는 **떨어진 종목을 사는** 규칙이라 지속 하락장에서
구조적으로 불리할 수 있다. 그러면 "하락 국면에는 롱을 멈추고 숏만" 이 성립한다.

## 설계

    국면   그 시각까지의 **과거** 360분 유니버스 중앙 수익률 (후행만)
    구간   국면을 5분위로 갈라
    측정   각 구간에서 롱 밴드·숏 밴드의 **시장 대비 초과분**

⚠ 국면은 자기상관이 극심하다. 3일치면 독립 국면 에피소드가 5~10개뿐이다.
  구간별 n 이 수만이어도 **독립 관측은 그것뿐**이다. 시각 클러스터로 t 를 낸다.
⚠ 위약은 원형 회전. 국면 라벨은 그대로 두고 진입 위치만 민다.
⚠ 표본이 얇으므로 "차이가 있다"보다 "차이가 안 보인다"에 더 무게를 둔다.

사용:
  python3 -m scripts.research.tick_regime_conditional --smoke 60
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
log = logging.getLogger("cond")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
FWD, STEP, MIN_LIVE_TR = 120, 5, 5.0
MKT_WIN = 360                      # 국면을 재는 과거 창(분)
QLABELS = ("강한하락", "하락", "횡보", "상승", "강한상승")


@dataclass(frozen=True)
class Cfg:
    min_ticks: int = 2_000
    fee_pct: float = 0.036
    reps: int = 200
    seed: int = 20260829


def build(sym: str, cfg: Cfg):
    d = TICKS / sym
    fs = sorted(d.glob("*.parquet"))
    if not fs:
        return None
    t = pd.concat([pd.read_parquet(f, columns=["ts_ms", "price", "qty"])
                   for f in fs], ignore_index=True)
    t = t[(t.price > 0) & (t.qty > 0)]
    if len(t) < cfg.min_ticks:
        return None
    g = t.sort_values("ts_ms").groupby(t.ts_ms // 60_000)
    b = pd.DataFrame({"cl": g.price.last(), "ntr": g.price.size()})
    b.index = pd.to_datetime(b.index * 60_000, unit="ms", utc=True)
    return b


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--reps", type=int, default=None)
    p.add_argument("--out", default="")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    log.info("설정 %s", json.dumps(asdict(cfg), ensure_ascii=False))

    syms = [s.strip().upper() for s in
            (ROOT / a.universe).read_text().split() if s.strip()]
    if a.smoke:
        syms = syms[:a.smoke]
    t0 = time.time()
    cols = {}
    for i, s in enumerate(syms, 1):
        try:
            b = build(s, cfg)
        except Exception:                                       # noqa: BLE001
            b = None
        if b is not None and len(b) > 1500:
            cols[s] = b
        if i % 100 == 0 or i == len(syms):
            log.info("[%d/%d] %.1f분", i, len(syms), (time.time()-t0)/60)
    idx = pd.date_range(min(b.index.min() for b in cols.values()),
                        max(b.index.max() for b in cols.values()),
                        freq="1min", tz="UTC")
    CL = pd.DataFrame({k: v.cl for k, v in cols.items()}).reindex(idx).ffill()
    NT = pd.DataFrame({k: v.ntr for k, v in cols.items()}).reindex(idx).fillna(0.0)
    log.info("판 %d분 × %d종목 · %.1f분", len(CL), CL.shape[1], (time.time()-t0)/60)

    # ── 신호 (종목별) — 동결분 그대로
    fw = CL.shift(-WIN_H) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW // 2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA)
    acc = vel - vel.shift(DELTA)
    neff = WINDOW / WIN_H
    se = np.sqrt(rate.clip(0.01, 0.99) * (1 - rate.clip(0.01, 0.99)) / neff)
    zv = vel / (se * np.sqrt(2))
    za = acc / (se * 2.0)
    live = NT.rolling(60).median().shift(1) >= MIN_LIVE_TR
    r_f = (CL.shift(-FWD) / CL - 1.0) * 100.0
    mkt_f = r_f.median(axis=1)                       # 그 시각의 시장 선도
    # ⚠ 국면은 **과거만** 본다
    mkt_p = ((CL / CL.shift(MKT_WIN) - 1.0) * 100.0).median(axis=1)

    grid = (np.asarray(CL.index.minute % STEP == 0))
    ok_l = live & (zv >= Z_LO) & (zv <= Z_HI) & (za < ACC_MAX)
    ok_s = live & (zv >= -Z_HI) & (zv <= -Z_LO) & (za > -ACC_MAX)

    ex_l = r_f.sub(mkt_f, axis=0)                    # 롱 초과 = 수익 − 시장
    ex_s = -r_f.add(-mkt_f, axis=0) * 0 + (-r_f).sub(-mkt_f, axis=0)

    qs = mkt_p[grid].dropna().quantile([.2, .4, .6, .8]).to_numpy()
    reg = pd.Series(np.digitize(mkt_p.to_numpy(), qs), index=CL.index)
    rows = []
    for k, lab in enumerate(QLABELS):
        m = grid & (reg.to_numpy() == k) & np.isfinite(mkt_p.to_numpy())
        if m.sum() < 20:
            continue
        for side, okm, exm in (("롱", ok_l, ex_l), ("숏", ok_s, ex_s)):
            sel = okm.loc[m] & exm.loc[m].notna()
            v = exm.loc[m].values[sel.values]
            if len(v) < 200:
                continue
            hrs = pd.Series(CL.index[m]).dt.floor("1h").to_numpy()
            hh = np.repeat(hrs, sel.shape[1])[sel.values.ravel()]
            u, inv = np.unique(hh, return_inverse=True)
            cm = (np.bincount(inv, weights=v, minlength=len(u))
                  / np.maximum(np.bincount(inv, minlength=len(u)), 1))
            t = (cm.mean() / (cm.std(ddof=1) / np.sqrt(len(cm)))
                 if len(cm) > 3 and cm.std(ddof=1) > 0 else np.nan)
            rows.append({"국면": lab, "방향": side, "n": int(len(v)),
                         "시간대": int(len(u)),
                         "시장(과거6h)": float(np.nanmedian(mkt_p.to_numpy()[m])),
                         "초과": float(np.mean(v)),
                         "수수료후": float(np.mean(v) - cfg.fee_pct),
                         "t": float(t) if np.isfinite(t) else np.nan})
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = Path(a.out) if a.out else OUT / "tick_regime_conditional.csv"
    R.to_csv(path, index=False)
    print("\n■ 국면별 초과분 (국면 = 그 시각까지의 **과거** 6시간 시장 중앙)")
    print(R.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    log.info("저장 %s · %.1f분", path, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
