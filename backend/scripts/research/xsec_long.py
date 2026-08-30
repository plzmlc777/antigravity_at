"""횡단면 축 — **2년 기질**로 다시 건다. 틱 4.3일이 아니라.

## 왜 (2026-08-30 밤, 대표님 지시)

교훈#109 — 여섯 축 전부 틱 4.3일(비겹침 블록 **48개**)에서 기각됐는데
그건 기각이 아니라 **측정 불가**였다. 회전 위약만으로 총손익 ±3% 가 나오는
창에서 관측 +3% 는 아무것도 아니다. `ohlcv_1m` 은 2년(블록 9,017)이다.

여기서 다루는 축(전부 **종가만** 필요 — 기질 요구를 먼저 적는다):

    A  보유 지평 × 신호      틱 판정 p 0.534
    D  횡단면 단기 되돌림    틱 판정 0/50 칸 마찰 돌파
    E  충격 되돌림(문턱)     틱 판정 엣지 1bp

⚠ 주문 흐름 불균형은 `ohlcv_1m` 에 체결방향이 없어 **이식하지 않는다**.
  대체 변수를 만들면 다른 것을 재게 된다.

## 규약

  · 앵커는 **1시간 격자**. 지평 h 는 그 부분집합을 비겹침으로 쓴다
  · 통계량 = 시각마다 상·하위 분위 스프레드 → 시각 가중 평균 → 시각 클러스터 t
  · 회전 위약 **최대통계량**, 시프트 하한 = 신호 기억 (교훈#108)
  · 회차당 종목이 아니라 **판 전체를 한 번** 민다(횡단면 구조 보존)
  · 마찰 왕복 0.072%(롱·숏 두 다리)
  · **비겹침 시각 수를 칸마다 적는다** — 못 재는 칸을 격자에 넣지 않는다

사용:
  python3 -m scripts.research.xsec_long --smoke 40 --reps 20
  python3 -m scripts.research.xsec_long --reps 1000
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
log = logging.getLogger("xsec")

BAR = 5                       # 봉 길이(분)
ANCH = 12                     # 앵커 격자 = 1시간
HOLDS_H = (1, 2, 4, 8, 12, 24, 48)      # 보유(시간)
# ⚠ **진입 지연**(봉). 급변 되돌림은 호가 튐의 교과서적 함정이다 — 5분 최대
#   급락 종목의 마지막 체결가는 매도호가 쪽에 붙어 있어 그 가격에 살 수 없다.
#   틱 세션에서 이 축이 죽은 이유가 정확히 그것이었다. 한 봉(5분)·두 봉(10분)
#   늦춰 들어가도 남는지 본다. 사라지면 튐이고, 남으면 진짜다.
DELAYS = (0, 1, 2)
Q = 0.2
FEE2 = 0.072                  # 왕복 두 다리


@dataclass(frozen=True)
class Cfg:
    min_syms: int = 20        # 이보다 종목이 적은 시각은 버린다
    min_times: int = 30       # 이보다 시각이 적은 칸은 **격자에서 뺀다**
    min_bars_in_5: float = 3.0
    reps: int = 1_000
    seed: int = 20260831


def load(files, cfg: Cfg):
    """5분봉 캐시 → 공통 시간축의 (시각 × 종목) 판. float32 로 든다."""
    cl, hi, lo, nb = {}, {}, {}, {}
    for f in files:
        d = pd.read_parquet(f)
        if len(d) < 5_000:
            continue
        ts = pd.to_datetime(d.ts, utc=True)
        s = f.stem
        cl[s] = pd.Series(d.c.to_numpy(np.float32), index=ts)
        hi[s] = pd.Series(d.h.to_numpy(np.float32), index=ts)
        lo[s] = pd.Series(d.l.to_numpy(np.float32), index=ts)
        nb[s] = pd.Series(d.n.to_numpy(np.float32), index=ts)
    idx = pd.date_range(min(v.index.min() for v in cl.values()),
                        max(v.index.max() for v in cl.values()),
                        freq=f"{BAR}min", tz="UTC")
    CL = pd.DataFrame(cl).reindex(idx).ffill()
    HI = pd.DataFrame(hi).reindex(idx).ffill()
    LO = pd.DataFrame(lo).reindex(idx).ffill()
    NB = pd.DataFrame(nb).reindex(idx).fillna(0.0)
    return CL, HI, LO, NB, idx


def signals(CL, HI, LO, NB, cfg: Cfg):
    """신호와 **각자의 기억 길이(봉)** 를 함께 돌려준다 — 위약 시프트에 쓴다."""
    S: dict[str, tuple[np.ndarray, int]] = {}
    lr = np.log(CL).diff()
    live = (NB.rolling(12).median().shift(1) >= cfg.min_bars_in_5).to_numpy()

    def put(name, mat, mem):
        S[name] = (np.where(live, np.asarray(mat, np.float32), np.nan), mem)

    # ── 되돌림 계열 (부호를 뒤집어 **큰 값 = 롱** 으로 통일)
    for h, k in (("1h", 12), ("4h", 48), ("24h", 288)):
        r = (CL / CL.shift(k) - 1.0) * 100.0
        put(f"되돌림{h}", -r, k)
        sd = lr.rolling(k).std() * np.sqrt(k) * 100.0
        put(f"변동조정되돌림{h}", -(r / (sd + 1e-9)), 2 * k)
    # ── 운동학 (동결 신호) — 창 72 · 간격 36 · 지평 12
    fw = CL.shift(-12) / CL - 1.0
    win = (fw > 0).astype(float).where(fw.notna())
    rate = win.rolling(72, min_periods=36).mean().shift(12)
    vel = rate - rate.shift(36)
    p_ = rate.clip(0.01, 0.99)
    se = np.sqrt(p_ * (1 - p_) / 6.0)
    put("z_vel", -(vel / (se * np.sqrt(2))), 72 + 36 + 12)
    # ── 충격: 한 봉 급변의 크기(절대 문턱은 칸에서 자른다)
    r1 = (CL / CL.shift(1) - 1.0) * 100.0
    put("충격1봉", -r1, 1)
    put("충격3봉", -((CL / CL.shift(3) - 1.0) * 100.0), 3)
    return S


def masks(X: np.ndarray, pos: np.ndarray, cfg: Cfg):
    """상·하위 분위 **마스크를 한 번만** 만든다.

    ⚠ 분위 경계는 **신호**로 정해지고 신호는 회전에 안 변한다. 그런데 위약
      회차마다 `np.nanquantile` 를 다시 부르면 회당 22초가 되어 1000회에
      6시간이다(실측). 마스크를 미리 만들면 루프에 남는 건 마스크 평균뿐이다.
    """
    x = X[pos]
    fin = np.isfinite(x)
    cnt = fin.sum(1)
    good = cnt >= cfg.min_syms
    if not good.any():
        return None
    x = x[good]
    with np.errstate(invalid="ignore"):
        qs = np.nanquantile(x, [Q, 1.0 - Q], axis=1)
    ok = qs[1] > qs[0]
    x = x[ok]
    lo_, hi_ = qs[0][ok][:, None], qs[1][ok][:, None]
    rows = pos[good][ok]
    return rows, (x >= hi_), (x <= lo_)


def spread(rows, top, bot, R: np.ndarray):
    """마스크 평균의 차. R 만 회차마다 바뀐다."""
    r = R[rows]
    with np.errstate(invalid="ignore"):
        v = (np.nanmean(np.where(top, r, np.nan), axis=1)
             - np.nanmean(np.where(bot, r, np.nan), axis=1))
    return v[np.isfinite(v)]


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
    log.info("설정 %s · 종목 %d", json.dumps(asdict(cfg), ensure_ascii=False), len(fs))

    t0 = time.time()
    CL, HI, LO, NB, idx = load(fs, cfg)
    log.info("판 %s봉 × %d종목 · %s ~ %s · %.1f분", f"{len(CL):,}", CL.shape[1],
             idx.min().date(), idx.max().date(), (time.time()-t0)/60)
    S = signals(CL, HI, LO, NB, cfg)
    log.info("신호 %d종 · %.1f분", len(S), (time.time()-t0)/60)
    CLv = CL.to_numpy(np.float32)
    n = len(CL)
    warm = max(m for _, m in S.values())
    anchors = np.arange(warm, n - max(HOLDS_H) * 12 - 1)
    anchors = anchors[anchors % ANCH == 0]             # 벽시계 1시간 격자
    log.info("앵커 %s개 (1시간 격자)", f"{len(anchors):,}")

    # 앵커 격자로 줄여 든다 — 전 구간을 다 들면 메모리가 안 된다
    XA = {k: v[anchors] for k, (v, _) in S.items()}
    MEM = {k: int(np.ceil(m / ANCH)) for k, (_, m) in S.items()}
    RA = {}
    for h in HOLDS_H:
        k = h * 12
        for d in DELAYS:
            # 신호는 앵커에서, 진입은 d봉 뒤, 청산은 진입 + h시간
            f = np.full(CLv.shape, np.nan, np.float32)
            hi_ = n - k - d
            f[:hi_] = (CLv[d+k:d+k+hi_] / CLv[d:d+hi_] - 1.0) * 100.0
            RA[(h, d)] = f[anchors]
    del S
    na = len(anchors)

    rows, keys, MSK = [], [], {}
    for h in HOLDS_H:
        pos = np.arange(0, na - h - 1, h)          # 앵커 단위 = 비겹침
        for nm in XA:
            mk = masks(XA[nm], pos, cfg)
            if mk is None or len(mk[0]) < cfg.min_times:
                continue
            MSK[(h, nm)] = mk
            for d in DELAYS:
                v = spread(*mk, RA[(h, d)])
                if len(v) < cfg.min_times or v.std(ddof=1) <= 0:
                    continue
                t = v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
                rows.append({"보유h": h, "지연봉": d, "신호": nm,
                             "시각수": len(v), "스프레드": v.mean(),
                             "수수료후": v.mean() - FEE2, "t": t})
                keys.append((h, d, nm))
    R0 = pd.DataFrame(rows)
    import sys as _s; _s.stdout.reconfigure(line_buffering=True)
    print(f"\n■ 횡단면 격자 (시각 가중 · 비겹침 · 마찰 {FEE2}%)")
    print(R0.sort_values("t", key=abs, ascending=False).head(24).to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))

    # ── 회전 위약 최대통계량 ────────────────────────────────
    rng = np.random.default_rng(cfg.seed)
    memmax = max(MEM.values()) + max(HOLDS_H)
    if na <= 2 * memmax:
        raise SystemExit(f"앵커 {na}개가 기억 {memmax}의 두 배가 안 된다")
    obs = float(R0.t.abs().max())
    null = np.empty(cfg.reps)
    for i in range(cfg.reps):
        # ⚠ 판 전체를 **한 번** 민다 — 종목마다 다르게 밀면 횡단면 구조가 깨진다
        sh = int(rng.integers(memmax, na - memmax))
        best = 0.0
        RR = {k: np.roll(v, sh, axis=0) for k, v in RA.items()}
        for (h, d, nm) in keys:
            v = spread(*MSK[(h, nm)], RR[(h, d)])
            if len(v) >= cfg.min_times and v.std(ddof=1) > 0:
                best = max(best, abs(v.mean()/(v.std(ddof=1)/np.sqrt(len(v)))))
        null[i] = best
        if (i+1) % 10 == 0:
            log.info("위약 %d/%d · 귀무중앙 %.2f · %.1f분", i+1, cfg.reps,
                     float(np.median(null[:i+1])), (time.time()-t0)/60)
    pm = float((null >= obs).mean())
    print(f"\n■ 회전 위약 최대통계량 ({cfg.reps}회 · {len(keys)}칸 · 시프트 하한 {memmax}앵커)")
    print(f"  관측 최대 |t| {obs:.2f} · 귀무 중앙 {np.median(null):.2f} "
          f"· 95분위 {np.quantile(null,.95):.2f} · 최대 {null.max():.2f}")
    print(f"  **p = {pm:.3f}**")
    OUT.mkdir(parents=True, exist_ok=True)
    R0.to_csv(OUT / "xsec_long.csv", index=False)
    (OUT / "xsec_long.null.json").write_text(json.dumps(
        {"obs": obs, "p": pm, "reps": cfg.reps, "cells": len(keys),
         "anchors": int(na), "shift_floor": int(memmax),
         "null_median": float(np.median(null)),
         "null_p95": float(np.quantile(null, .95))}, ensure_ascii=False, indent=1))
    log.info("저장 · %.1f분", (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
