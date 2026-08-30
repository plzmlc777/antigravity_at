"""횡단면 되돌림 + **펀딩**. 오늘 밤 통째로 빠뜨린 항.

## 왜 (2026-08-31 새벽)

24시간 보유는 펀딩 정산을 **세 번** 지난다. 8시간당 0.01% 면 하루 0.03% 로
왕복 수수료 0.036% 와 같은 자릿수인데, 오늘 밤 모든 계산에서 빼먹었다.

그리고 이건 스프레드에서 상쇄되지 않는다 — 펀딩은 가격을 따라가고 이 전략은
양 극단을 **반대로** 잡는다:

    롱 다리 = 24h 급락 종목 매수 → 펀딩 음수 쪽 → 롱이 **받는다**
    숏 다리 = 24h 급등 종목 공매 → 펀딩 양수 쪽 → 숏이 **받는다**

## 미리 못 박는 것

⚠ 펀딩이 전반적으로 양수면 **무작위 숏도 받는다**. "펀딩 넣으니 흑자"는
  답이 아니다. 질문은 **신호가 고른 숏이 무작위 숏보다 더 받는가**이고,
  그건 방향별 회전 위약이 잰다. 오늘 밤 이 함정에 이미 두 번 걸렸다
  (손절 해로움 t -8.13 · 숏 다리 +0.106%).

⚠ R-5 시드 `funding_carry` 는 종결된 축이다. 펀딩 **자체를 거래**하는 것과
  다른 이유로 잡은 포지션의 **부수입**은 다르다. 여기선 후자만 다룬다.

⚠ 교훈#85 — 펀딩 정산은 시간대 효과일 수 있다. UTC 시각 대조를 함께 낸다.

사용:
  python3 -m scripts.research.xsec_funding --smoke 60 --reps 30
  python3 -m scripts.research.xsec_funding --reps 1000
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
log = logging.getLogger("xfund")

BAR, ANCH, Q = 5, 12, 0.2
FEE1, FEE2 = 0.036, 0.072
SIGS = {"충격12봉": 12, "충격72봉": 72, "되돌림24h": 288}
# ⚠ 3~7일은 아직 한 번도 안 봤다. 마찰이 고정이니 지평이 길수록 유리해야
#   하는데 48h 는 240종목에서 이미 음수였다. 끝까지 열어 확정한다.
HOLDS_H = (24, 48, 96, 168)
DELAY = 1


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20
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


def load_funding(syms, idx) -> tuple[np.ndarray, dict]:
    """봉마다 **그때까지 누적된** 펀딩(%). 보유 구간 합은 차분으로 낸다."""
    q = text("SELECT funding_time, funding_rate FROM binance_funding_rate "
             "WHERE symbol=:s AND funding_time >= :a AND funding_time < :b "
             "ORDER BY funding_time")
    a = idx.min().tz_convert(None); b = idx.max().tz_convert(None)
    cum = np.zeros((len(idx), len(syms)), np.float32)
    stat = {"종목": 0, "정산": 0, "없음": []}
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='240s'"))
        for j, s in enumerate(syms):
            r = c.execute(q, {"s": s, "a": a, "b": b}).all()
            if not r:
                stat["없음"].append(s)
                continue
            stat["종목"] += 1; stat["정산"] += len(r)
            t = pd.to_datetime([x[0] for x in r], utc=True)
            v = np.asarray([float(x[1]) for x in r], np.float64) * 100.0
            # 정산 시각을 봉 격자에 올린다 — 그 봉 **이후**에 반영된다
            pos = idx.searchsorted(t, side="left")
            pos = np.clip(pos, 0, len(idx) - 1)
            acc = np.zeros(len(idx), np.float64)
            np.add.at(acc, pos, v)
            cum[:, j] = np.cumsum(acc).astype(np.float32)
    return cum, stat


def masks(X, pos, cfg):
    x = X[pos]
    good = np.isfinite(x).sum(1) >= cfg.min_syms
    if not good.any():
        return None
    x = x[good]
    with np.errstate(invalid="ignore"):
        qs = np.nanquantile(x, [Q, 1 - Q], axis=1)
    ok = qs[1] > qs[0]
    x = x[ok]
    return (pos[good][ok], x >= qs[1][ok][:, None], x <= qs[0][ok][:, None])


def legs(rows, top, bot, R, FD=None):
    """롱·숏 다리.

    ## 펀딩 규약 — 한 번만 뺀다

    펀딩은 **롱이 숏에게** 내는 것이다(요율 양수일 때). 그래서 종목마다
    조정수익률을 `r - f` 하나로 정의하면 롱은 그대로 받고 숏은 부호만
    뒤집으면 자동으로 맞는다:

        롱 손익 = r - f          요율 양수면 낸다
        숏 손익 = -(r - f)       = -r + f  요율 양수면 받는다

    ⚠ 처음에 숏쪽을 `r + f` 로 따로 만들었다가 **펀딩 이득을 통째로 지어냈다**
      (실측 +0.0489%p 가 실제로는 -0.003%p). 양 극단 모두 펀딩이 음수라
      롱은 받고 **숏은 내는데**, 부호를 뒤집어 둘 다 받는 것으로 만들었다.
      교훈#89(숏 수익률 규약)와 같은 자리다.
    """
    r = R[rows] if FD is None else (R[rows] - FD[rows])
    with np.errstate(invalid="ignore"):
        L = np.nanmean(np.where(top, r, np.nan), axis=1)
        S = np.nanmean(np.where(bot, r, np.nan), axis=1)
    m = np.isfinite(L) & np.isfinite(S)
    return L[m], S[m]


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
    syms = list(CL.columns)
    n = len(CL)
    log.info("판 %s봉 × %d종목", f"{n:,}", len(syms))
    CUM, fstat = load_funding(syms, idx)
    log.info("펀딩 — 종목 %d/%d · 정산 %s건 · 없음 %d · %.1f분",
             fstat["종목"], len(syms), f"{fstat['정산']:,}",
             len(fstat["없음"]), (time.time()-t0)/60)
    if fstat["없음"]:
        log.warning("펀딩 없는 종목 %d개는 **0으로 취급된다** — %s",
                    len(fstat["없음"]), fstat["없음"][:6])

    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()
    C = CL.to_numpy(np.float32)
    X = {}
    for nm, k in SIGS.items():
        r = np.full(C.shape, np.nan, np.float32)
        r[k:] = (C[k:] / C[:-k] - 1.0) * 100.0
        X[nm] = np.where(live, -r, np.nan)
    warm = max(SIGS.values()) + 12
    anc = np.arange(warm, n - max(HOLDS_H)*12 - DELAY - 1)
    anc = anc[anc % ANCH == 0]
    XA = {k: v[anc] for k, v in X.items()}
    del X
    RA, FA = {}, {}
    for h in HOLDS_H:
        k, d = h * 12, DELAY
        f = np.full(C.shape, np.nan, np.float32)
        hi_ = n - k - d
        f[:hi_] = (C[d+k:d+k+hi_] / C[d:d+hi_] - 1.0) * 100.0
        RA[h] = f[anc]
        g = np.full(C.shape, np.nan, np.float32)
        g[:hi_] = CUM[d+k:d+k+hi_] - CUM[d:d+hi_]     # 보유 구간 펀딩 합
        FA[h] = g[anc]
    na = len(anc)
    log.info("앵커 %s개 · %.1f분", f"{na:,}", (time.time()-t0)/60)

    rows, MSK, keys = [], {}, []
    for h in HOLDS_H:
        pos = np.arange(0, na - h - 1, h)
        for nm in XA:
            mk = masks(XA[nm], pos, cfg)
            if mk is None or len(mk[0]) < cfg.min_times:
                continue
            MSK[(h, nm)] = mk
            L0, S0 = legs(*mk, RA[h])
            L1, S1 = legs(*mk, RA[h], FA[h])
            fd = FA[h][mk[0]]
            with np.errstate(invalid="ignore"):
                f_top = np.nanmean(np.where(mk[1], fd, np.nan))
                f_bot = np.nanmean(np.where(mk[2], fd, np.nan))
            rows.append({
                "보유h": h, "신호": nm, "시각수": len(L0),
                "펀딩前": (L0 - S0).mean() - FEE2,
                "펀딩後": (L1 - S1).mean() - FEE2,
                "펀딩기여": (L1 - S1).mean() - (L0 - S0).mean(),
                "롱後": L1.mean() - FEE1, "숏後": -S1.mean() - FEE1,
                "롱펀딩수취": -f_top, "숏펀딩수취": f_bot,
                "t": float((L1-S1).mean()/((L1-S1).std(ddof=1)/np.sqrt(len(L1))))})
            keys.append((h, nm))
    R = pd.DataFrame(rows).sort_values("펀딩後", ascending=False)
    print(f"\n■ 펀딩 전후 (마찰 {FEE2}% · 진입지연 {DELAY}봉)")
    print(R.to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    rng = np.random.default_rng(cfg.seed)
    mem = max(SIGS.values())//ANCH + max(HOLDS_H) + 2
    obs = float(R.펀딩後.max()); obsS = float(R.숏後.max()); obsL = float(R.롱後.max())
    nl = np.empty(cfg.reps); nS = np.empty(cfg.reps); nL = np.empty(cfg.reps)
    for i in range(cfg.reps):
        sh = int(rng.integers(mem, na - mem))
        RR = {h: np.roll(RA[h], sh, axis=0) for h in HOLDS_H}
        FF = {h: np.roll(FA[h], sh, axis=0) for h in HOLDS_H}
        b = bS = bL = -9e9
        for (h, nm) in keys:
            L, S = legs(*MSK[(h, nm)], RR[h], FF[h])
            if len(L) >= cfg.min_times:
                b = max(b, float((L-S).mean()) - FEE2)
                bL = max(bL, float(L.mean()) - FEE1)
                bS = max(bS, float(-S.mean()) - FEE1)
        nl[i], nL[i], nS[i] = b, bL, bS
        if (i+1) % 100 == 0:
            log.info("위약 %d/%d · %.1f분", i+1, cfg.reps, (time.time()-t0)/60)
    pm = float((nl >= obs).mean()); pS = float((nS >= obsS).mean())
    pL = float((nL >= obsL).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(keys)}칸 · **펀딩 포함**)")
    print(f"  스프레드 관측 {obs:+.4f}% · 귀무 중앙 {np.median(nl):+.4f}% "
          f"· 95분위 {np.quantile(nl,.95):+.4f}%  **p = {pm:.3f}**")
    print(f"  롱 다리  관측 {obsL:+.4f}% · 귀무 중앙 {np.median(nL):+.4f}% "
          f"· 95분위 {np.quantile(nL,.95):+.4f}%  **p = {pL:.3f}**")
    print(f"  숏 다리  관측 {obsS:+.4f}% · 귀무 중앙 {np.median(nS):+.4f}% "
          f"· 95분위 {np.quantile(nS,.95):+.4f}%  **p = {pS:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "xsec_funding.csv", index=False)
    (OUT / "xsec_funding.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "p_long": pL, "p_short": pS, "reps": cfg.reps,
         "anchors": int(na), "cells": len(keys),
         "null_median": float(np.median(nl)),
         "funding_symbols": fstat["종목"]}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
