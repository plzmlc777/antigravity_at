"""살아남은 축을 깊이 판다 — 충격 되돌림 × 긴 보유.

## 왜 (2026-08-31 새벽)

2년 격자에서 **진입 지연이 축을 둘로 갈랐다**:

    충격1봉 × 보유 1~4h   지연 5분에 스프레드 -50~67%   → **호가 튐**
    충격3봉 × 보유 24h    지연 10분에도 -13%             → 튐 아님
    되돌림24h × 보유 12h  지연 5분에 -8%                 → 튐 아님

틱 4.3일에서는 보유 24시간 칸의 비겹침 표본이 4개라 **볼 수가 없었다**.
2년이면 753개다.

## 무엇을 확인하나

    ① 지연 격자를 더 깊게 (0~12봉 = 0~60분)   튐이면 계속 무너진다
    ② 롱 다리 · 숏 다리 분리                  한쪽만 벌면 표류다
    ③ 전반 · 후반                             감쇠 여부
    ④ 사건 집중도                             상위 시각 빼면 남나
    ⑤ 슬롯 실현 총손익                        실제로 얼마인가
    ⑥ 종목별 분포                             몇 종목이 다 벌었나

⚠ 롱·숏 각 다리는 **자기 방향 위약**과 비교해야 한다(교훈#91·101).
  전체 시장이 오르면 롱 다리는 그냥 벌고, 그건 신호가 아니다.

사용:
  python3 -m scripts.research.shock_deep --smoke 60
  python3 -m scripts.research.shock_deep --reps 500
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
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("shock")

BAR, ANCH, Q = 5, 12, 0.2
FEE1, FEE2 = 0.036, 0.072      # 한 다리 / 두 다리
# 살아남은 후보 — (신호이름, 되돌아보는 봉수)
SIGS = {"충격3봉": 3, "충격6봉": 6, "충격12봉": 12, "되돌림24h": 288}
# ⚠ 12시간 이하는 **호가 튐**으로 확정됐다 — 지연 1봉에 부호까지 뒤집힌다
#   (충격3봉 보유12h: 100 → -84 → -112 → -218). 그런 칸을 격자에 남기면
#   귀무만 부풀고 검정력이 죽는다(교훈#95·108의 같은 실패).
HOLDS_H = (24, 48)
# ⚠ 지연은 **자유 모수가 아니라 강건성 점검**이다. 판정 격자에는 실행 가능한
#   1봉(5분)만 넣고, 나머지는 감쇠표로만 본다.
DELAYS = (0, 1, 2, 3, 6, 12)   # 0~60분
JUDGE_DELAYS = (1,)            # 위약 격자에 들어가는 것


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20
    min_times: int = 30
    min_bars_in_5: float = 3.0
    reps: int = 500
    seed: int = 20260831


def load(files):
    cl, nb = {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0), idx)


def masks(X, pos, cfg):
    x = X[pos]
    cnt = np.isfinite(x).sum(1)
    good = cnt >= cfg.min_syms
    if not good.any():
        return None
    x = x[good]
    with np.errstate(invalid="ignore"):
        qs = np.nanquantile(x, [Q, 1 - Q], axis=1)
    ok = qs[1] > qs[0]
    x = x[ok]
    return (pos[good][ok], x >= qs[1][ok][:, None], x <= qs[0][ok][:, None])


def legs(rows, top, bot, R):
    """롱 다리·숏 다리를 **따로** 돌려준다. 한쪽만 벌면 표류다."""
    r = R[rows]
    with np.errstate(invalid="ignore"):
        L = np.nanmean(np.where(top, r, np.nan), axis=1)     # 신호 상위 = 롱
        S = np.nanmean(np.where(bot, r, np.nan), axis=1)     # 하위 = 숏
    m = np.isfinite(L) & np.isfinite(S)
    return L[m], S[m], rows[m]


def tstat(v):
    return (float(v.mean() / (v.std(ddof=1) / np.sqrt(len(v))))
            if len(v) > 2 and v.std(ddof=1) > 0 else np.nan)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    fs = sorted(CACHE.glob("*.parquet"))
    if a.smoke:
        fs = fs[:a.smoke]
    t0 = time.time()
    CL, NB, idx = load(fs)
    n = len(CL)
    log.info("판 %s봉 × %d종목 · %s ~ %s", f"{n:,}", CL.shape[1],
             idx.min().date(), idx.max().date())
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    X = {}
    for nm, k in SIGS.items():
        r = np.full(C.shape, np.nan, np.float32)
        r[k:] = (C[k:] / C[:-k] - 1.0) * 100.0
        X[nm] = np.where(live, -r, np.nan)          # 부호 뒤집어 큰 값 = 롱
    warm = max(SIGS.values()) + 12
    anc = np.arange(warm, n - max(HOLDS_H)*12 - max(DELAYS) - 1)
    anc = anc[anc % ANCH == 0]
    XA = {k: v[anc] for k, v in X.items()}
    del X
    RA = {}
    for h in HOLDS_H:
        k = h * 12
        for d in DELAYS:
            f = np.full(C.shape, np.nan, np.float32)
            hi_ = n - k - d
            f[:hi_] = (C[d+k:d+k+hi_] / C[d:d+hi_] - 1.0) * 100.0
            RA[(h, d)] = f[anc]
    na = len(anc)
    log.info("앵커 %s개 · %.1f분", f"{na:,}", (time.time()-t0)/60)

    rows = []
    MSK, LEG = {}, {}
    for h in HOLDS_H:
        pos = np.arange(0, na - h - max(DELAYS)//ANCH - 1, h)
        for nm in XA:
            mk = masks(XA[nm], pos, cfg)
            if mk is None or len(mk[0]) < cfg.min_times:
                continue
            MSK[(h, nm)] = mk
            for d in DELAYS:
                L, S, rw = legs(*mk, RA[(h, d)])
                if len(L) < cfg.min_times:
                    continue
                sp = L - S
                half = len(sp) // 2
                # ④ 사건 집중도 — |스프레드| 상위 5% 시각을 빼면 남나
                thr = np.quantile(np.abs(sp), 0.95)
                trim = sp[np.abs(sp) < thr]
                LEG[(h, d, nm)] = (L, S, rw)
                rows.append({
                    "보유h": h, "지연": d, "신호": nm, "시각수": len(sp),
                    "스프레드": sp.mean(), "수수료후": sp.mean() - FEE2,
                    "t": tstat(sp),
                    "롱": L.mean() - FEE1, "숏": -S.mean() - FEE1,
                    "t롱": tstat(L), "t숏": tstat(-S),
                    "전반": sp[:half].mean(), "후반": sp[half:].mean(),
                    "상위5%제외": trim.mean(), "t제외": tstat(trim)})
    R = pd.DataFrame(rows)
    keys = [(r.보유h, r.지연, r.신호) for r in R.itertuples()]
    print(f"\n■ 충격 되돌림 깊이 판독 (마찰 두다리 {FEE2}% · 한다리 {FEE1}%)")
    print(R.sort_values("수수료후", ascending=False).head(28).to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))

    print("\n■ 지연 감쇠 — 지연 0 대비 남은 비율(%). 튐이면 급락한다")
    piv = R.pivot_table(index=["신호", "보유h"], columns="지연", values="스프레드")
    rel = (piv.div(piv[0], axis=0) * 100.0)
    print(rel.to_string(float_format=lambda x: f"{x:.0f}"))

    # ── 회전 위약 최대통계량(수수료 후 기준) ──────────────
    rng = np.random.default_rng(cfg.seed)
    memmax = max(SIGS.values())//ANCH + max(HOLDS_H) + 2
    J = R[R.지연.isin(JUDGE_DELAYS)]
    jkeys = [(r.보유h, r.지연, r.신호) for r in J.itertuples()]
    obs = float(J.수수료후.max())
    obsL, obsS = float(J.롱.max()), float(J.숏.max())
    null = np.empty(cfg.reps)
    nullL = np.empty(cfg.reps); nullS = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(memmax, na - memmax))
        RR = {k: np.roll(v, sh, axis=0) for k, v in RA.items()}
        best, bl, bs = -9e9, -9e9, -9e9
        for (h, d, nm) in jkeys:
            L, S, _ = legs(*MSK[(h, nm)], RR[(h, d)])
            if len(L) >= cfg.min_times:
                best = max(best, float((L - S).mean()) - FEE2)
                # ⚠ 다리별 **자기 방향** 위약 (교훈#91·101). 시장이 표류하면
                #   한쪽 다리는 그냥 번다 — 그 몫을 빼야 신호 몫이 남는다.
                bl = max(bl, float(L.mean()) - FEE1)
                bs = max(bs, float(-S.mean()) - FEE1)
        null[i] = best; nullL[i] = bl; nullS[i] = bs
        if (i+1) % 50 == 0:
            log.info("위약 %d/%d · 귀무중앙 %.4f · %.1f분", i+1, cfg.reps,
                     float(np.median(null[:i+1])), (time.time()-t0)/60)
    pm = float((null >= obs).mean())
    pl = float((nullL >= obsL).mean()); ps = float((nullS >= obsS).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · **판정 격자 {len(jkeys)}칸** "
          f"· 지연 {JUDGE_DELAYS}봉)")
    print(f"  스프레드  관측 {obs:+.4f}% · 귀무 중앙 {np.median(null):+.4f}% "
          f"· 95분위 {np.quantile(null,.95):+.4f}%  **p = {pm:.3f}**")
    print(f"  롱 다리   관측 {obsL:+.4f}% · 귀무 중앙 {np.median(nullL):+.4f}% "
          f"· 95분위 {np.quantile(nullL,.95):+.4f}%  **p = {pl:.3f}**")
    print(f"  숏 다리   관측 {obsS:+.4f}% · 귀무 중앙 {np.median(nullS):+.4f}% "
          f"· 95분위 {np.quantile(nullS,.95):+.4f}%  **p = {ps:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "shock_deep.csv", index=False)
    (OUT / "shock_deep.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(keys),
         "p_long": pl, "p_short": ps, "obs_long": obsL, "obs_short": obsS,
         "anchors": int(na), "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
