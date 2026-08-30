"""지속성 게이트를 깊이 판다 — 오늘 밤 유일하게 위약을 뚫은 것.

## 무엇이 나왔나 (2026-08-31 02:20)

    k8차 +0.3445  위약중앙 -0.0127  위약95 +0.1905   p 0.003
    최대통계량(14항목 보정)                           **p 0.023**

최근 8블록(8일) 평균이 양수면 다음 블록 +0.2324%, 음수면 -0.1121%.
게이트 단리합 +91.55% 대 항상거래 +50.37%.

## 조심할 이유

`build_regime_baseline` 주석에 이미 있다 — "전략 자신의 과거 성과로 스위치 →
위약 p 0.112, **항상거래보다 낮음**". 다른 전략에서 한 번 죽은 형태다.
그리고 전체 평균은 위약을 못 뚫었는데(p 0.369) 조건부만 뚫었다.

## 확인 네 가지

    ① 전반·후반      한쪽에서만 나오면 잡음이다
    ② 여유 한 칸     블록 i 청산과 i+1 진입이 **정확히 맞닿아** 있다.
                     한 블록 더 띄워도 남나 (shift 2)
    ③ 다른 신호      엣지의 일반 성질이면 되돌림24h·충격72봉 에서도 나와야
    ④ 집중도         상위 5% 블록 빼면 남나

⚠ 격자(신호 3 × k 6 × 여유 2)를 뒤지므로 **최대통계량**(교훈#95).

사용:
  python3 -m scripts.research.persist_deep --smoke 80 --reps 30
  python3 -m scripts.research.persist_deep --reps 1000
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("pdeep")

BAR, ANCH, Q = 5, 12, 0.2
FEE2 = 0.072
SIGS = {"충격12봉": 12, "충격72봉": 72, "되돌림24h": 288}
HOLD_H, DELAY = 24, 1
KS = (2, 3, 5, 8, 13)
LAGSHIFT = (1, 2)              # 게이트가 보는 과거의 여유(블록)


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20
    min_bars_in_5: float = 3.0
    min_per_side: int = 40
    reps: int = 1_000
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


def funding_cum(syms, idx):
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
             "ORDER BY funding_time")
    a = idx.min().tz_convert(None); b = idx.max().tz_convert(None)
    cum = np.zeros((len(idx), len(syms)), np.float32)
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c.execute(q, {"s": s, "a": a, "b": b}).all()
            if not r:
                continue
            t = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r], np.float64) * 100.0
            pos = np.clip(idx.searchsorted(t, side="left"), 0, len(idx)-1)
            acc = np.zeros(len(idx)); np.add.at(acc, pos, v)
            cum[:, j] = np.cumsum(acc).astype(np.float32)
    return cum


def gate_stats(x: np.ndarray, k: int, lag: int, cfg: Cfg):
    """최근 k 블록 평균의 부호로 가른다. `lag` 은 여유(블록)."""
    prev = pd.Series(x).rolling(k).mean().shift(lag).to_numpy()
    m = np.isfinite(prev)
    pos, neg = m & (prev > 0), m & (prev <= 0)
    if pos.sum() < cfg.min_per_side or neg.sum() < cfg.min_per_side:
        return None
    return (float(x[pos].mean() - x[neg].mean()), float(x[pos].mean()),
            float(x[neg].mean()), float(x[pos].sum()), int(pos.sum()), pos)


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
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    k_, d = HOLD_H * 12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - k_ - d
    R[:hi_] = ((C[d+k_:d+k_+hi_] / C[d:d+hi_] - 1.0) * 100.0
               - (CUM[d+k_:d+k_+hi_] - CUM[d:d+hi_]))
    MK, SER = {}, {}
    for nm, sb in SIGS.items():
        r = np.full(C.shape, np.nan, np.float32)
        r[sb:] = (C[sb:] / C[:-sb] - 1.0) * 100.0
        X = np.where(live, -r, np.nan)
        warm = max(SIGS.values()) + 12
        anc = np.arange(warm, n - k_ - d - 1)
        anc = anc[anc % ANCH == 0]
        XA = X[anc]
        pos = np.arange(0, len(anc) - HOLD_H - 1, HOLD_H)
        x = XA[pos]
        good = np.isfinite(x).sum(1) >= cfg.min_syms
        x = x[good]
        with np.errstate(invalid="ignore"):
            qs = np.nanquantile(x, [Q, 1-Q], axis=1)
        ok = qs[1] > qs[0]
        x = x[ok]
        MK[nm] = (pos[good][ok], x >= qs[1][ok][:, None], x <= qs[0][ok][:, None])
        SER[nm] = anc
    RA = {nm: R[SER[nm]] for nm in SIGS}
    log.info("판 %s봉 × %d종목 · 블록 %d개 · %.1f분", f"{n:,}", len(syms),
             len(MK['충격12봉'][0]), (time.time()-t0)/60)

    def ser(nm, Rm):
        rows, top, bot = MK[nm]
        r = Rm[rows]
        with np.errstate(invalid="ignore"):
            v = (np.nanmean(np.where(top, r, np.nan), axis=1)
                 - np.nanmean(np.where(bot, r, np.nan), axis=1)) - FEE2
        return v[np.isfinite(v)]

    rows, keys = [], []
    for nm in SIGS:
        x = ser(nm, RA[nm])
        h = len(x) // 2
        for k in KS:
            for lg in LAGSHIFT:
                g = gate_stats(x, k, lg, cfg)
                if g is None:
                    continue
                diff, mp, mn, tot, npos, mask = g
                g1 = gate_stats(x[:h], k, lg, cfg)
                g2 = gate_stats(x[h:], k, lg, cfg)
                thr = np.quantile(np.abs(x), 0.95)
                xt = x.copy(); keep = np.abs(x) < thr
                gt = gate_stats(xt[keep], k, lg, cfg)
                rows.append({
                    "신호": nm, "k": k, "여유": lg, "블록": len(x),
                    "양수후": mp, "음수후": mn, "차": diff,
                    "게이트합": tot, "항상합": float(x.sum()), "거래블록": npos,
                    "전반차": g1[0] if g1 else np.nan,
                    "후반차": g2[0] if g2 else np.nan,
                    "상위5%제외차": gt[0] if gt else np.nan})
                keys.append((nm, k, lg))
    R0 = pd.DataFrame(rows).sort_values("차", ascending=False)
    print(f"\n■ 지속성 게이트 (보유{HOLD_H}h · 지연{DELAY}봉 · 펀딩 포함 · 마찰 {FEE2}%)")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    na = len(SER["충격12봉"])
    mem = HOLD_H * 2 + max(SIGS.values())
    obs = float(R0.차.max())
    null = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(mem, na - mem))
        best = -9e9
        for nm in SIGS:
            xx = ser(nm, np.roll(RA[nm], sh, axis=0))
            for k in KS:
                for lg in LAGSHIFT:
                    g = gate_stats(xx, k, lg, cfg)
                    if g:
                        best = max(best, g[0])
        null[i] = best
        if (i+1) % 100 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pm = float((null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(keys)}칸 "
          f"· 신호{len(SIGS)} × k{len(KS)} × 여유{len(LAGSHIFT)})")
    print(f"  관측 최대 차 {obs:+.4f}%p · 귀무 중앙 {np.median(null):+.4f}%p "
          f"· 95분위 {np.quantile(null,.95):+.4f}%p")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "persist_deep.csv", index=False)
    (OUT / "persist_deep.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(keys),
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
