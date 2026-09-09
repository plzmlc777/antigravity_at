"""탄성저울 선별 규칙 격자 — **방향 확인을 넣으면 나아지는가** (2026-09-09).

## 물음 (대표님)

    현행: 거래대금 대비 **가격이 안 움직인**(imp 최저) 3종목을 숏.
    제안: 가격이 **이미 반대로 움직인**(꺾인) 종목을 고르는 편이 낫지 않은가.

## 왜 사후 분류로는 답이 안 되나

이미 뽑힌 3종목을 방향으로 갈라 보는 것은 **선별을 바꾼 효과를 못 본다**
(교훈#108 — 선택 단계의 미래참조와 같은 자리의 함정). 규칙을 바꾸면 **다른
종목이 뽑히므로** 선별부터 다시 돌려야 한다.

## 기질

`runs/bars1m/<종목>/<UTC날짜>.parquet` — 522종목 · 2026-08-26~09-09 · 561MB.
**엔진과 같은 1분봉**이라 교훈#108(접으면 신호가 달라진다)을 피한다.
REST 는 쓰지 않는다(교훈#111).

## 커널은 하나

진입·손절·만기·수수료를 한 함수(`simulate`)가 처리하고 변형은 **선별 함수만**
바꾼다. 갈래마다 딴 커널을 쓰면 비교가 깨진다(하네스 규칙 ⑤).

## 관측 단위는 **날**

한 날의 거래는 같은 시장을 공유한다. 날 묶음 수익 하나가 관측 하나다.

## 판정

격자를 뒤지므로 **최대통계량**(교훈#95). 섞은 자료로 같은 격자를 매번 다시
전부 뒤진 최고값이 기준선이다.

사용:
    python3 -m scripts.research.imp_direction_grid --smoke      # 2일
    python3 -m scripts.research.imp_direction_grid --perm 200
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
log = logging.getLogger("impdir")


@dataclass
class Cfg:
    bars: str = "runs/bars1m"
    out: str = "runs/research_track/imp_direction_grid"
    # ── 엔진과 같은 값 (kinematics_paper.py 에서 옮겨 적음)
    slots: int = 3
    hold_min: int = 480
    stop_pct: float = 5.0
    fee_rt: float = 0.072              # 왕복(%)
    cycle_min: int = 5
    imp_win: int = 60                  # ai 이동평균 창
    imp_med: int = 1440                # 하루 후행 중앙값
    imp_med_min: int = 360
    need_bars: int = 1500              # signal_now 의 imp 요구량
    min_live: float = 5.0              # 분당 체결 수 중앙 하한
    # ── 격자
    conf_k: tuple = (5, 15, 30)        # 방향 확인 창(분)
    pool_n: tuple = (10, 20)           # 방향 우선에서 imp 하위 몇 개를 볼지
    n_perm: int = 200
    seed: int = 20260909


# ── 선별 규칙 ─────────────────────────────────────────────
# 전부 (imp, ret_k, 유효마스크) 를 받아 **숏 대상 인덱스 배열**을 돌려준다.
def pick_base(imp, rets, ok, c: Cfg, k=None, n=None):
    """현행 — imp 최저."""
    idx = np.flatnonzero(ok)
    return idx[np.argsort(imp[idx])]


def pick_confirm(imp, rets, ok, c: Cfg, k=5, n=None):
    """imp 최저 순이되 **직전 k분 수익 < 0** 인 것만."""
    m = ok & (rets[k] < 0)
    idx = np.flatnonzero(m)
    return idx[np.argsort(imp[idx])]


def pick_dirfirst(imp, rets, ok, c: Cfg, k=5, n=10):
    """imp 하위 n 개를 추린 뒤 **직전 k분 수익이 가장 낮은** 순."""
    idx = np.flatnonzero(ok)
    if len(idx) == 0:
        return idx
    idx = idx[np.argsort(imp[idx])][:n]
    return idx[np.argsort(rets[k][idx])]


def pick_dironly(imp, rets, ok, c: Cfg, k=5, n=None):
    """대조군 — imp 를 **무시**하고 직전 k분 수익 최저 순."""
    idx = np.flatnonzero(ok)
    return idx[np.argsort(rets[k][idx])]


_RNG = np.random.default_rng(20260909)


def pick_random(imp, rets, ok, c: Cfg, k=None, n=None):
    """무작위 대조군 — 관문만 통과하면 아무나. **하락장 효과**를 잰다.

    이 창(2026-08~09)은 알트가 약했다. 무작위 숏도 벌면 규칙이 아니라
    장세다(교훈#85 계열)."""
    idx = np.flatnonzero(ok)
    return _RNG.permutation(idx)


VARIANTS = [("현행 imp", pick_base, None, None)]


def build_grid(c: Cfg):
    """격자 전문을 만든다 — 설정에서 유도한다(하네스 규칙 ④)."""
    g = [("현행 imp", pick_base, None, None)]
    for k in c.conf_k:
        g.append((f"확인 k={k}", pick_confirm, k, None))
    for n in c.pool_n:
        for k in c.conf_k:
            g.append((f"방향우선 n={n} k={k}", pick_dirfirst, k, n))
    for k in c.conf_k:
        g.append((f"대조 방향만 k={k}", pick_dironly, k, None))
    g.append(("대조 무작위 숏", pick_random, None, None))
    return g


# ── 기질 적재 ─────────────────────────────────────────────
def load_panel(c: Cfg, days: int = 0):
    """(시각격자, 종목, 행렬들). 행렬은 [분 × 종목] float32."""
    base = ROOT / c.bars
    syms = sorted(p.name for p in base.iterdir() if p.is_dir())
    files = sorted({f.name for s in syms[:5] for f in (base / s).glob("*.parquet")})
    if days:
        files = files[-days - 2:]          # 워밍업 여유 2일
    log.info("종목 %d · 날짜 %d개 (%s ~ %s)", len(syms), len(files),
             files[0][:10], files[-1][:10])

    mats, kept = {}, []
    t0 = time.time()
    for i, s in enumerate(syms, 1):
        fs = [base / s / f for f in files if (base / s / f).exists()]
        if not fs:
            continue
        try:
            d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
        except Exception:                                       # noqa: BLE001
            continue
        if "qv" not in d or "ntr" not in d or len(d) < c.need_bars // 2:
            continue
        d = d.sort_values("ts_ms").drop_duplicates("ts_ms")
        kept.append((s, d))
        if i % 100 == 0:
            log.info("  적재 %d/%d · %.0f초", i, len(syms), time.time() - t0)
    if not kept:
        raise SystemExit("봉을 하나도 못 읽었다")

    lo = min(int(d.ts_ms.iloc[0]) for _, d in kept)
    hi = max(int(d.ts_ms.iloc[-1]) for _, d in kept)
    grid = np.arange(lo, hi + 60_000, 60_000)
    nT, nS = len(grid), len(kept)
    log.info("시각 격자 %d분 · 종목 %d — 행렬 %.0f MB/칸",
             nT, nS, nT * nS * 4 / 1e6)

    C = np.full((nT, nS), np.nan, np.float32)
    H = np.full((nT, nS), np.nan, np.float32)
    L = np.full((nT, nS), np.nan, np.float32)
    IMP = np.full((nT, nS), np.nan, np.float32)
    LIVE = np.full((nT, nS), np.nan, np.float32)
    AGE = np.zeros((nT, nS), np.int32)

    pos = {t: k for k, t in enumerate(grid)}
    for j, (s, d) in enumerate(kept):
        ix = np.array([pos[int(t)] for t in d.ts_ms], int)
        cl = d.cl.to_numpy(float)
        C[ix, j] = cl
        # ⚠ bars1m 에는 고가·저가가 없다(ts_ms·cl·qv·ntr·…). **엔진도 손절을
        #   종가로 판정한다**(`hi10 = 최근 10봉 종가의 최대`) — 그대로 맞춘다.
        H[ix, j] = cl
        L[ix, j] = cl
        # 빈 분은 종가 ffill — tickbars.finalize 와 같은 규약
        col = pd.Series(C[:, j]).ffill()
        C[:, j] = col.to_numpy(np.float32)
        H[:, j] = pd.Series(H[:, j]).fillna(col).to_numpy(np.float32)
        L[:, j] = pd.Series(L[:, j]).fillna(col).to_numpy(np.float32)
        # imp — 엔진 수식 그대로
        qv = np.zeros(nT)
        qv[ix] = d.qv.to_numpy(float)
        ntr = np.zeros(nT)
        ntr[ix] = d.ntr.to_numpy(float)
        cc = C[:, j].astype(float)
        ar = np.abs(np.diff(np.log(np.maximum(cc, 1e-12)), prepend=np.nan)) * 100.0
        ai = pd.Series(ar / np.maximum(qv, 1e-9)).rolling(c.imp_win).mean()
        med = ai.rolling(c.imp_med, min_periods=c.imp_med_min).median().shift(1)
        IMP[:, j] = (ai / med.where(med > 0)).to_numpy(np.float32)
        LIVE[:, j] = pd.Series(ntr).rolling(60).median().shift(1).to_numpy(np.float32)
        AGE[:, j] = np.arange(nT) - ix[0]
    log.info("적재 완료 %.0f초", time.time() - t0)
    return grid, [s for s, _ in kept], dict(C=C, H=H, L=L, IMP=IMP,
                                            LIVE=LIVE, AGE=AGE)


# ── 커널 — 변형이 무엇이든 여기만 지난다 ──────────────────
def simulate(M: dict, grid: np.ndarray, c: Cfg, pick, k, n,
             imp_over: np.ndarray | None = None,
             short: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """(날별 자본수익%, 날). `short=False` 는 **거울 대조군**(교훈#91)."""
    C, H, IMP, LIVE, AGE = M["C"], M["H"], (imp_over if imp_over is not None
                                            else M["IMP"]), M["LIVE"], M["AGE"]
    nT, nS = C.shape
    hold, st = c.hold_min, c.stop_pct / 100.0
    open_end = np.full(nS, -1, np.int64)      # 종목별 보유 종료 분(−1이면 없음)
    open_px = np.zeros(nS)
    n_open = 0
    day = pd.to_datetime(grid, unit="ms", utc=True).tz_convert("Asia/Seoul").date
    per_day: dict = {}
    rets = {kk: np.full(nS, np.nan, np.float32) for kk in c.conf_k}
    for t in range(c.need_bars, nT, c.cycle_min):
        # ① 만기·손절 청산
        for j in np.flatnonzero(open_end >= 0):
            if open_end[j] > t:
                continue
            e = open_px[j]
            seg = C[max(0, int(open_end[j]) - hold):int(open_end[j]) + 1, j]
            adverse = (np.nanmax(seg) / e - 1) if short else (1 - np.nanmin(seg) / e)
            if np.isfinite(adverse) and adverse >= st:
                r = -c.stop_pct
            else:
                x = C[min(int(open_end[j]), nT - 1), j]
                r = (100.0 * (e - x) / e) if short else (100.0 * (x - e) / e)
            per_day.setdefault(day[t], []).append(float(r) - c.fee_rt)
            open_end[j] = -1
            n_open -= 1
        free = c.slots - n_open
        if free <= 0:
            continue
        # ② 후보 — 엔진과 같은 관문
        ok = (np.isfinite(IMP[t]) & (LIVE[t] >= c.min_live)
              & (AGE[t] >= c.need_bars) & (open_end < 0) & np.isfinite(C[t]))
        if not ok.any():
            continue
        for kk in c.conf_k:
            prev = C[max(0, t - kk)]
            rets[kk] = np.where(prev > 0, 100.0 * (C[t] / prev - 1.0), np.nan)
        order = pick(IMP[t], rets, ok, c, k, n)
        for j in order[:free]:
            open_end[j] = t + hold
            open_px[j] = C[t, j]
            n_open += 1
    days = sorted(per_day)
    out = np.array([np.sum(per_day[d]) / c.slots for d in days], float)
    return out, np.array(days)


def tstat(x: np.ndarray) -> float:
    if len(x) < 5 or np.std(x, ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="예비비행 — 2일")
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--perm", type=int, default=0)
    a = ap.parse_args()
    c = Cfg(n_perm=a.perm)
    days = 2 if a.smoke else a.days
    grid_cells = build_grid(c)
    log.info("설정 — 격자 %d칸 · 슬롯 %d · 보유 %d분 · 손절 %.1f%% · 통행료 %.3f%% "
             "· 사이클 %d분 · 유동성 %.1f · 요구봉 %d · 위약 %d회",
             len(grid_cells), c.slots, c.hold_min, c.stop_pct, c.fee_rt,
             c.cycle_min, c.min_live, c.need_bars, c.n_perm)

    cache = ROOT / c.out / (f"panel_{days or 'all'}.npz")
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        tgrid = z["grid"]
        M = {k: z[k] for k in ("C", "H", "L", "IMP", "LIVE", "AGE")}
        log.info("패널 캐시 사용 — %s", cache.name)
    else:
        tgrid, syms, M = load_panel(c, days)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, grid=tgrid, **M)
        log.info("패널 캐시 저장 — %s", cache.name)
    rows = []
    for name, fn, k, n in grid_cells:
        r, dy = simulate(M, tgrid, c, fn, k, n)
        if len(r) < 3:
            continue
        rows.append({"갈래": name, "날": len(r), "일평균%": r.mean(),
                     "합%": r.sum(), "t": tstat(r),
                     "양수일%": 100 * (r > 0).mean()})
    obs = pd.DataFrame(rows).sort_values("t", ascending=False)
    d = ROOT / c.out
    d.mkdir(parents=True, exist_ok=True)
    obs.to_csv(d / "observed.csv", index=False)
    (d / "config.json").write_text(json.dumps(asdict(c), ensure_ascii=False,
                                              indent=1, default=list))
    print(f"\n■ 관측 — {len(obs)}칸 · 날 {rows[0]['날'] if rows else 0}")
    print(obs.round(4).to_string(index=False))

    # ── 거울 대조군 (교훈#91) — 같은 선별, **반대 방향**으로 거래한다.
    #   숏이 번 것이 규칙 때문인지 그냥 하락장인지를 가른다. 두 방향 합이
    #   −2×통행료 근처면 규칙에 정보가 없다.
    mrows = []
    for name, fn, k, n in grid_cells:
        r, _ = simulate(M, tgrid, c, fn, k, n, short=False)
        if len(r) >= 3:
            mrows.append({"갈래": name, "거울(롱) 일평균%": r.mean(),
                          "거울 t": tstat(r)})
    mir = pd.DataFrame(mrows)
    j = obs.merge(mir, on="갈래")
    j["숏+롱"] = j["일평균%"] + j["거울(롱) 일평균%"]
    print(f"\n■ 거울 대조군 — 숏+롱 합이 {-2*c.fee_rt:.3f} 근처면 정보 없음")
    print(j[["갈래", "일평균%", "거울(롱) 일평균%", "숏+롱", "t", "거울 t"]]
          .round(3).to_string(index=False))
    j.to_csv(d / "observed_with_mirror.csv", index=False)

    if c.n_perm <= 0:
        return
    rng = np.random.default_rng(c.seed)
    nT, nS = M["IMP"].shape
    null = []
    t1 = time.time()
    for j in range(c.n_perm):
        # ⚠ 종목별 원형회전. imp 만 돌리면 **`대조 방향만` 칸에는 귀무가 안
        #   걸린다**(그 칸은 imp 를 안 쓴다). 가격·imp·유동성을 **같은 옵셋으로
        #   함께** 돌려 종목 내부 정합은 지키고 종목 간·날짜 정렬만 끊는다.
        MS = {kk: M[kk].copy() for kk in ("C", "H", "L", "IMP", "LIVE")}
        for s in range(nS):
            k_ = int(rng.integers(1, max(nT - 1, 2)))
            for kk in MS:
                MS[kk][:, s] = np.roll(M[kk][:, s], k_)
        MS["AGE"] = M["AGE"]
        best = -1e9
        for name, fn, k, n in grid_cells:
            r, _ = simulate(MS, tgrid, c, fn, k, n)
            if len(r) >= 3:
                best = max(best, tstat(r))
        null.append(best)
        if (j + 1) % 5 == 0:
            el = time.time() - t1
            log.info("  위약 %d/%d · %.1f분 · 남은 %.1f분", j + 1, c.n_perm,
                     el / 60, el / 60 * (c.n_perm - j - 1) / (j + 1))
            np.save(d / "null_partial.npy", np.asarray(null))
    null = np.asarray(null)
    om = float(obs.t.iloc[0])
    pv = float((null >= om).mean())
    print(f"\n■ 최대통계량 (원형회전 {c.n_perm}회 · 같은 {len(grid_cells)}칸)")
    print(f"  관측 최고 t {om:.3f} ({obs.갈래.iloc[0]})")
    print(f"  귀무 최고 t 중앙 {np.median(null):.3f} · 90%% {np.quantile(null,0.9):.3f}"
          f" · 최대 {null.max():.3f}")
    print(f"  **p = {pv:.3f}**")
    np.save(d / "null_max_t.npy", null)
    (d / "verdict.json").write_text(json.dumps(
        {"obs_max_t": om, "best": obs.갈래.iloc[0], "p": pv,
         "n_perm": c.n_perm, "n_cells": len(grid_cells)},
        ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
