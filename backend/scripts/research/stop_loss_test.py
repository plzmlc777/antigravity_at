"""**최대 손절**이 무엇을 바꾸나 — 14개월 패널로.

## 왜 (2026-09-03 대표님 제안)

`충격숏3`·`충격스프3`이 한 거래에서 **-47.01%** 를 맞았다. 3슬롯 갈래이니
자본의 -15.7% 다. "손절을 10% 정도로 상한을 두면 어떤가"가 질문이다.

⚠ 어제 익절·손절 격자(50칸)는 **손절 0 이 최선**이었다. 다만 거기서 시험한
  손절은 0.3~1.5% 였다 — 잔손실을 자르는 것이고, 10% 는 **꼬리만 막는** 것이라
  성격이 다르다. 다시 재는 게 맞다.
⚠ 손절은 **엣지가 아니라 생존**의 문제다. 거래당이 나빠져도 최악 거래와
  최대낙폭이 줄면 채택 근거가 된다. 둘을 같이 낸다.
⚠ 경로를 봐야 한다 — 진입가 대비 **보유 중 최저/최고**로 도달을 판정한다.
  종가만으로는 중간에 스친 손절을 놓친다.
⚠ 체결 가정: 손절가에 정확히 체결된다고 본다(지정가). 대표님 지시대로
  지정가 슬리피지는 다시 문제 삼지 않는다.

사용:
  python3 -m scripts.research.stop_loss_test --signal imp --mode short --slots 3 --hold 480
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("stoploss")
ROOT = Path(__file__).resolve().parents[2]
MICRO = ROOT / "runs" / "micro1m"


@dataclass(frozen=True)
class Cfg:
    win_h: int = 60
    window: int = 360
    delta: int = 180
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5
    min_live: float = 5.0
    fee_rt: float = 0.072
    hold: int = 120
    noise_win: int = 60
    slots: int = 6
    def dump(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)


def feats(path: Path, c: Cfg):
    d = pd.read_parquet(path).sort_values("ts")
    ix = pd.DatetimeIndex(d.ts)
    g = d.set_index(ix).reindex(pd.date_range(ix.min(), ix.max(), freq="1min",
                                              tz="UTC"))
    cl = g.cl.ffill(); n = len(cl)
    if n < c.win_h + c.window + 2*c.delta + c.hold + 100:
        return None
    cc = cl.to_numpy(float)
    fw = np.full(n, np.nan); fw[:n-c.win_h] = cc[c.win_h:]/cc[:n-c.win_h] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    rate = win.rolling(c.window, min_periods=c.window//2).mean().shift(c.win_h)
    vel = rate - rate.shift(c.delta); acc = vel - vel.shift(c.delta)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_*(1-p_)/max(c.window/c.win_h, 1.0))
    n60 = g.ntr.rolling(c.noise_win).sum().to_numpy()
    f60 = g.flip.rolling(c.noise_win).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        bump = np.where(n60 > 0, f60/n60, np.nan)
        dm = g.dtm.rolling(c.noise_win).mean().to_numpy()
        ds = g.dts.rolling(c.noise_win).mean().to_numpy()
        irr = np.where(dm > 0, ds/dm, np.nan)
        qvv = g.qv.to_numpy(float)
        ar = np.abs(np.diff(np.log(np.maximum(cc, 1e-12)), prepend=np.nan))*100.0
        ai = pd.Series(ar/np.maximum(qvv, 1e-9)).rolling(60).mean()
        med = ai.rolling(1440, min_periods=360).median().shift(1)
        imp = np.where(med.to_numpy() > 0, ai.to_numpy()/med.to_numpy(), np.nan)
        qsk = (g.q90/g.qmed.replace(0, np.nan)).rolling(60).mean().to_numpy()
        rmv = g.rmax.astype(float)
        rmed = rmv.rolling(1440, min_periods=360).median().shift(1).to_numpy()
        rmz = np.where(rmed > 0, rmv.rolling(60).max().to_numpy()/rmed, np.nan)
    nt = g.ntr.astype(float)
    ac1 = nt.rolling(60).corr(nt.shift(1)).to_numpy()
    rev = np.full(n, np.nan); rev[61:] = -(cc[61:]/cc[:-61] - 1.0)*100.0
    # ── 보유 구간의 **최저·최고** (경로) ────────────────
    s = pd.Series(cc)
    fmin = s[::-1].rolling(c.hold, min_periods=1).min()[::-1].shift(-1).to_numpy()
    fmax = s[::-1].rolling(c.hold, min_periods=1).max()[::-1].shift(-1).to_numpy()
    fwd = np.full(n, np.nan)
    fwd[:n-c.hold] = (cc[c.hold:]/cc[:n-c.hold] - 1.0)*100.0
    return pd.DataFrame(
        {"zv": (vel/(se*np.sqrt(2))).to_numpy(),
         "za": (acc/(se*2.0)).to_numpy(),
         "live": g.ntr.rolling(60).median().shift(1).to_numpy(),
         "bump": bump, "irr": irr, "fwd": fwd,
         "imp": -imp, "skew": qsk, "ac1": ac1, "rmz": rmz, "rev": rev,
         "dnmin": (fmin/cc - 1.0)*100.0,      # 보유 중 최저 (진입 대비 %)
         "upmax": (fmax/cc - 1.0)*100.0},     # 보유 중 최고
        index=cl.index)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--signal", default="noise",
                   choices=["noise","kine","imp","skew","ac1","rmz","rev"])
    p.add_argument("--mode", default="both", choices=["both","short"])
    p.add_argument("--slots", type=int, default=6)
    p.add_argument("--hold", type=int, default=120)
    p.add_argument("--stops", default="0,5,10,15,20,30")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    c = Cfg(slots=a.slots, hold=a.hold)
    log.info("인자 도달 — 신호 %s · %s · 슬롯 %d · 보유 %d분 · 손절 %s",
             a.signal, a.mode, a.slots, a.hold, a.stops)
    t0 = time.time()
    F, names = {}, []
    for f in sorted(MICRO.glob("*.parquet")):
        try: r = feats(f, c)
        except Exception as e: log.warning("%s %s", f.stem, e); r = None  # noqa
        if r is not None: F[f.stem] = r; names.append(f.stem)
    lo = min(x.index.min() for x in F.values())
    hi = max(x.index.max() for x in F.values())
    grid = pd.date_range(lo, hi, freq=f"{c.hold}min", tz="UTC")
    K = ("zv","za","live","bump","irr","fwd","imp","skew","ac1","rmz","rev",
         "dnmin","upmax")
    Z = {k: np.full((len(grid), len(names)), np.nan, np.float32) for k in K}
    for j, s in enumerate(names):
        r = F[s].reindex(grid)
        for k in K: Z[k][:, j] = r[k].to_numpy(np.float32)
    del F
    log.info("앵커 %d · 종목 %d", len(grid), len(names))

    half = c.slots // 2
    picks = []          # (숏여부, 만기수익%, 보유중최저%, 보유중최고%)
    for t in range(len(grid)):
        lv, fw = Z["live"][t], Z["fwd"][t]
        dn, up = Z["dnmin"][t], Z["upmax"][t]
        base = (np.isfinite(lv) & np.isfinite(fw) & np.isfinite(dn)
                & np.isfinite(up) & (lv >= c.min_live))
        if a.signal in ("noise","kine"):
            zv, za = Z["zv"][t], Z["za"][t]
            ok = base & np.isfinite(zv) & np.isfinite(za)
            L = ok & (zv >= c.z_lo) & (zv <= c.z_hi) & (za < c.acc_max)
            S = ok & (zv >= -c.z_hi) & (zv <= -c.z_lo) & (za > -c.acc_max)
            if a.signal == "noise":
                pool = L | S
                if not pool.any(): continue
                rb = pd.Series(np.where(pool, Z["bump"][t], np.nan)).rank(pct=True).to_numpy()
                ri = pd.Series(np.where(pool, Z["irr"][t], np.nan)).rank(pct=True).to_numpy()
                key = -(rb + ri)
            else:
                key = None
            if a.mode == "short":
                i = np.flatnonzero(S)
                if len(i) < c.slots: continue
                o = np.argsort(key[i] if key is not None else -zv[i])
                for j in i[o][:c.slots]: picks.append((True, fw[j], dn[j], up[j]))
            else:
                for mask, sh in ((L, False), (S, True)):
                    i = np.flatnonzero(mask)
                    if len(i) < half: continue
                    o = np.argsort(key[i] if key is not None
                                   else (zv[i] if not sh else -zv[i]))
                    for j in i[o][:half]: picks.append((sh, fw[j], dn[j], up[j]))
            continue
        sg = Z[a.signal][t]
        ok = base & np.isfinite(sg)
        i = np.flatnonzero(ok)
        if a.mode == "short":
            if len(i) < c.slots: continue
            for j in i[np.argsort(-sg[i])][:c.slots]:
                picks.append((True, fw[j], dn[j], up[j]))
        else:
            if len(i) < c.slots: continue
            o = i[np.argsort(sg[i])]
            for j in o[:half]: picks.append((False, fw[j], dn[j], up[j]))
            for j in o[-half:]: picks.append((True, fw[j], dn[j], up[j]))
    P = np.array(picks, dtype=np.float64)
    sh, fw, dn, up = P[:,0].astype(bool), P[:,1], P[:,2], P[:,3]
    print(f"\n■ 손절 상한 검정 — 신호 {a.signal} · {a.mode} · 슬롯 {c.slots} · "
          f"보유 {c.hold}분 · 거래 {len(P):,}")
    print(f"  {'손절':>6}{'거래당%':>10}{'승률':>7}{'최악%':>9}{'하위1%':>9}"
          f"{'손절발동':>9}{'복리%':>10}{'최대낙폭%':>10}")
    for s_ in [float(x) for x in a.stops.split(",")]:
        if s_ <= 0:
            net = np.where(sh, -fw, fw) - c.fee_rt
            hit = 0
        else:
            # 롱: 보유 중 최저가 -s 이하면 발동 · 숏: 보유 중 최고가 +s 이상
            trig = np.where(sh, up >= s_, dn <= -s_)
            raw = np.where(sh, -fw, fw)
            net = np.where(trig, -s_, raw) - c.fee_rt
            hit = int(trig.sum())
        e = np.cumprod(1 + net/c.slots/100)
        mdd = 100*(1 - (e/np.maximum.accumulate(e)).min())
        print(f"  {('없음' if s_<=0 else f'{s_:.0f}%'):>6}{net.mean():>+10.4f}"
              f"{100*(net>0).mean():>6.0f}%{net.min():>+9.2f}"
              f"{np.percentile(net,1):>+9.2f}{100*hit/len(net):>8.1f}%"
              f"{100*(e[-1]-1):>+10.2f}{mdd:>10.2f}")
    log.info("완료 %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
