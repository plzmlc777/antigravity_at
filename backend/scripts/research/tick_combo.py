"""보조지표 **조합** — 틱에서 전수 탐색. 단독은 이미 닫혔다.

## 왜 (2026-09-01, 대표님 지시)

"보조지표 단독 말고 **다양한 조합으로** 틱 데이터를 테스트하라."

앞선 시너지 격자(732칸)에서 나온 것:
  · z_vel 과 결합하면 지표 단독보다 **일관되게 나쁘다** — z_vel 은 방해다
  · 지표 단독 상위(atr·ema_sl·flip·irr)는 이미 2년·4년에서 닫힌 축이다
  · 보유를 6종으로 채우니 최대통계량 p 가 0.000 → **0.135** 로 무너졌다(교훈#117)

그러면 남은 질문은 **지표끼리의 조합**이다. 하나로는 안 되는데 둘·셋을 겹치면
되는가.

## 격자 — 먼저 선언하고 좁히지 않는다 (교훈#117)

    단독      12지표 × 2방향                    =    24
    2개 조합  C(12,2)=66 × 4 부호조합           =   264
    3개 조합  C(12,3)=220 × 8 부호조합          = 1,760
              × 보유 2종(120·240분) · 종목 3    = **4,096칸**

조합은 **행 안 백분위의 합**으로 만든다. 지표마다 눈금이 달라 원값을 못 더한다.
부호조합을 전부 넣는 이유는 어느 방향으로 쓸지를 **결과 보고 고르지 않기**
위해서다(교훈#91).

⚠ 표본 — 틱 6~7일. 독립 단위는 날짜 6~7개(교훈#112). **선별이지 판정이 아니다.**
⚠ 상위/하위 마스킹 분리(교훈#116) · 블록 수 표기 · 보유별 기준선.
⚠ p 는 **칸 수·귀무 95분위와 함께** 읽는다(교훈#117).

사용:
  python3 -m scripts.research.tick_combo --smoke
  python3 -m scripts.research.tick_combo --reps 200
"""
from __future__ import annotations

import argparse
import itertools
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.tick_synergy import (IND, Cfg, build_all,   # noqa: E402
                                           rank_rows)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "tick_combo_2026_09_01"
