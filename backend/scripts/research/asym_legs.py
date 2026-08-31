"""롱숏 구조 진화 — **비대칭 슬롯**과 **시장 헤지**. 2년으로.

## 왜 (2026-08-31, 페이퍼 분해에서)

공통 구간 45.7시간 실측:

    롱숏10 롱 다리 +0.1021%  대  롱10(슬롯10) -0.1027%   차 **+0.2047%p**
    롱숏10 숏 다리 +0.0064%  대  숏10(슬롯10) +0.0045%   차   +0.0019%p

**수익은 전부 롱에서 나오고, 롱 슬롯을 줄일수록 강해진다.** 숏은 기여 0 이고
시장 노출을 상쇄하는 역할만 한다. 시각 SD 도 0.379% 로 다른 갈래의 1/3 이다.

그러면 두 갈래로 진화한다:

    A 비대칭 슬롯   롱은 집중(적게) · 숏은 분산(많게). 자본은 **다리별 반반**
                    이라 시장 중립은 유지된다
    B 시장 헤지     숏 선별이 0 을 더한다면 **선별 대신 시장 전체를 숏**한다.
                    같은 헤지를 개별 종목 위험 없이 얻는다

⚠ 5일 틱으로 하면 30배 부풀려진다(A-B 검정 실측). z_vel 은 종가만 쓰므로
  **2년 기질**로 잰다.
⚠ 자본이 다리별 반반이면 포트폴리오 수익 = (롱평균 - 숏평균)/2 이고
  종목 수와 무관하다. 종목 수는 **평균의 대상**만 바꾼다.
⚠ 위상 24개 평균(교훈#111) · 진입 5분 지연 · 왕복 0.072% · 펀딩 포함

사용:
  python3 -m scripts.research.asym_legs --reps 300
  python3 -m scripts.research.asym_legs --cache runs/bars5m_oos
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
OUT = ROOT / "runs" / "research_track" / "night_2026_08_31"
log = logging.getLogger("asym")

BAR = 5
WIN_H, WINDOW, DELTA = 12, 72, 36
Z_LO, Z_HI, ACC_MAX = -1.25, -0.25, 0.5
HOLD, DELAY, FEE1, MIN_BARS = 24, 1, 0.036, 3.0
# (롱 종목, 숏 종목) — 자본은 다리별 반반
PAIRS = [(2, 8), (3, 7), (5, 5), (7, 3), (8, 2), (3, 3), (5, 10), (10, 5)]
MKT_LONGS = (3, 5, 10)          # 롱 N + 시장 전체 숏


@dataclass(frozen=True)
class Cfg:
    min_side: int = 12          # 앵커당 롱·숏 후보 최소
    reps: int = 300
    seed: int = 20260831


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache", default="runs/bars5m")
    p.add_argument("--reps", type=int, default=None)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = Cfg(**({"reps": a.reps} if a.reps is not None else {}))
    t0 = time.time()
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
    CL = pd.DataFrame(cl).reindex(idx).ffill()
    NB = pd.DataFrame(nb).reindex(idx).fillna(0.0)
    syms, n = list(CL.columns), len(CL)
    log.info("판 %s봉 × %d종목 · %s ~ %s · %.1f분", f"{n:,}", len(syms),
             idx.min().date(), idx.max().date(), (time.time()-t0)/60)

    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time>=:a AND funding_time<:b "
             "ORDER BY funding_time")
    CUM = np.zeros((n, len(syms)), np.float32)
    with engine.connect() as c_:
        c_.execute(text("SET statement_timeout='240s'"))
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

    C = CL.to_numpy(np.float32)
    live = (NB.rolling(12).median().shift(1) >= MIN_BARS).to_numpy()
    del NB, nb, cl
    # ⚠ 메모리 — 240종목 × 218k봉이면 중간값 하나가 419MB(float64)다. 일곱 개를
    #   동시에 들고 있다가 **역추적 없이 강제종료**됐다(2026-08-31, 로그 한 줄).
    #   쓴 즉시 버리고 float32 로 낮춘다.
    fw = CL.shift(-WIN_H)/CL - 1.0
    win = (fw > 0).astype(np.float32).where(fw.notna())
    del fw, CL
    rate = win.rolling(WINDOW, min_periods=WINDOW//2).mean().shift(WIN_H)
    del win
    vel = (rate - rate.shift(DELTA)).to_numpy(np.float32)
    accd = (vel - np.roll(vel, DELTA, axis=0)).astype(np.float32)
    accd[:DELTA] = np.nan
    # ⚠ `to_numpy()` 는 **읽기전용 뷰**를 돌려줄 수 있다 — 제자리 clip 이 막힌다
    pr = np.clip(rate.to_numpy(np.float32), 0.01, 0.99); del rate
    se = np.sqrt(pr*(1-pr)/(WINDOW/WIN_H), dtype=np.float32); del pr
    ZV = (vel/(se*np.float32(np.sqrt(2)))).astype(np.float32); del vel
    ZA = (accd/(se*np.float32(2.0))).astype(np.float32); del accd, se
    R = np.full(C.shape, np.nan, np.float32)
    hi_ = n - HOLD - DELAY
    R[:hi_] = ((C[DELAY+HOLD:DELAY+HOLD+hi_]/C[DELAY:DELAY+hi_]-1.0)*100.0
               - (CUM[DELAY+HOLD:DELAY+HOLD+hi_]-CUM[DELAY:DELAY+hi_]))
    base = np.arange(WIN_H+WINDOW+2*DELTA, n-HOLD-DELAY-1)
    zv, za, lv, Ra = ZV[base], ZA[base], live[base], R[base]
    OKL = (zv>=Z_LO)&(zv<=Z_HI)&(za<ACC_MAX)&lv&np.isfinite(zv)
    OKS = (zv>=-Z_HI)&(zv<=-Z_LO)&(za>-ACC_MAX)&lv&np.isfinite(zv)
    ALIVE = lv & np.isfinite(Ra)
    nb_ = len(base)
    log.info("앵커 %s · 후보 롱 중앙 %d · 숏 중앙 %d · %.1f분", f"{nb_:,}",
             int(np.median(OKL.sum(1))), int(np.median(OKS.sum(1))),
             (time.time()-t0)/60)

    def build(nl, ns, mkt_hedge):
        """위상별 (행, 롱색인, 숏색인). 자본은 다리별 반반이라 평균끼리 뺀다."""
        out = []
        for ph in range(HOLD):
            rows = np.arange(ph, nb_ - HOLD - 1, HOLD)
            kk, L, S = [], [], []
            for i in rows:
                li = np.where(OKL[i])[0]
                if len(li) < max(nl, cfg.min_side):
                    continue
                # ⚠ 앵커를 **모든 칸에서 같게** 건다. 시장헤지만 숏후보 부족한
                #   순간까지 거래하면(132,718 대 58,145) 나쁜 값이 구조 탓인지
                #   그 순간들 탓인지 못 가른다. 숏 가용 조건은 그대로 두고
                #   **고르는 대상만** 바꾼다.
                if len(np.where(OKS[i])[0]) < max(ns, cfg.min_side):
                    continue
                if mkt_hedge:
                    si = np.where(ALIVE[i])[0]      # 시장 전체 등가중
                    if len(si) < 30:
                        continue
                else:
                    si = np.where(OKS[i])[0]
                    si = si[np.argsort(-zv[i][si])[:ns]]
                kk.append(i); L.append(li[np.argsort(zv[i][li])[:nl]]); S.append(si)
            if kk:
                out.append((np.asarray(kk), L, S))
        return out

    def stat(mk, Rm):
        per = []
        for kk, L, S in mk:
            v = []
            for j, i in enumerate(kk):
                a_, b_ = Rm[i][L[j]], Rm[i][S[j]]
                a_, b_ = a_[np.isfinite(a_)], b_[np.isfinite(b_)]
                if len(a_) and len(b_):
                    v.append(a_.mean() - b_.mean())
            if v:
                per.append(np.mean(v))
        return float(np.mean(per)) - 2*FEE1 if per else np.nan

    CELLS = ([(nl, ns, False) for nl, ns in PAIRS]
             + [(nl, 0, True) for nl in MKT_LONGS])
    rng = np.random.default_rng(cfg.seed)
    shifts = rng.integers(HOLD*4, nb_ - HOLD*4, size=cfg.reps)
    rows, best = [], np.full(cfg.reps, -9e9)
    for (nl, ns, mh) in CELLS:
        mk = build(nl, ns, mh)
        if not mk:
            continue
        o = stat(mk, Ra)
        rows.append({"롱": nl, "숏": ("시장전체" if mh else ns),
                     "앵커": sum(len(k) for k, _, _ in mk), "수수료후": o})
        for i, sh in enumerate(shifts):
            v = stat(mk, np.roll(Ra, int(sh), axis=0))
            if np.isfinite(v):
                best[i] = max(best[i], v)
        # 앵커 수를 같이 찍는다 — 칸마다 같아야 비교가 성립한다(도달 증명)
        log.info("  롱%d · 숏%-4s → %+.4f%% · 앵커 %s · %.1f분", nl,
                 "시장" if mh else str(ns), o,
                 f"{sum(len(k) for k, _, _ in mk):,}", (time.time()-t0)/60)
    R0 = pd.DataFrame(rows).sort_values("수수료후", ascending=False)
    print(f"\n■ 롱숏 구조 — 자본 다리별 반반 · 보유{HOLD*BAR}분 · 지연{DELAY*BAR}분 "
          f"· 왕복 {2*FEE1}% · 펀딩 · 위상 평균 · 종목 {len(syms)}")
    print(R0.to_string(index=False, float_format=lambda z: f"{z:+.4f}"))
    cur = R0[(R0.롱 == 5) & (R0.숏 == 5)]
    if len(cur):
        print(f"\n  현행(롱5·숏5) {float(cur.수수료후.iloc[0]):+.4f}%")
    obs = float(R0.수수료후.max())
    pm = float((best >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(R0)}칸)")
    print(f"  관측 최대 {obs:+.4f}% · 귀무 중앙 {np.median(best):+.4f}% "
          f"· 95분위 {np.quantile(best,.95):+.4f}%  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "oos" if "oos" in a.cache else "is"
    R0.to_csv(OUT / f"asym_legs_{tag}.csv", index=False)
    (OUT / f"asym_legs_{tag}.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
