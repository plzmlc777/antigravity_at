"""진입 필터 — **틱 전용 미시구조**로. 종가·거래량 파생은 이미 다 닫혔다.

## 왜 이 축인가 (2026-08-31)

지금까지 쓴 필터(변동성·거래활성·고저폭·되돌림·체결방향)는 전부 5분봉으로도
되는 것이었고 12칸 중 11칸이 무필터보다 나빴다. 틱에만 있는 것을 쓴다.

    대형체결집중도  Σqv² / (Σqv)² × n  — 체결 크기가 소수에 몰렸나
    체결크기비      평균 체결 크기 ÷ 24h 평균
    튐강도          연속 체결의 가격 방향 반전 비율 (호가 튐 세기)
    **이동효율**    |순이동| / Σ|틱이동| — 직선 하락인가 지그재그인가
    매수체결수비율  **건수** 기준 (대금 기준과 다르다)
    체결간격변동    도착 시각의 불규칙성

이동효율이 기제가 가장 분명하다 — 같은 -5% 라도 직선이면 정보(지속),
지그재그면 잡음(되돌림)이다.

## 측정을 바꾼다

슬롯 5개로 실현해 재면 표본이 앵커 수로 줄고, 필터가 z_vel 선별과 충돌해
**필터의 정보와 선별 훼손이 섞인다**(앞선 탐색에서 11/12칸이 무필터보다 나빴다).

여기선 **밴드 후보 전체를 분위로 갈라** 각 분위의 gross 스프레드를 잰다.
후보 14만 건을 다 쓰므로 검정력이 크고, 선별 훼손이 안 섞인다.

    분위별 gross = (롱 후보 분위 평균) − (숏 후보 분위 평균)
    마찰 0.072% 를 넘는 분위가 있나

⚠ 앵커마다 **횡단면 분위**로 자른다(전역 문턱 아님)
⚠ 시각 클러스터 — 같은 앵커의 후보는 독립이 아니다. 앵커 평균으로 접는다
⚠ 위상 24개 평균 · 회전 위약 최대통계량 (6특징 × 5분위 = 30칸)

사용:
  python3 -m scripts.research.tick_micro_filter --reps 500
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
TICKS = ROOT / "runs" / "ticks"
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("micro")

WIN_H, WINDOW, DELTA = 60, 360, 180
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
HOLD, ANCH, DELAY = 120, 5, 5
FEE2, MIN_LIVE = 0.072, 5.0
NQ = 5
LOOK = 60                     # 특징을 재는 뒤돌아보기(분)


@dataclass(frozen=True)
class Cfg:
    min_ticks: int = 2_000
    min_cand: int = 30        # 앵커당 최소 후보(롱·숏 각각)
    min_per_bin: int = 5
    reps: int = 500
    seed: int = 20260831


def per_minute(x: pd.DataFrame) -> pd.DataFrame:
    """틱 → 분당 미시구조 집계. 여기서만 되는 것들."""
    x = x.sort_values("ts_ms")
    p = x.price.to_numpy(np.float64)
    qv = (x.price * x.qty).to_numpy(np.float64)
    m = (x.ts_ms // 60_000).to_numpy()
    d = np.diff(p, prepend=p[0])
    sg = np.sign(d)
    # 방향 반전: 직전 0 아닌 부호와 반대인가
    prev = pd.Series(np.where(sg == 0, np.nan, sg)).ffill().to_numpy()
    flip = (sg != 0) & (np.roll(prev, 1) != 0) & (sg != np.roll(prev, 1))
    g = pd.DataFrame({
        "m": m, "p": p, "qv": qv, "ad": np.abs(d), "fl": flip.astype(float),
        "bq": (~x.is_buyer_maker).to_numpy().astype(float),
        "dt": np.diff(x.ts_ms.to_numpy(), prepend=x.ts_ms.iloc[0]).astype(float),
    }).groupby("m")
    o = pd.DataFrame({
        "cl": g.p.last(), "n": g.p.size(),
        "qv": g.qv.sum(), "qv2": g.qv.apply(lambda z: float((z**2).sum())),
        "absmove": g.ad.sum(),
        "netmove": g.p.apply(lambda z: abs(float(z.iloc[-1] - z.iloc[0]))),
        "flip": g.fl.sum(), "buyn": g.bq.sum(),
        "dtm": g.dt.mean(), "dts": g.dt.std(),
    })
    o.index = pd.to_datetime(o.index * 60_000, unit="ms", utc=True)
    return o


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_live_universe.txt")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    t0 = time.time()
    uni = [s.strip().upper() for s in (ROOT/a.universe).read_text().split()
           if s.strip()]
    cols = {}
    for i, s in enumerate(uni):
        d = TICKS / s
        if not d.is_dir():
            continue
        fs = sorted(d.glob("*.parquet"))
        if not fs:
            continue
        try:
            x = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        except Exception:                                      # noqa: BLE001
            continue
        x = x[(x.price > 0) & (x.qty > 0)]
        if len(x) < cfg.min_ticks:
            continue
        cols[s] = per_minute(x)
        if (i+1) % 80 == 0:
            log.info("  [%d/%d] %.1f분", i+1, len(uni), (time.time()-t0)/60)
    syms = sorted(cols)
    idx = pd.date_range(min(v.index.min() for v in cols.values()),
                        max(v.index.max() for v in cols.values()),
                        freq="1min", tz="UTC")
    def mat(k, fill=0.0):
        return pd.DataFrame({s: cols[s][k] for s in syms}).reindex(idx).fillna(fill)
    CL = pd.DataFrame({s: cols[s]["cl"] for s in syms}).reindex(idx).ffill()
    N, QV, QV2 = mat("n"), mat("qv"), mat("qv2")
    ABS, NET, FLIP = mat("absmove"), mat("netmove"), mat("flip")
    BUYN, DTM, DTS = mat("buyn"), mat("dtm", np.nan), mat("dts", np.nan)
    del cols
    n = len(CL)
    log.info("틱 → 분당 집계 %s분 × %d종목 · %.1f분", f"{n:,}", len(syms),
             (time.time()-t0)/60)

    L = LOOK
    rs = lambda M: M.rolling(L).sum()
    F = {
        # Σqv²/(Σqv)² × n — 1 이면 균등, 클수록 소수 체결에 몰림
        "대형체결집중": (rs(QV2) * rs(N) / (rs(QV)**2 + 1e-18)).shift(1),
        "체결크기비": ((rs(QV)/(rs(N)+1e-9))
                     / (QV.rolling(1440).sum()/(N.rolling(1440).sum()+1e-9)
                        + 1e-18)).shift(1),
        "튐강도": (rs(FLIP)/(rs(N)+1e-9)).shift(1),
        "이동효율": (rs(NET)/(rs(ABS)+1e-12)).shift(1),
        "매수체결수비": (rs(BUYN)/(rs(N)+1e-9)).shift(1),
        "체결간격변동": (DTS.rolling(L).mean()/(DTM.rolling(L).mean()+1e-9)).shift(1),
    }
    F = {k: v.to_numpy(np.float32) for k, v in F.items()}

    fw = CL.shift(-WIN_H)/CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H)
    vel = rate - rate.shift(DELTA); accd = vel - vel.shift(DELTA)
    pr = rate.clip(0.01, 0.99); se = np.sqrt(pr*(1-pr)/(WINDOW/WIN_H))
    ZV = (vel/(se*np.sqrt(2))).to_numpy(np.float32)
    ZA = (accd/(se*2.0)).to_numpy(np.float32)
    live = (N.rolling(60).median().shift(1) >= MIN_LIVE).to_numpy()

    C = CL.to_numpy(np.float32)
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time>=:a AND funding_time<:b "
             "ORDER BY funding_time")
    CUM = np.zeros((n, len(syms)), np.float32)
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='180s'"))
        for j, s in enumerate(syms):
            r = c_.execute(q, {"s": s, "a": idx.min().tz_convert(None),
                               "b": idx.max().tz_convert(None)}).all()
            if not r:
                continue
            t_ = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r])*100.0
            pos = np.clip(idx.searchsorted(t_, side="left"), 0, n-1)
            acc_ = np.zeros(n); np.add.at(acc_, pos, v)
            CUM[:, j] = np.cumsum(acc_).astype(np.float32)
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - HOLD - DELAY
    R[:hi_] = ((C[DELAY+HOLD:DELAY+HOLD+hi_]/C[DELAY:DELAY+hi_]-1.0)*100.0
               - (CUM[DELAY+HOLD:DELAY+HOLD+hi_]-CUM[DELAY:DELAY+hi_]))

    base = np.arange(WIN_H+WINDOW+2*DELTA, n-HOLD-DELAY-1)
    base = base[base % ANCH == 0]
    zv, za, lv, Ra = ZV[base], ZA[base], live[base], R[base]
    OKL = (zv >= Z_LO)&(zv <= Z_HI)&(za < ACC_MAX)&lv&np.isfinite(zv)
    OKS = (zv >= -Z_HI)&(zv <= -Z_LO)&(za > -ACC_MAX)&lv&np.isfinite(zv)
    nph = HOLD//ANCH
    log.info("앵커 %s개 · 후보 롱 %s · 숏 %s · %.1f분", f"{len(base):,}",
             f"{int(OKL.sum()):,}", f"{int(OKS.sum()):,}", (time.time()-t0)/60)

    def masks(fname):
        """앵커마다 롱·숏 후보를 특징 5분위로. (행, 분위, 롱/숏 색인)"""
        fv = F[fname][base]
        out = []
        for ph in range(nph):
            rows = np.arange(ph, len(base)-nph-1, nph)
            per = []
            for i in rows:
                li, si = np.where(OKL[i])[0], np.where(OKS[i])[0]
                if len(li) < cfg.min_cand or len(si) < cfg.min_cand:
                    continue
                ent = []
                ok = True
                for ii in (li, si):
                    x = fv[i][ii]
                    m = np.isfinite(x)
                    if m.sum() < NQ*cfg.min_per_bin:
                        ok = False; break
                    xi, xv = ii[m], x[m]
                    e = np.quantile(xv, np.linspace(0, 1, NQ+1)[1:-1])
                    ent.append([xi[(np.digitize(xv, e) == b)] for b in range(NQ)])
                if ok and all(len(z) for e in ent for z in e):
                    per.append((i, ent[0], ent[1]))
            if per:
                out.append(per)
        return out

    def stat(mk, Rm):
        """분위별 gross 스프레드 — 앵커 평균 → 위상 평균."""
        res = np.zeros(NQ)
        for ph in mk:
            acc = np.zeros((NQ, 0)).tolist()
            per = [[] for _ in range(NQ)]
            for i, eL, eS in ph:
                r = Rm[i]
                for b in range(NQ):
                    a_, b_ = r[eL[b]], r[eS[b]]
                    a_, b_ = a_[np.isfinite(a_)], b_[np.isfinite(b_)]
                    if len(a_) and len(b_):
                        per[b].append(a_.mean() - b_.mean())
            for b in range(NQ):
                if per[b]:
                    res[b] += np.mean(per[b])
        return res / max(len(mk), 1)

    MK = {f: masks(f) for f in F}
    MK = {k: v for k, v in MK.items() if v}
    rng = np.random.default_rng(cfg.seed)
    shifts = rng.integers(nph*4, len(base)-nph*4, size=cfg.reps)
    rows, best = [], np.full(cfg.reps, -9e9)
    for f, mk in MK.items():
        o = stat(mk, Ra)
        rows.append({"특징": f, **{f"Q{b+1}": o[b]-FEE2 for b in range(NQ)},
                     "최고-최저": float(o.max()-o.min())})
        for i, sh in enumerate(shifts):
            v = stat(mk, np.roll(Ra, int(sh), axis=0)) - FEE2
            best[i] = max(best[i], float(np.nanmax(v)))
        log.info("  %-12s Q1 %+.4f … Q5 %+.4f · %.1f분", f, o[0]-FEE2,
                 o[-1]-FEE2, (time.time()-t0)/60)
    R0 = pd.DataFrame(rows)
    print(f"\n■ 틱 미시구조 필터 — 밴드 후보 **분위별 gross 스프레드** "
          f"(수수료 {FEE2}% 차감 · 위상 평균 · 뒤돌아보기 {LOOK}분)")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    obs = float(R0[[f"Q{b+1}" for b in range(NQ)]].to_numpy().max())
    pm = float((best >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(MK)}특징 × {NQ}분위)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "tick_micro_filter.csv", index=False)
    (OUT / "tick_micro_filter.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "feats": list(MK)},
        ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