log = logging.getLogger("combo")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reps", type=int, default=200)
    p.add_argument("--holds", default="24,48")
    p.add_argument("--pick", type=int, default=3)
    p.add_argument("--max-k", type=int, default=3, help="조합 최대 개수")
    p.add_argument("--smoke", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    holds = [int(x) for x in a.holds.split(",")]
    reps, maxk = (10, 2) if a.smoke else (a.reps, a.max_k)
    if a.smoke:
        holds = holds[:1]
    cfg = Cfg()
    t0 = time.time()
    S, ZV, ZA, live, C, idx, syms, F = build_all(cfg)
    n, m = C.shape
    OKL = ((ZV >= cfg.z_lo) & (ZV <= cfg.z_hi) & (ZA < cfg.acc_max) & live
           & np.isfinite(ZV))
    OKS = ((ZV >= -cfg.z_hi) & (ZV <= -cfg.z_lo) & (ZA > -cfg.acc_max) & live
           & np.isfinite(ZV))
    warm = cfg.win_h + cfg.window + 2*cfg.delta
    rng = np.random.default_rng(cfg.seed)
    rows, best = [], np.full(reps, -9e9)

    # 조합 목록을 **미리 다 만든다** — 결과를 보고 더하거나 빼지 않는다
    combos = []
    for k in range(1, maxk+1):
        for names in itertools.combinations(IND, k):
            for sg in itertools.product((1, -1), repeat=k):
                combos.append((names, sg))
    log.info("조합 %s개 × 보유 %d종 = %s칸 · %.1f분", f"{len(combos):,}",
             len(holds), f"{len(combos)*len(holds):,}", (time.time()-t0)/60)

    for H in holds:
        hi_ = n - H
        R = np.full(C.shape, np.nan, np.float32)
        R[:hi_] = (C[H:H+hi_]/C[:hi_] - 1.0)*100.0
        base = np.arange(warm, n - H - 1)
        Ra, L0, S0 = R[base], OKL[base], OKS[base]
        nb_ = len(base)
        day = pd.Series(pd.DatetimeIndex(idx[base]).date).to_numpy()
        blocks = []
        for ph in range(H):
            kk = np.arange(ph, nb_ - H - 1, H)
            kk = kk[(L0[kk].sum(1) >= cfg.min_side) & (S0[kk].sum(1) >= cfg.min_side)]
            if len(kk):
                blocks.append(kk)
        allk = np.concatenate(blocks) if blocks else np.array([], int)
        dayk = day[allk]
        # 지표 백분위를 **한 번만** 만들어 조합에서 재사용한다
        RK = {}
        for nm in IND:
            v = S[nm][base]
            RK[nm] = (rank_rows(v, L0), rank_rows(v, S0))
        RZ = (rank_rows(-ZV[base], L0), rank_rows(ZV[base], S0))
        log.info("보유 %d분 · 앵커 %s · 날짜 %d · 백분위 준비 · %.1f분",
                 H*5, f"{len(allk):,}", len(set(dayk)), (time.time()-t0)/60)

        def picks(sl, ss):
            o = []
            for sc, ok in ((sl, L0), (ss, S0)):
                v = np.where(ok & np.isfinite(sc), sc, -np.inf)
                o.append(np.argsort(-v, axis=1)[:, :a.pick].astype(np.int32))
            return o

        def stat(li, si, Rm):
            with np.errstate(invalid="ignore"):
                l_ = np.nanmean(np.take_along_axis(Rm, li, 1), 1)
                s_ = np.nanmean(np.take_along_axis(Rm, si, 1), 1)
            return (l_ - s_)/2.0 - cfg.fee_rt

        cells = []
        rr = rng.random(L0.shape).astype(np.float32)
        cells.append((("무작위",), (0,), *picks(rr, rr.copy())))
        cells.append((("z_vel",), (0,), *picks(RZ[0], RZ[1])))
        for names, sg in combos:
            sl = sum(s_*RK[nm][0] for nm, s_ in zip(names, sg))
            ss = sum(s_*RK[nm][1] for nm, s_ in zip(names, sg))
            cells.append((names, sg, *picks(sl, ss)))
        log.info("  칸 %s 준비 · %.1f분", f"{len(cells):,}", (time.time()-t0)/60)

        for names, sg, li, si in cells:
            v = stat(li, si, Ra)[allk]
            d_ = pd.Series(v, index=dayk).dropna()
            if len(d_) < 50:
                continue
            dd = d_.groupby(level=0).mean()
            mn, sdv = float(dd.mean()), float(dd.std(ddof=1))
            rows.append({"보유분": H*5, "k": len(names) if names[0] not in
                         ("무작위", "z_vel") else 0,
                         "조합": "+".join(f"{'-' if s_ < 0 else ''}{nm}"
                                         for nm, s_ in zip(names, sg))
                         if names[0] not in ("무작위", "z_vel") else names[0],
                         "앵커": int(len(d_)), "날짜": len(dd),
                         "거래당": float(d_.mean()), "일평균": mn,
                         "날짜t": mn/(sdv/np.sqrt(len(dd))) if len(dd) > 2 else np.nan,
                         "양수일": f"{int((dd>0).sum())}/{len(dd)}"})
        # 회전 위약 최대통계량 — 격자 전체
        lo_s = max(warm, H) + 10
        for rep in range(reps):
            sh = int(rng.integers(lo_s, nb_ - lo_s))
            Rs = Ra[(np.arange(nb_) - sh) % nb_]
            mx = -9e9
            for names, sg, li, si in cells:
                if names[0] == "무작위":
                    continue
                v = stat(li, si, Rs)[allk]
                v = v[np.isfinite(v)]
                if len(v):
                    mx = max(mx, float(v.mean()))
            best[rep] = max(best[rep], mx)
            if (rep+1) % 25 == 0:
                log.info("    위약 %d/%d · %.1f분", rep+1, reps,
                         (time.time()-t0)/60)
        del R, Ra, cells
    T = pd.DataFrame(rows)
    zb = T[T.조합 == "z_vel"].set_index("보유분").일평균.to_dict()
    T["z대비"] = T.일평균 - T.보유분.map(zb)
    print(f"\n■ 지표 조합 — 틱 {m}종목 · 칸 {len(T):,} · 왕복 {cfg.fee_rt}%")
    print("  기준선  " + " · ".join(
        f"{k}분 z_vel {v:+.4f}" for k, v in sorted(zb.items())))
    for k in sorted(x for x in T.k.unique() if x > 0):
        sub = T[T.k == k].sort_values("일평균", ascending=False).head(8)
        print(f"\n  [{k}개 조합] 상위 8")
        print(sub[["보유분", "조합", "날짜", "거래당", "일평균", "날짜t",
                   "양수일", "z대비"]].to_string(
            index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(T[T.조합 != "무작위"].일평균.max())
    bb = best[np.isfinite(best) & (best > -8e9)]
    pm = float((bb >= obs).mean()) if len(bb) else np.nan
    print(f"\n■ 회전 위약 최대통계량")
    print(f"  칸 {len(T):,} · 위약 {len(bb)}회 · 관측 최대 {obs:+.4f}%/일")
    print(f"  귀무 중앙 {np.median(bb):+.4f} · **95분위 {np.quantile(bb,.95):+.4f}** "
          f"· **p = {pm:.3f}**")
    print("\n  k별 최고 (조합이 단독을 이기는가)")
    for k in sorted(T.k.unique()):
        sub = T[T.k == k]
        lab = {0: "기준선", 1: "단독", 2: "2개", 3: "3개"}.get(k, str(k))
        print(f"    {lab:6s} 최고 {sub.일평균.max():+.4f} · "
              f"중앙 {sub.일평균.median():+.4f} · 칸 {len(sub):,}")
    OUT.mkdir(parents=True, exist_ok=True)
    T.to_csv(OUT / "combo.csv", index=False)
    log.info("저장 %s · %.1f분", OUT, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
