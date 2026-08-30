"""**어느 종목에서** 되는가 — 오늘 밤 한 번도 안 물은 축.

## 왜 (2026-08-31 새벽)

오늘 밤 모든 축이 "**언제** 되나"만 물었다(국면·시각·변동성·폭). 전부 닫혔다.
"**어느 종목에서** 되나"는 한 번도 안 물었다. 240종목은 유동성·변동성·나이·
혼잡도가 전부 다르다.

특히 직전에 나온 사실이 근거를 준다 — 급등 코인은 펀딩이 **더 음수**다.
음수 펀딩은 숏이 롱에게 낸다는 뜻이고, 즉 **급등을 되받아치는 자리가 붐빈다**.
평균 펀딩은 그래서 **혼잡도의 대리변수**다. 안 붐비는 종목에서는 되돌림이
남아 있을 수 있다.

## 설계

앵커마다 종목을 특성 **3분위**로 나누고, **각 분위 안에서** 되돌림 스프레드를
잰다. 분위마다 20종목 이상 남아야 횡단면이 성립한다(240 ÷ 3 = 80).

    거래활성30d   유동성 대리
    변동성30d     위험
    평균펀딩30d   **혼잡도** — 음수일수록 페이드가 붐빈다
    나이          상장 후 경과
    로그가격      코인 유형 대리

⚠ 특성은 전부 **앵커 이전 30일**로 만든다. 전 구간으로 분류하면 미래참조다
  (교훈#99 와 같은 자리 — 같은 기질에서 같은 시점으로 분류하라).
⚠ 회전 위약 최대통계량 — 특성 5 × 분위 3 × 신호 2 × 보유 2 = 60칸.
⚠ 수익률은 **펀딩 포함**(`r - f`). 다리 부호는 한 번만 뺀다.

사용:
  python3 -m scripts.research.xsec_symbol --smoke 80 --reps 30
  python3 -m scripts.research.xsec_symbol --reps 1000
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
log = logging.getLogger("xsym")

BAR, ANCH, Q = 5, 12, 0.2
FEE2 = 0.072
SIGS = {"충격12봉": 12, "되돌림24h": 288}
HOLDS_H = (24, 48)
DELAY = 1
NB_BINS = 3
D30 = 30 * 288                 # 30일 = 8,640봉


@dataclass(frozen=True)
class Cfg:
    min_syms_bin: int = 20     # 분위 안에 이만큼은 있어야 횡단면이 된다
    min_times: int = 30
    min_bars_in_5: float = 3.0
    reps: int = 1_000
    seed: int = 20260831


def load_bars(files):
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


def load_funding(syms, idx):
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
             "ORDER BY funding_time")
    a = idx.min().tz_convert(None); b = idx.max().tz_convert(None)
    cum = np.zeros((len(idx), len(syms)), np.float32)
    rate = np.zeros((len(idx), len(syms)), np.float32)
    have = 0
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c.execute(q, {"s": s, "a": a, "b": b}).all()
            if not r:
                continue
            have += 1
            t = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r], np.float64) * 100.0
            pos = np.clip(idx.searchsorted(t, side="left"), 0, len(idx)-1)
            acc = np.zeros(len(idx))
            np.add.at(acc, pos, v)
            cum[:, j] = np.cumsum(acc).astype(np.float32)
            rate[:, j] = acc.astype(np.float32)
    return cum, rate, have


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
    CL, NB, idx = load_bars(fs)
    syms = list(CL.columns); n = len(CL)
    CUM, RATE, nf = load_funding(syms, idx)
    log.info("판 %s봉 × %d종목 · 펀딩 %d종목 · %.1f분", f"{n:,}", len(syms), nf,
             (time.time()-t0)/60)

    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    lr = np.log(CL).diff()
    # ── 종목 특성: 전부 **앵커 이전 30일**. 전 구간 분류는 미래참조다
    CH = {
        "거래활성30d": NB.rolling(D30, min_periods=D30//4).mean().shift(1).to_numpy(),
        "변동성30d": (lr.rolling(D30, min_periods=D30//4).std()
                     * np.sqrt(288) * 100.0).shift(1).to_numpy(),
        "평균펀딩30d": pd.DataFrame(RATE).rolling(
            D30, min_periods=D30//4).sum().shift(1).to_numpy(),
        "나이": np.cumsum(np.isfinite(C), axis=0).astype(np.float32),
        "로그가격": np.log(np.where(C > 0, C, np.nan)),
    }
    CH = {k: np.where(live, v, np.nan) for k, v in CH.items()}
    X = {}
    for nm, k in SIGS.items():
        r = np.full(C.shape, np.nan, np.float32)
        r[k:] = (C[k:] / C[:-k] - 1.0) * 100.0
        X[nm] = np.where(live, -r, np.nan)
    warm = max(D30, max(SIGS.values()) + 12)
    anc = np.arange(warm, n - max(HOLDS_H)*12 - DELAY - 1)
    anc = anc[anc % ANCH == 0]
    if len(anc) < 200:
        raise SystemExit(f"앵커 {len(anc)}개뿐 — 30일 특성 워밍업이 자료를 다 먹었다")
    XA = {k: v[anc] for k, v in X.items()}
    CHA = {k: v[anc] for k, v in CH.items()}
    RA = {}
    for h in HOLDS_H:
        k, d = h*12, DELAY
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - k - d
        f[:hi_] = ((C[d+k:d+k+hi_] / C[d:d+hi_] - 1.0) * 100.0
                   - (CUM[d+k:d+k+hi_] - CUM[d:d+hi_]))   # ⚠ r - f 한 번만
        RA[h] = f[anc]
    del X, CH
    na = len(anc)
    log.info("앵커 %s개 · %.1f분", f"{na:,}", (time.time()-t0)/60)

    def build(sig, ch, b, pos):
        """특성 3분위 중 b번 칸 **안에서** 상·하위 신호 마스크."""
        x, c = XA[sig][pos], CHA[ch][pos]
        okc = np.isfinite(c)
        with np.errstate(invalid="ignore"):
            e1, e2 = np.nanquantile(np.where(okc, c, np.nan),
                                    [1/3, 2/3], axis=1)
        sel = okc & ((c <= e1[:, None]) if b == 0 else
                     (c > e2[:, None]) if b == 2 else
                     ((c > e1[:, None]) & (c <= e2[:, None])))
        xs = np.where(sel & np.isfinite(x), x, np.nan)
        cnt = np.isfinite(xs).sum(1)
        good = cnt >= cfg.min_syms_bin
        if not good.any():
            return None
        xs = xs[good]
        with np.errstate(invalid="ignore"):
            qs = np.nanquantile(xs, [Q, 1-Q], axis=1)
        ok = qs[1] > qs[0]
        xs = xs[ok]
        return (pos[good][ok], xs >= qs[1][ok][:, None], xs <= qs[0][ok][:, None])

    def spread(mk, R):
        rows, top, bot = mk
        r = R[rows]
        with np.errstate(invalid="ignore"):
            v = (np.nanmean(np.where(top, r, np.nan), axis=1)
                 - np.nanmean(np.where(bot, r, np.nan), axis=1))
        return v[np.isfinite(v)]

    rows, MSK, keys = [], {}, []
    for h in HOLDS_H:
        pos = np.arange(0, na - h - 1, h)
        for sig in XA:
            for ch in CHA:
                for b in range(NB_BINS):
                    mk = build(sig, ch, b, pos)
                    if mk is None or len(mk[0]) < cfg.min_times:
                        continue
                    v = spread(mk, RA[h])
                    if len(v) < cfg.min_times or v.std(ddof=1) <= 0:
                        continue
                    MSK[(h, sig, ch, b)] = mk
                    keys.append((h, sig, ch, b))
                    rows.append({
                        "보유h": h, "신호": sig, "특성": ch,
                        "분위": ["하", "중", "상"][b], "시각수": len(v),
                        "스프레드": v.mean(), "수수료후": v.mean() - FEE2,
                        "t": float(v.mean()/(v.std(ddof=1)/np.sqrt(len(v))))})
    R = pd.DataFrame(rows).sort_values("수수료후", ascending=False)
    print(f"\n■ 종목 특성별 되돌림 (펀딩 포함 · 마찰 {FEE2}% · 지연 {DELAY}봉)")
    print(R.head(24).to_string(index=False, float_format=lambda x: f"{x:+.4f}"))
    print("\n■ 특성 × 분위 요약 (수수료 후 평균, 보유·신호 통합)")
    print(R.pivot_table(index="특성", columns="분위", values="수수료후",
                        aggfunc="mean").reindex(columns=["하", "중", "상"])
          .to_string(float_format=lambda x: f"{x:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    mem = max(D30//ANCH, max(HOLDS_H)) + 2
    obs = float(R.수수료후.max())
    null = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(mem, na - mem))
        RR = {h: np.roll(RA[h], sh, axis=0) for h in HOLDS_H}
        best = -9e9
        for k in keys:
            v = spread(MSK[k], RR[k[0]])
            if len(v) >= cfg.min_times:
                best = max(best, float(v.mean()) - FEE2)
        null[i] = best
        if (i+1) % 100 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pm = float((null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(keys)}칸)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(null):+.4f}% "
          f"· 95분위 {np.quantile(null,.95):+.4f}%  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "xsec_symbol.csv", index=False)
    (OUT / "xsec_symbol.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(keys),
         "anchors": int(na), "null_median": float(np.median(null))},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
