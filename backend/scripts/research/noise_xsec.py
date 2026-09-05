"""잡음 선별 **횡단면** 검정 — 아카이브 미시구조 여러 달치로.

## 왜 (2026-09-02)

`잡음6`은 **521종목 중 잡음 상위 3+3**을 고른다. 그런데 판정 근거가
**틱 7일 · 날짜 3개**뿐이었다. 아카이브로 미시구조를 몇 달치 만들었으니
같은 선별을 긴 구간에서 다시 잰다.

ZORA 단일 종목(403일)에서는 **잡음이 역방향**이었다 — 자기 과거 대비
상위 10% 가 -0.341%/건, 하위가 +0.013%/건, 무작위 대비 p 0.908.
여기서는 **횡단면 순위**로 다시 묻는다(단일 종목 순위와 다른 것이다).

⚠ 대조군 셋을 반드시 같이 낸다.
   ① 무작위 3+3     — 선별이 아무거나 고르는 것을 이기나
   ② 잡음 **하위**  — 거울에서 부호가 반대여야 진짜다(교훈#91)
   ③ 구간 3분할     — 한 구간이 전부를 만들었나(2026-09-02 실측: 자유배분
                      이득 +0.158%p 가 3구간 중 1구간에서 전부 나왔다)
⚠ **비겹침 진입**만. 겹치면 표본이 부풀고 t 가 가짜가 된다.
⚠ 앵커마다 **살아 있는 종목만** 후보다. 상장 전 종목이 섞이면 조용히 틀린다.

사용:
  python3 -m scripts.research.noise_xsec --reps 500
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

log = logging.getLogger("noise_xsec")
ROOT = Path(__file__).resolve().parents[2]
MICRO = ROOT / "runs" / "micro1m"
OUT = ROOT / "runs" / "research_track" / "noise_xsec"


@dataclass(frozen=True)
class Cfg:
    win_h: int = 60
    window: int = 360
    delta: int = 180
    z_lo: float = -1.25
    z_hi: float = -0.25
    acc_max: float = 0.5
    min_live: float = 5.0
    fee_rt: float = 0.072      # 왕복
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
    cl = g.cl.ffill()
    n = len(cl)
    if n < c.win_h + c.window + 2*c.delta + c.hold + 100:
        return None
    cc = cl.to_numpy(float)
    fw = np.full(n, np.nan)
    fw[:n-c.win_h] = cc[c.win_h:]/cc[:n-c.win_h] - 1.0
    win = pd.Series(np.where(np.isfinite(fw), (fw > 0).astype(float), np.nan))
    # ⚠ shift(win_h) — 승부가 끝난 앵커만. 빼먹으면 미래참조다.
    rate = win.rolling(c.window, min_periods=c.window//2).mean().shift(c.win_h)
    vel = rate - rate.shift(c.delta)
    acc = vel - vel.shift(c.delta)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_*(1-p_)/max(c.window/c.win_h, 1.0))
    n60 = g.ntr.rolling(c.noise_win).sum().to_numpy()
    f60 = g.flip.rolling(c.noise_win).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        bump = np.where(n60 > 0, f60/n60, np.nan)
        dm = g.dtm.rolling(c.noise_win).mean().to_numpy()
        ds = g.dts.rolling(c.noise_win).mean().to_numpy()
        irr = np.where(dm > 0, ds/dm, np.nan)
    fwd = np.full(n, np.nan)
    fwd[:n-c.hold] = (cc[c.hold:]/cc[:n-c.hold] - 1.0)*100.0
    return pd.DataFrame(
        {"zv": (vel/(se*np.sqrt(2))).to_numpy(),
         "za": (acc/(se*2.0)).to_numpy(),
         "live": g.ntr.rolling(60).median().shift(1).to_numpy(),
         "bump": bump, "irr": irr, "fwd": fwd}, index=cl.index)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=500)
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    c = Cfg()
    log.info("설정 전문:\n%s", c.dump())
    rng = np.random.default_rng(20260902)

    fs = sorted(MICRO.glob("*.parquet"))
    if a.limit:
        fs = fs[:a.limit]
    log.info("종목 파일 %d", len(fs))
    t0 = time.time()
    F, names = {}, []
    for i, f in enumerate(fs, 1):
        try:
            r = feats(f, c)
        except Exception as e:                                 # noqa: BLE001
            log.warning("%s 실패 %s", f.stem, e); r = None
        if r is not None:
            F[f.stem] = r; names.append(f.stem)
        if i % 10 == 0:
            log.info("[%d/%d] %.1f분", i, len(fs), (time.time()-t0)/60)
    if len(F) < 10:
        raise SystemExit(f"종목 {len(F)}개 — 횡단면이 안 된다")

    lo = min(x.index.min() for x in F.values())
    hi = max(x.index.max() for x in F.values())
    grid = pd.date_range(lo, hi, freq=f"{c.hold}min", tz="UTC")   # 비겹침 앵커
    K = ("zv","za","live","bump","irr","fwd")
    Z = {k: np.full((len(grid), len(names)), np.nan, dtype=np.float32) for k in K}
    for j, s in enumerate(names):
        r = F[s].reindex(grid)
        for k in K:
            Z[k][:, j] = r[k].to_numpy(np.float32)
    del F
    log.info("앵커 %d (%d분) · 종목 %d · %s ~ %s", len(grid), c.hold,
             len(names), grid[0], grid[-1])

    def cands(t):
        zv, za, lv = Z["zv"][t], Z["za"][t], Z["live"][t]
        bp, ir, fw = Z["bump"][t], Z["irr"][t], Z["fwd"][t]
        ok = (np.isfinite(zv) & np.isfinite(za) & np.isfinite(lv)
              & np.isfinite(bp) & np.isfinite(ir) & np.isfinite(fw)
              & (lv >= c.min_live))
        L = ok & (zv >= c.z_lo) & (zv <= c.z_hi) & (za < c.acc_max)
        S = ok & (zv >= -c.z_hi) & (zv <= -c.z_lo) & (za > -c.acc_max)
        if not (L.any() or S.any()):
            return None
        pool = L | S
        rb = pd.Series(np.where(pool, bp, np.nan)).rank(pct=True).to_numpy()
        ri = pd.Series(np.where(pool, ir, np.nan)).rank(pct=True).to_numpy()
        return L, S, rb + ri, fw

    half = c.slots // 2
    modes = ["잡음상위", "잡음하위", "자유6상위", "무작위"]
    res = {m: [] for m in modes}
    per = {m: [] for m in modes}      # (앵커번호, 순수익) — 구간 분할용
    nrand = 0
    for t in range(len(grid)):
        r = cands(t)
        if r is None:
            continue
        L, S, sc, fw = r
        def take(mask, k, top=True):
            i = np.flatnonzero(mask)
            if len(i) < k:
                return []
            o = np.argsort(-sc[i] if top else sc[i])
            return list(i[o][:k])
        def net(idx, short):
            return [(-fw[j] if short else fw[j]) - c.fee_rt for j in idx]
        for m, sel in (
            ("잡음상위", net(take(L, half), False) + net(take(S, half), True)),
            ("잡음하위", net(take(L, half, False), False)
                       + net(take(S, half, False), True)),
        ):
            res[m].extend(sel); per[m].extend([(t, x) for x in sel])
        pool = L | S
        i6 = take(pool, c.slots)
        v6 = [(-fw[j] if S[j] else fw[j]) - c.fee_rt for j in i6]
        res["자유6상위"].extend(v6); per["자유6상위"].extend([(t, x) for x in v6])
        # 무작위 — 같은 다리·같은 개수
        for _ in range(1):
            il = np.flatnonzero(L); is_ = np.flatnonzero(S)
            if len(il) >= half and len(is_) >= half:
                j1 = rng.choice(il, half, replace=False)
                j2 = rng.choice(is_, half, replace=False)
                v = net(j1, False) + net(j2, True)
                res["무작위"].extend(v); per["무작위"].extend([(t, x) for x in v])
                nrand += 1

    print(f"\n■ 잡음 횡단면 — 종목 {len(names)} · 앵커 {len(grid):,} · "
          f"보유 {c.hold}분 · 왕복 {c.fee_rt}%")
    print(f"  {'판본':<10}{'거래':>8}{'거래당%':>10}{'승률':>7}{'표준편차':>9}")
    for m in modes:
        x = np.array(res[m])
        if not len(x): continue
        print(f"  {m:<10}{len(x):>8,}{x.mean():>+10.4f}"
              f"{100*(x>0).mean():>6.0f}%{x.std(ddof=1):>9.3f}")

    # ── 무작위 위약을 여러 판 — 상위 선별이 우연을 이기나 ──
    obs = np.mean(res["잡음상위"]) if res["잡음상위"] else np.nan
    draws = []
    for _ in range(a.reps):
        v = []
        for t in range(len(grid)):
            r = cands(t)
            if r is None: continue
            L, S, sc, fw = r
            il, is_ = np.flatnonzero(L), np.flatnonzero(S)
            if len(il) < half or len(is_) < half: continue
            j1 = rng.choice(il, half, replace=False)
            j2 = rng.choice(is_, half, replace=False)
            v += [fw[j]-c.fee_rt for j in j1] + [-fw[j]-c.fee_rt for j in j2]
        if v: draws.append(float(np.mean(v)))
    draws = np.array(draws)
    print(f"\n■ 무작위 위약 {len(draws)}판 — 잡음 상위가 우연을 이기나")
    print(f"  관측 **{obs:+.4f}%** · 위약 중앙 {np.median(draws):+.4f}% "
          f"· 95분위 {np.percentile(draws,95):+.4f}% · **p = {(draws>=obs).mean():.3f}**")

    # ── 구간 3분할 ─────────────────────────────────────
    print(f"\n■ 구간 3분할 — 한 구간이 전부를 만들었나")
    print(f"  {'구간':<24}{'잡음상위':>10}{'잡음하위':>10}{'무작위':>10}")
    q = len(grid)//3
    for w in range(3):
        a0, a1 = w*q, (w+1)*q if w < 2 else len(grid)
        row = []
        for m in ("잡음상위","잡음하위","무작위"):
            v = [x for tt, x in per[m] if a0 <= tt < a1]
            row.append(np.mean(v) if v else np.nan)
        print(f"  {str(grid[a0])[:10]}~{str(grid[min(a1,len(grid)-1)])[:10]:<12}"
              + "".join(f"{x:>+10.4f}" for x in row))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"cfg.json").write_text(c.dump())
    log.info("완료 %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
