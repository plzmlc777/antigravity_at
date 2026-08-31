"""**횡단면 위약 가속도** — 가속도를 순위 신호로 쓰는 건 처음이다.

## 어젯밤과 무엇이 다른가

    동결 규칙   지평 60분 · 창 360분 · **속도(z_vel)로 순위** · 가속도는 필터로만
    이번        **가속도(z_acc)로 순위** · 지평 5분도 함께

지평 5분은 t+5 면 확정된다(60분은 t+60). 대표님 착안 — 빠른 지평은 먼저 안다.
시장 전체 방향으로는 4년에서 죽었다(+0.0056%, p 0.260). 횡단면은 별개다.

## 격자 16칸 (고정 — 새로 뒤지지 않는다)

    신호       속도 · 가속도
    지평       1봉(5분) · 12봉(60분)
    창/간격    빠름(12/6) · 동결(72/36)
    보유       24봉(2시간) · 48봉(4시간)
    슬롯       10 고정 (어젯밤 최적점)

## 규약

⚠ 승률은 **지평만큼 밀어** 확정된 것만(안 밀면 미래참조)
⚠ 보유만큼 띄워 뽑으면 위상 고정 → **위상 전부 평균**(교훈#111)
⚠ 분위 마스크는 신호로만 정해지므로 한 번만 만든다
⚠ 진입 5분 지연 · 왕복 마찰 0.072% · 회전 위약 최대통계량

사용:
  python3 -m scripts.research.xsec_accel --reps 300
  python3 -m scripts.research.xsec_accel --merge runs/bars5m_oos --reps 300
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
log = logging.getLogger("xacc")

BAR, SLOT, DELAY, FEE1 = 5, 10, 1, 0.036
HORIZ = (1, 12)                  # 5분 · 60분
WINDELTA = ((12, 6), (72, 36))   # (창, 간격) — 빠름 · 동결
HOLDS = (24, 48)                 # 2시간 · 4시간
KINDS = ("속도", "가속도")


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 30
    min_anchors: int = 200
    reps: int = 300
    seed: int = 20260831


def build_panel(a):
    if a.merge:
        A = {x.stem for x in (ROOT/a.cache).glob("*.parquet")}
        B = {x.stem for x in (ROOT/a.merge).glob("*.parquet")}
        parts = []
        for s in sorted(A & B):
            d = pd.concat([pd.read_parquet(ROOT/a.merge/f"{s}.parquet",
                                           columns=["ts", "c", "n"]),
                           pd.read_parquet(ROOT/a.cache/f"{s}.parquet",
                                           columns=["ts", "c", "n"])],
                          ignore_index=True).drop_duplicates("ts")
            d["sym"] = s
            parts.append(d)
        P = pd.concat(parts); del parts
        cl = {s: g.set_index(pd.to_datetime(g.ts, utc=True)).c.astype(np.float32)
              for s, g in P.groupby("sym")}
        nb = {s: g.set_index(pd.to_datetime(g.ts, utc=True)).n.astype(np.float32)
              for s, g in P.groupby("sym")}
        del P
    else:
        cl, nb = {}, {}
        for f in sorted((ROOT/a.cache).glob("*.parquet")):
            d = pd.read_parquet(f, columns=["ts", "c", "n"])
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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--merge", default="")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    t0 = time.time()
    CL, NB, idx = build_panel(a)
    n, ns = len(CL), CL.shape[1]
    log.info("판 %s봉(5분) × %d종목 · %s ~ %s · %.1f분", f"{n:,}", ns,
             idx.min().date(), idx.max().date(), (time.time()-t0)/60)
    live = (NB.rolling(12).median().shift(1) >= 3.0).to_numpy()
    C = CL.to_numpy(np.float32)

    RET = {}
    for h in HOLDS:
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - h - DELAY
        f[:hi_] = (C[DELAY+h:DELAY+h+hi_] / C[DELAY:DELAY+hi_] - 1.0) * 100.0
        RET[h] = f
    del CL

    def signal(hz, W, D, kind):
        """지평 hz · 창 W · 간격 D 의 속도/가속도. **hz 만큼 밀어** 확정만."""
        fw = np.full(C.shape, np.nan, np.float32)
        fw[:n-hz] = C[hz:] / C[:n-hz] - 1.0
        win = pd.DataFrame(np.where(np.isfinite(fw), (fw > 0).astype(np.float32),
                                    np.nan))
        rate = win.rolling(W, min_periods=W//2).mean().shift(hz)
        vel = rate - rate.shift(D)
        s = vel if kind == "속도" else (vel - vel.shift(D))
        pr = rate.clip(0.01, 0.99)
        se = np.sqrt(pr*(1-pr) / max(W/hz, 1.0))
        z = (s / (se * (np.sqrt(2) if kind == "속도" else 2.0))).to_numpy()
        return np.where(live, z, np.nan)

    CELLS = [(k, hz, wd, h) for k in KINDS for hz in HORIZ
             for wd in WINDELTA for h in HOLDS]
    rng = np.random.default_rng(cfg.seed)
    shifts = rng.integers(max(HOLDS)*4, n - max(HOLDS)*4, size=cfg.reps)
    rows, best_null = [], np.full(cfg.reps, -9e9)
    for (kind, hz, (W, D), h) in CELLS:
        X = signal(hz, W, D, kind)
        obs_ph, msk = [], []
        for ph in range(h):                       # 위상 전부 (교훈#111)
            k = np.arange(ph, n - h - DELAY, h)
            x = X[k]
            cnt = np.isfinite(x).sum(1)
            good = cnt >= max(2*SLOT + 10, cfg.min_syms)
            if good.sum() < 5:
                continue
            kk, xx = k[good], x[good]
            top = np.argsort(np.where(np.isfinite(xx), xx, -np.inf),
                             axis=1)[:, -SLOT:]
            bot = np.argsort(np.where(np.isfinite(xx), xx, np.inf),
                             axis=1)[:, :SLOT]
            msk.append((kk, top, bot))
        if not msk or sum(len(m[0]) for m in msk) < cfg.min_anchors:
            continue

        def stat(Rm):
            out = []
            for kk, top, bot in msk:
                r = Rm[kk]
                a_ = np.take_along_axis(r, top, 1)
                b_ = np.take_along_axis(r, bot, 1)
                with np.errstate(invalid="ignore"):
                    v = np.nanmean(a_, 1) - np.nanmean(b_, 1)
                v = v[np.isfinite(v)]
                if len(v):
                    out.append(v.mean())
            return float(np.mean(out)) - 2*FEE1 if out else np.nan

        o = stat(RET[h])
        rows.append({"신호": kind, "지평분": hz*BAR, "창분": W*BAR,
                     "간격분": D*BAR, "보유분": h*BAR,
                     "앵커": sum(len(m[0]) for m in msk), "수수료후": o})
        for i, sh in enumerate(shifts):            # 칸별로 전 회차를 한 번에
            v = stat(np.roll(RET[h], int(sh), axis=0))
            if np.isfinite(v):
                best_null[i] = max(best_null[i], v)
        log.info("  %s · 지평%d · 창%d · 보유%d → %+.4f%% · %.1f분",
                 kind, hz*BAR, W*BAR, h*BAR, o, (time.time()-t0)/60)

    R = pd.DataFrame(rows).sort_values("수수료후", ascending=False)
    print(f"\n■ 횡단면 위약 가속도/속도 (슬롯{SLOT} · 지연 {DELAY*BAR}분 · "
          f"왕복 {2*FEE1}% · 위상 평균 · 종목 {ns})")
    print(R.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(R.수수료후.max())
    pm = float((best_null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(R)}칸)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best_null):+.4f}% "
          f"· 95분위 {np.quantile(best_null,.95):+.4f}%")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "4y" if a.merge else "2y"
    R.to_csv(OUT / f"xsec_accel_{tag}.csv", index=False)
    (OUT / f"xsec_accel_{tag}.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(R),
         "symbols": int(ns), "null_median": float(np.median(best_null))},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
