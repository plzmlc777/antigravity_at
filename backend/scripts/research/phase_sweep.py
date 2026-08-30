"""**위상 점검** — 24시간 보유 격자가 하루 중 한 시각에 고정된다.

## 왜 (2026-08-31 04:38)

같은 전략(슬롯10 · 무조건 되돌림)이 두 하네스에서 갈렸다:

    final_verdict   +0.315%/블록
    xsec_volume     -0.081%/블록

원인은 **앵커 시작점**이다. 워밍업이 달라 블록 격자가 23시간 어긋났다.
그런데 블록 간격이 24시간이라 **격자가 하루 중 한 시각에 고정된다** —
지금까지 모든 24시간 보유 검정은 매일 같은 시각에만 진입했다.

교훈#85(펀딩 정산은 시간대 효과)가 경고한 자리다. 그리고 이게 **표본 밖
부호 반전의 설명**일 수 있다 — 구간이 다르면 달력 정렬이 달라져 다른 시각을 잡는다.

## 무엇을 하나

위상 0~23 을 **전부** 돌려 분포를 본다.

    위상 간 표준편차가 크다  → 지금까지의 결과는 **한 시각의 우연**이다
    위상 간 표준편차가 작다  → 위상은 무관하고 앞의 불일치는 다른 원인이다

⚠ 위약도 같은 24위상으로 돌려 나란히 놓는다. 위상 분산 자체는 잡음에도 있다 —
  실측 분산이 위약 분산보다 커야 "시각 효과"라 부를 수 있다.
⚠ 위상 평균(24개를 다 쓰는 겹친 전략)이 진짜 기대값이다. 하나만 쓰면
  그건 **선택**이고 24칸 중 최고를 고른 값이다.

사용:
  python3 -m scripts.research.phase_sweep --reps 200
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("phase")

BAR, ANCH = 5, 12
SIG_BARS, HOLD_H, DELAY = 12, 24, 1
FEE1 = 0.036
SLOTS = (10, 20, 48)


@dataclass(frozen=True)
class Cfg:
    min_bars_in_5: float = 3.0
    reps: int = 200
    seed: int = 20260831


def load(files):
    cl, nb, vv = {}, {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        cl[f.stem] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        nb[f.stem] = pd.Series(d.n.to_numpy(np.float32), index=ts)
        vv[f.stem] = pd.Series(d.v.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    return (pd.DataFrame(cl).reindex(idx).ffill(),
            pd.DataFrame(nb).reindex(idx).fillna(0.0),
            pd.DataFrame(vv).reindex(idx).fillna(0.0), idx)


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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="")
    p.add_argument("--limit-to", default="",
                   help="종목 집합을 맞춰야 구간 비교가 사과 대 사과다(교훈#110)")
    p.add_argument("--signal", default="되돌림", choices=["되돌림", "거래량"],
                   help="거래량 신호도 같은 격자에서 나온 값이라 같은 검사를 받아야 한다")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    cache = (ROOT / a.cache) if a.cache else CACHE
    fs = sorted(cache.glob("*.parquet"))
    if a.limit_to:
        keep = {x.stem for x in (ROOT / a.limit_to).glob("*.parquet")}
        fs = [x for x in fs if x.stem in keep]
    t0 = time.time()
    CL, NB, V, idx = load(fs)
    syms = list(CL.columns); n = len(CL)
    CUM = funding_cum(syms, idx)
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    if a.signal == "거래량":
        # 상대거래량 = 최근 1h ÷ 직전 24h 시간당 평균. 큰 값 = 롱 이 되도록 부호를
        # 뒤집는다(조용한 종목을 롱, 급증한 종목을 숏).
        v1 = V.rolling(SIG_BARS).sum()
        v24 = V.rolling(288).sum().shift(SIG_BARS) / (288 / SIG_BARS)
        X = np.where(live, -(v1 / (v24 + 1e-9)).to_numpy(np.float32), np.nan)
    else:
        r = np.full(C.shape, np.nan, np.float32)
        r[SIG_BARS:] = (C[SIG_BARS:] / C[:-SIG_BARS] - 1.0) * 100.0
        X = np.where(live, -r, np.nan)
    kk, d = HOLD_H*12, DELAY
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - kk - d
    R[:hi_] = ((C[d+kk:d+kk+hi_] / C[d:d+hi_] - 1.0)*100.0
               - (CUM[d+kk:d+kk+hi_] - CUM[d:d+hi_]))
    warm = 300 if a.signal == "거래량" else SIG_BARS + 12
    base = np.arange(warm, n - kk - d - 1)
    base = base[base % ANCH == 0]
    XA, RA = X[base], R[base]
    hours = idx[base].hour.to_numpy()
    log.info("판 %s봉 × %d종목 · 앵커 %s개 · %.1f분", f"{n:,}", len(syms),
             f"{len(base):,}", (time.time()-t0)/60)

    def phase_mean(Rm, N, ph):
        """위상 `ph` 의 비겹침 블록만 써서 평균 스프레드."""
        pos = np.arange(ph, len(base) - HOLD_H - 1, HOLD_H)
        vals = []
        for i in pos:
            x, rr = XA[i], Rm[i]
            m = np.isfinite(x) & np.isfinite(rr)
            if m.sum() < 2*N + 10:
                continue
            ii = np.where(m)[0]
            o = ii[np.argsort(x[ii])]
            vals.append(float(rr[o[-N:]].mean() - rr[o[:N]].mean()) - 2*FEE1)
        return (float(np.mean(vals)), int(np.median(hours[pos]))) if vals else (np.nan, -1)

    rows = []
    for N in SLOTS:
        ms = [phase_mean(RA, N, ph) for ph in range(HOLD_H)]
        v = np.array([m[0] for m in ms])
        rows.append({"슬롯": N, "위상평균": float(np.nanmean(v)),
                     "위상표준편차": float(np.nanstd(v, ddof=1)),
                     "최고위상": float(np.nanmax(v)), "최저위상": float(np.nanmin(v)),
                     "양수위상": int(np.nansum(v > 0)), "폭": float(np.nanmax(v)-np.nanmin(v))})
        if N == 10:
            print(f"\n■ 슬롯 10 · 위상 24개 (UTC 진입시각별) — 평균 스프레드 %")
            pr = pd.DataFrame({"위상": range(HOLD_H),
                               "UTC시각": [m[1] for m in ms],
                               "평균": v})
            print(pr.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    RS = pd.DataFrame(rows)
    print("\n■ 슬롯별 위상 분포")
    print(RS.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    nb_ = len(base)
    nsd, nmax, nmean = [], [], []
    for i in range(cfg.reps):
        sh = int(rng.integers(HOLD_H, nb_ - HOLD_H))
        Rr = np.roll(RA, sh, axis=0)
        v = np.array([phase_mean(Rr, 10, ph)[0] for ph in range(HOLD_H)])
        nsd.append(np.nanstd(v, ddof=1)); nmax.append(np.nanmax(v))
        nmean.append(np.nanmean(v))
        if (i+1) % 25 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    nsd = np.array(nsd); nmax = np.array(nmax); nmean = np.array(nmean)
    o = RS[RS.슬롯 == 10].iloc[0]
    print(f"\n■ 회전 위약 ({cfg.reps}회 · 슬롯 10 · 위약도 24위상 전부)")
    print(f"  위상 표준편차  관측 {o.위상표준편차:.4f} · 귀무 중앙 {np.median(nsd):.4f} "
          f"· 95분위 {np.quantile(nsd,.95):.4f}  **p = {(nsd>=o.위상표준편차).mean():.3f}**")
    print(f"  최고 위상      관측 {o.최고위상:+.4f} · 귀무 중앙 {np.median(nmax):+.4f} "
          f"· 95분위 {np.quantile(nmax,.95):+.4f}  **p = {(nmax>=o.최고위상).mean():.3f}**")
    print(f"  **위상 평균**  관측 {o.위상평균:+.4f} · 귀무 중앙 {np.median(nmean):+.4f} "
          f"· 95분위 {np.quantile(nmean,.95):+.4f}  **p = {(nmean>=o.위상평균).mean():.3f}**")
    print("\n  ⚠ 위상 평균이 진짜 기대값이다. 한 위상만 쓰면 24칸 중 하나를 **고른** 것이다.")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = ("oos" if a.cache else ("is125" if a.limit_to else "is")) \
        + ("_vol" if a.signal == "거래량" else "")
    RS.to_csv(OUT / f"phase_sweep_{tag}.csv", index=False)
    (OUT / f"phase_sweep_{tag}.null.json").write_text(json.dumps(
        {"phase_mean": float(o.위상평균), "phase_sd": float(o.위상표준편차),
         "p_mean": float((nmean >= o.위상평균).mean()),
         "p_sd": float((nsd >= o.위상표준편차).mean()),
         "p_max": float((nmax >= o.최고위상).mean()), "reps": cfg.reps},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
