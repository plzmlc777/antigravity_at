"""번 구간은 **지속되는가** — 국면 질문의 가장 실용적인 형태.

## 왜 (2026-08-31 새벽, 대표님 지시 ②의 핵심)

"이득 본 구간과 손해 본 구간의 특징을 추상화하라."

오늘 밤 관측 가능한 상태 15종으로 갈라봤고 전부 실패했다(p 0.713 / 0.175).
그런데 **가장 실용적인 형태를 아직 안 물었다** — 그 구간들이 **지속되는가**.

지속되면 상태 변수가 필요 없다. "최근 k 구간에서 벌었으면 계속한다"는
게이트가 그 자체로 성립한다. 지속되지 않으면 국면을 알아도 못 쓴다.

## 무엇을 재나

    ① 자기상관     블록 성과의 lag 1..24 자기상관 (비겹침)
    ② 조건부       최근 k 블록 평균이 양수/음수일 때 다음 블록
    ③ 런 길이      연속 양수·음수 구간의 길이 분포 대 무작위
    ④ 게이트 실현  "최근 k 양수면 거래" 규칙의 실제 총손익

⚠ **위약 대조 필수.** 회전한 계열에도 자기상관이 있으면(시장 자체의 성질)
  그건 신호의 지속성이 아니다.
⚠ 겹치는 창으로 자기상관을 재지 마라 — 이 트랙에서 r +0.470 이 비겹침에서
  +0.001 이 된 적이 있다. 블록은 **비겹침**으로 만든다.
⚠ 조건부 격자(k × 문턱)를 뒤지므로 **최대통계량**(교훈#95).

사용:
  python3 -m scripts.research.edge_persistence --smoke 80 --reps 30
  python3 -m scripts.research.edge_persistence --reps 1000
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
log = logging.getLogger("persist")

BAR, ANCH, Q = 5, 12, 0.2
FEE2 = 0.072
SIG_BARS, HOLD_H, DELAY = 12, 24, 1        # 충격12봉 · 보유24h · 지연1봉
KS = (1, 2, 3, 5, 8, 13)                   # 최근 몇 구간을 보나
LAGS = (1, 2, 3, 4, 6, 8, 12, 24)


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


def series(mk, R) -> np.ndarray:
    rows, top, bot = mk
    r = R[rows]
    with np.errstate(invalid="ignore"):
        v = (np.nanmean(np.where(top, r, np.nan), axis=1)
             - np.nanmean(np.where(bot, r, np.nan), axis=1))
    return v


def stats(v: np.ndarray, cfg: Cfg) -> dict:
    """자기상관 · 조건부 · 런 길이. 전부 **비겹침** 계열에서."""
    x = v[np.isfinite(v)] - FEE2
    out = {"n": len(x), "평균": float(x.mean())}
    for L in LAGS:
        if len(x) > L + 10:
            a, b = x[:-L], x[L:]
            out[f"ac{L}"] = float(np.corrcoef(a, b)[0, 1])
    for k in KS:
        if len(x) <= k + 10:
            continue
        prev = pd.Series(x).rolling(k).mean().shift(1).to_numpy()
        m = np.isfinite(prev)
        pos, neg = m & (prev > 0), m & (prev <= 0)
        if pos.sum() < cfg.min_per_side or neg.sum() < cfg.min_per_side:
            continue
        out[f"k{k}양수후"] = float(x[pos].mean())
        out[f"k{k}음수후"] = float(x[neg].mean())
        out[f"k{k}차"] = float(x[pos].mean() - x[neg].mean())
        # ④ 게이트 실현 — "최근 k 양수면 거래"의 단리합
        out[f"k{k}게이트"] = float(x[pos].sum())
        out[f"k{k}항상"] = float(x.sum())
    s = np.sign(x)
    runs = np.diff(np.flatnonzero(np.r_[True, s[1:] != s[:-1], True]))
    out["런평균"] = float(runs.mean()); out["런최장"] = int(runs.max())
    return out


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
    r = np.full(C.shape, np.nan, np.float32)
    r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
    X = np.where(live, -r, np.nan)
    k, d = HOLD_H * 12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - k - d
    R[:hi_] = ((C[d+k:d+k+hi_] / C[d:d+hi_] - 1.0) * 100.0
               - (CUM[d+k:d+k+hi_] - CUM[d:d+hi_]))       # r - f
    warm = SIG_BARS + 12
    anc = np.arange(warm, n - k - d - 1)
    anc = anc[anc % ANCH == 0]
    XA, RA = X[anc], R[anc]
    na = len(anc)
    pos = np.arange(0, na - HOLD_H - 1, HOLD_H)           # **비겹침**
    x = XA[pos]
    good = np.isfinite(x).sum(1) >= cfg.min_syms
    x = x[good]
    with np.errstate(invalid="ignore"):
        qs = np.nanquantile(x, [Q, 1-Q], axis=1)
    ok = qs[1] > qs[0]
    x = x[ok]
    MK = (pos[good][ok], x >= qs[1][ok][:, None], x <= qs[0][ok][:, None])
    log.info("판 %s봉 × %d종목 · 비겹침 블록 %d개 · %.1f분", f"{n:,}", len(syms),
             len(MK[0]), (time.time()-t0)/60)

    O = stats(series(MK, RA), cfg)
    print(f"\n■ 비겹침 블록 {O['n']}개 · 평균 {O['평균']:+.4f}% "
          f"(충격12봉 · 보유{HOLD_H}h · 지연{DELAY}봉 · 펀딩 포함)")
    print("\n■ 자기상관 (지속되면 양수여야 한다)")
    print("  " + " · ".join(f"lag{L} {O.get(f'ac{L}', float('nan')):+.3f}"
                            for L in LAGS))
    print("\n■ 조건부 — 최근 k 블록 평균의 부호로 가른 다음 블록(%)")
    rows = [{"k": kk, "양수후": O.get(f"k{kk}양수후"), "음수후": O.get(f"k{kk}음수후"),
             "차": O.get(f"k{kk}차"), "게이트단리합": O.get(f"k{kk}게이트"),
             "항상단리합": O.get(f"k{kk}항상")}
            for kk in KS if f"k{kk}차" in O]
    print(pd.DataFrame(rows).to_string(index=False,
                                       float_format=lambda v: f"{v:+.4f}"))
    print(f"\n■ 런 — 평균 {O['런평균']:.2f}블록 · 최장 {O['런최장']}")

    rng = np.random.default_rng(cfg.seed)
    mem = HOLD_H * 2 + SIG_BARS
    keys = [f"ac{L}" for L in LAGS] + [f"k{kk}차" for kk in KS if f"k{kk}차" in O]
    NUL = {q_: np.empty(cfg.reps) for q_ in keys + ["런평균"]}
    for i in range(cfg.reps):
        sh = int(rng.integers(mem, na - mem))
        P = stats(series(MK, np.roll(RA, sh, axis=0)), cfg)
        for q_ in NUL:
            NUL[q_][i] = P.get(q_, np.nan)
        if (i+1) % 100 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    rr = []
    for q_ in keys + ["런평균"]:
        nn = NUL[q_][np.isfinite(NUL[q_])]
        if not len(nn):
            continue
        ov = O.get(q_, np.nan)
        rr.append({"항목": q_, "관측": ov, "위약중앙": float(np.median(nn)),
                   "위약95": float(np.quantile(nn, .95)),
                   "p": float((np.abs(nn) >= abs(ov)).mean())})
    RES = pd.DataFrame(rr).sort_values("p")
    print("\n■ 회전 위약 대조 (양측 |값| 기준)")
    print(RES.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    gobs = max(abs(O.get(q_, 0.0)) for q_ in keys)
    gnull = np.nanmax(np.abs(np.vstack([NUL[q_] for q_ in keys])), axis=0)
    gp = float((gnull >= gobs).mean())
    print(f"\n■ 최대통계량 ({cfg.reps}회 · {len(keys)}항목)")
    print(f"  관측 최대 |값| {gobs:.4f} · 귀무 중앙 {np.median(gnull):.4f} "
          f"· 95분위 {np.quantile(gnull,.95):.4f}  **p = {gp:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    RES.to_csv(OUT / "edge_persistence.csv", index=False)
    (OUT / "edge_persistence.null.json").write_text(json.dumps(
        {"blocks": O["n"], "mean": O["평균"], "p_max": gp, "reps": cfg.reps,
         "obs_max": float(gobs)}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
