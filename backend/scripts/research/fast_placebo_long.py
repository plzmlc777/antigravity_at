"""**5분 위약 가속도**를 4년으로 — 대표님이 제기한 가설의 판정.

## 착안 (2026-08-31, 대표님)

위약 승률은 **선도**를 본다. 그래서 지평마다 **정보가 도착하는 시각이 다르다** —
5분 위약은 t+5 면 확정되고 1시간 위약은 t+60 이 돼야 확정된다.
**빠른 지평은 55분 먼저 아는 정보**다.

틱 5일 실측: 5분 가속 단독이 60분 가속보다 강했다(차 +0.575 대 +0.202).
"빠름 − 느림" 형태는 오히려 약했다(+0.252) — 60분 가속이 잡음만 더한다.
그런데 12칸 보정하면 **p 0.303** 이라 판정이 안 됐다. 비겹침 표본이 28~116개.

## 그래서 격자를 **고정한 채** 4년으로 옮긴다

    되돌아보기  15 · 30 · 60 · 120분   (5분봉 3 · 6 · 12 · 24)
    예측 지평   60 · 120 · 240분       (12 · 24 · 48)
    = 12칸. 틱 검정과 **똑같다**. 새로 뒤지지 않는다 — 그래야 판정이 된다.

## 규약

⚠ 위약 승률을 **1봉 밀어** 확정된 것만 쓴다(안 밀면 미래참조)
⚠ 예측 지평만큼 띄워 뽑으면 **위상이 고정된다**(교훈#111) → 위상 전부 평균
⚠ 분위 마스크는 신호로 정해지므로 **한 번만** 만든다(위약 루프에서 재사용)
⚠ 회전 위약 최대통계량으로 12칸 보정(교훈#95)

사용:
  python3 -m scripts.research.fast_placebo_long --reps 500
  python3 -m scripts.research.fast_placebo_long --cache runs/bars5m_oos
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("fastpl")

BAR = 5
DELTAS = (3, 6, 12, 24)          # 15 · 30 · 60 · 120분
HS = (12, 24, 48)                # 60 · 120 · 240분


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 30
    min_per_bin: int = 25
    reps: int = 500
    seed: int = 20260831


def load(files):
    cl = {}
    for f in files:
        d = pd.read_parquet(f, columns=["ts", "c"])
        if len(d) < 5_000:
            continue
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32),
                               index=pd.to_datetime(d.ts, utc=True))
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return pd.DataFrame(cl).reindex(idx).ffill(), idx


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--limit-to", default="")
    p.add_argument("--merge", default="",
                   help="두 캐시를 합쳐 4년으로. 종목은 **교집합**만")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    t0 = time.time()
    if a.merge:
        A = {x.stem for x in (ROOT/a.cache).glob("*.parquet")}
        B = {x.stem for x in (ROOT/a.merge).glob("*.parquet")}
        common = sorted(A & B)
        parts = []
        for s in common:
            d = pd.concat([pd.read_parquet(ROOT/a.merge/f"{s}.parquet",
                                           columns=["ts", "c"]),
                           pd.read_parquet(ROOT/a.cache/f"{s}.parquet",
                                           columns=["ts", "c"])],
                          ignore_index=True).drop_duplicates("ts")
            d["sym"] = s
            parts.append(d)
        P = pd.concat(parts); del parts
        cl = {s: g.set_index(pd.to_datetime(g.ts, utc=True)).c.astype(np.float32)
              for s, g in P.groupby("sym")}
        del P
        idx = pd.date_range(min(v.index.min() for v in cl.values()),
                            max(v.index.max() for v in cl.values()),
                            freq=f"{BAR}min", tz="UTC")
        CL = pd.DataFrame(cl).reindex(idx).ffill(); del cl
    else:
        fs = sorted((ROOT/a.cache).glob("*.parquet"))
        if a.limit_to:
            keep = {x.stem for x in (ROOT/a.limit_to).glob("*.parquet")}
            fs = [x for x in fs if x.stem in keep]
        CL, idx = load(fs)
    n, ns = len(CL), CL.shape[1]
    log.info("판 %s봉(5분) × %d종목 · %s ~ %s · %.1f분", f"{n:,}", ns,
             idx.min().date(), idx.max().date(), (time.time()-t0)/60)

    # ── 5분 위약 승률 — **1봉 밀어** 확정된 것만
    fw = CL.shift(-1) / CL - 1.0
    cnt = fw.notna().sum(axis=1)
    W = ((fw > 0).sum(axis=1) / cnt.where(cnt >= cfg.min_syms) * 100.0).shift(1)
    mkt = (np.log(CL).diff().median(axis=1) * 100.0).to_numpy()
    log.info("위약 승률 — 평균 %.1f%% · 유효 %s봉", float(W.mean()),
             f"{int(W.notna().sum()):,}")

    # ── 가속도 + 분위 마스크(신호로만 정해지므로 한 번만)
    ACC = {}
    for d in DELTAS:
        v = W - W.shift(d)
        acc = v - v.shift(d)
        sd = acc.rolling(d*6, min_periods=d*2).std().shift(1)
        ACC[d] = (acc / (sd + 1e-9)).to_numpy()

    CELLS = [(d, h) for d in DELTAS for h in HS]
    MASK = {}
    for (d, h) in CELLS:
        s = ACC[d]
        per = []
        for ph in range(h):                       # ⚠ 위상 전부 (교훈#111)
            k = np.arange(ph, n - h, h)
            x = s[k]
            m = np.isfinite(x)
            if m.sum() < 3 * cfg.min_per_bin:
                continue
            xm = x[m]
            q1, q2 = np.quantile(xm, [1/3, 2/3])
            kk = k[m]
            per.append((kk[xm > q2], kk[xm < q1]))
        if per:
            MASK[(d, h)] = per

    def stat(mk, h, mkarr):
        """위상 평균의 (상위3분위 − 하위3분위) 이후 시장 수익."""
        fwd = pd.Series(mkarr).rolling(h).sum().shift(-h).to_numpy()
        out = []
        for hi_, lo_ in mk:
            a_, b_ = fwd[hi_], fwd[lo_]
            a_, b_ = a_[np.isfinite(a_)], b_[np.isfinite(b_)]
            if len(a_) < cfg.min_per_bin or len(b_) < cfg.min_per_bin:
                continue
            out.append(a_.mean() - b_.mean())
        return float(np.mean(out)) if out else np.nan

    rows = []
    for (d, h) in CELLS:
        if (d, h) not in MASK:
            continue
        rows.append({"되돌아보기": d*BAR, "예측지평": h*BAR,
                     "위상수": len(MASK[(d, h)]),
                     "상위-하위": stat(MASK[(d, h)], h, mkt)})
    R = pd.DataFrame(rows).sort_values("상위-하위", ascending=False)
    print(f"\n■ 5분 위약 가속도 → 이후 시장 (위상 평균 · 종목 {ns} · "
          f"{idx.min().date()} ~ {idx.max().date()})")
    print(R.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    obs = float(R["상위-하위"].max())
    null = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(max(HS)*4, n - max(HS)*4))
        mk2 = np.roll(mkt, sh)
        b = -9e9
        for (d, h) in MASK:
            v = stat(MASK[(d, h)], h, mk2)
            if np.isfinite(v):
                b = max(b, v)
        null[i] = b
        if (i+1) % 50 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pm = float((null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(MASK)}칸 · 위상 평균)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(null):+.4f}% "
          f"· 95분위 {np.quantile(null,.95):+.4f}%")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "4y" if a.merge else ("oos" if "oos" in a.cache else "is")
    R.to_csv(OUT / f"fast_placebo_{tag}.csv", index=False)
    (OUT / f"fast_placebo_{tag}.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(MASK),
         "symbols": int(ns), "bars": int(n),
         "null_median": float(np.median(null))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
