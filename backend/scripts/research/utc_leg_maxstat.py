"""UTC 시각×다리 격자의 **최대통계량** 판정 (2026-09-08).

## 왜 만드나

`utc_hour_xsec.py` 는 48칸(24시각 × 2방향)을 뒤졌고 전부 음수였다. 그 뒤
대표님 질문("슬롯 10개 말고 1개면?")을 따라 **다리 수와 롱/숏 다리**까지
뒤졌더니 01시·숏·1종목에서 t +3.16 이 나왔다.

그건 그 자체로 근거가 아니다. 나는 이제 **24시각 × {롱,숏} × 다리 4종 = 192칸**
을 뒤졌고, 뒤진 격자의 최고 t 는 **같은 격자를 섞은 자료로 다시 전부 뒤진 최고
t** 와 비교해야 한다(교훈#95). 칸별 위약은 이미 선택된 칸이라 통과한다.

## 귀무 — 두 가지를 다 돌린다

`rotate` (기본) `utc_hour_xsec.py` 와 같은 방식. 종목별 원형회전으로
        신호↔미래 대응을 시간 축에서 끊는다. 종목 고유의 수익 분포·
        변동성·꼬리는 그대로 둔다.

`cross`  **교차자산 위약**(교훈#93). 날 안에서 (미래·저가·고가) 묶음을
        종목끼리 섞는다 — 1순위 자리에 **무작위 종목의 미래**가 붙는다.
        그 날의 횡단면 수익 분포·후보 수·시장 상황은 그대로다. 끊기는 것은
        "이 종목이 올랐다"와 "이 종목을 판다"의 연결뿐이다.

        이 위약을 못 이기면 번 것은 신호가 아니라 **그 시각에 아무 알트나
        숏 친 것**이다.

## 관측 단위는 날

한 날의 다리들은 같은 2시간을 공유한다. 날 묶음 수익 하나가 관측 하나다.

사용:
    python3 -m scripts.research.utc_leg_maxstat --smoke      # 예비비행
    python3 -m scripts.research.utc_leg_maxstat --perm 200   # 본실행
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("utc_leg")


# ── 설정은 이 하나뿐이다 (하네스 규칙 ①)
@dataclass
class Cfg:
    panel: str = "runs/research_track/utc_hour_xsec/panel_all.parquet"
    out: str = "runs/research_track/utc_leg_maxstat"
    stop_pct: float = 5.0
    fee_rt: float = 0.072               # **왕복**(%)
    min_cand: int = 30                  # 하루 후보 종목 하한 (교훈#99)
    hours: tuple = tuple(range(24))
    sides: tuple = ("L", "S")           # 롱 다리 · 숏 다리
    n_sides: tuple = (1, 2, 3, 5)
    n_perm: int = 200
    seed: int = 20260908
    null: str = "rotate"                # rotate | cross (교훈#93)

    @property
    def n_cells(self) -> int:
        return len(self.hours) * len(self.sides) * len(self.n_sides)


def leg_daily(day_s, sig_s, fwd_s, lo_s, hi_s, side: str, n: int,
              stop: float, fee: float) -> np.ndarray:
    """한 칸의 날별 수익(%). day 는 이미 (day, sig) 로 정렬돼 있어야 한다."""
    b = np.flatnonzero(np.r_[True, day_s[1:] != day_s[:-1], True])
    out = np.empty(len(b) - 1, dtype=float)
    m = 0
    for a, e in zip(b[:-1], b[1:]):
        if e - a < 2 * n + 10:          # 후보가 얇은 날은 건너뛴다
            continue
        if side == "S":                 # 가장 오른 n 종목을 숏
            i = np.arange(e - n, e)
            r = np.where(hi_s[i] >= stop, -stop, -fwd_s[i])
        else:                           # 가장 떨어진 n 종목을 롱
            i = np.arange(a, a + n)
            r = np.where(lo_s[i] <= -stop, -stop, fwd_s[i])
        out[m] = (r * 100.0 - fee).mean()
        m += 1
    return out[:m]


def tstat(x: np.ndarray) -> float:
    if len(x) < 30 or np.std(x, ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def sweep(pre: dict, c: Cfg, fwd=None, lo=None, hi=None,
          over: dict | None = None) -> pd.DataFrame:
    """192칸 전부. 같은 커널을 지난다(하네스 규칙 ⑤).

    `over` 가 오면 **시각별로 이미 정렬된** (미래·저·고) 를 그대로 쓴다 —
    교차자산 위약이 날 안에서 섞은 결과를 넘길 때 쓴다."""
    st = c.stop_pct / 100.0
    rows = []
    for h, g in pre.items():
        o = g["order"]
        if over is not None:
            f, l, k = over[h]
        else:
            f = (g["fwd"] if fwd is None else fwd[g["idx"]][o])
            l = (g["lo"] if lo is None else lo[g["idx"]][o])
            k = (g["hi"] if hi is None else hi[g["idx"]][o])
        for side in c.sides:
            for n in c.n_sides:
                x = leg_daily(g["day"], g["sig"], f, l, k, side, n, st, c.fee_rt)
                if len(x) < 200:
                    continue
                rows.append({"hour": h, "side": side, "n_side": n,
                             "days": len(x), "평균%": x.mean(),
                             "중앙%": float(np.median(x)), "t": tstat(x)})
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="예비비행 — 3시각·5회")
    ap.add_argument("--perm", type=int, default=200)
    ap.add_argument("--hours", default="")
    ap.add_argument("--null", choices=("rotate", "cross"), default="rotate",
                    help="rotate=종목별 원형회전 · cross=교차자산(교훈#93)")
    a = ap.parse_args()

    c = Cfg(n_perm=a.perm, null=a.null)
    if a.smoke:
        c = Cfg(hours=(0, 1, 2), n_perm=5, null=a.null)
    if a.hours:
        c = Cfg(hours=tuple(int(x) for x in a.hours.split(",")),
                n_perm=a.perm, null=a.null)
    log.info("설정 — 격자 %d칸 (시각 %d × 다리방향 %d × 다리수 %d) · 위약 %s %d회 "
             "· 손절 %.1f%% · 통행료 %.3f%% · 후보하한 %d",
             c.n_cells, len(c.hours), len(c.sides), len(c.n_sides),
             c.null, c.n_perm, c.stop_pct, c.fee_rt, c.min_cand)

    p = pd.read_parquet(ROOT / c.panel)
    log.info("패널 %d행 · 종목 %d · %s~%s",
             len(p), p.sym.nunique(), p.day.min().date(), p.day.max().date())

    # 커버리지 하한 — 하루 후보가 얇으면 '순위 뽑기'가 전종목이 된다(교훈#99)
    k = p.groupby(["day", "hour"]).sym.transform("size")
    p = p[k >= c.min_cand].reset_index(drop=True)
    log.info("후보 %d종목 이상만 남김 — %d행", c.min_cand, len(p))

    # 시각별로 (day, sig) 정렬을 **한 번만** 해 둔다
    pre = {}
    for h in c.hours:
        m = (p.hour == h).to_numpy()
        if m.sum() == 0:
            continue
        idx = np.flatnonzero(m)
        g = p.iloc[idx]
        o = np.lexsort((g.sig.to_numpy(), g.day.to_numpy()))
        dsort = g.day.to_numpy()[o]
        pre[h] = {"idx": idx, "order": o,
                  "day": dsort, "sig": g.sig.to_numpy()[o],
                  "fwd": g.fwd.to_numpy()[o], "lo": g.lo_r.to_numpy()[o],
                  "hi": g.hi_r.to_numpy()[o],
                  # 날 경계 — 교차자산 위약은 **이 안에서만** 섞는다
                  "bnd": np.flatnonzero(
                      np.r_[True, dsort[1:] != dsort[:-1], True])}

    obs = sweep(pre, c).sort_values("t", ascending=False)
    d = ROOT / c.out / c.null
    d.mkdir(parents=True, exist_ok=True)
    obs.to_csv(d / "observed.csv", index=False)
    (d / "config.json").write_text(json.dumps(asdict(c), ensure_ascii=False,
                                              indent=1, default=list))
    print("\n■ 관측 — %d칸 중 상위 10" % len(obs))
    print(obs.head(10).round(4).to_string(index=False))
    print("  t>0 %d칸 · t>2 %d칸 · 중앙 t %.2f"
          % ((obs.t > 0).sum(), (obs.t > 2).sum(), obs.t.median()))

    # 귀무 — 종목별 원형회전 (utc_hour_xsec 와 같은 방식)
    rng = np.random.default_rng(c.seed)
    fwd, lo, hi = p.fwd.to_numpy(), p.lo_r.to_numpy(), p.hi_r.to_numpy()
    codes = pd.Categorical(p.sym).codes
    order = np.argsort(codes, kind="stable")
    bnd = np.flatnonzero(np.r_[True, codes[order][1:] != codes[order][:-1], True])
    null, t1 = [], time.time()
    for j in range(c.n_perm):
        if c.null == "cross":
            # 교차자산 — **날 안에서** 종목끼리 (미래·저·고) 를 통째로 섞는다.
            # 순위 자리는 그대로 두고 그 자리에 앉는 종목의 미래만 바뀐다.
            over = {}
            for h, g in pre.items():
                f2 = g["fwd"].copy(); l2 = g["lo"].copy(); h2 = g["hi"].copy()
                b = g["bnd"]
                for x, y in zip(b[:-1], b[1:]):
                    if y - x < 3:
                        continue
                    q = rng.permutation(y - x) + x
                    f2[x:y] = g["fwd"][q]
                    l2[x:y] = g["lo"][q]
                    h2[x:y] = g["hi"][q]
                over[h] = (f2, l2, h2)
            t = sweep(pre, c, over=over).t.to_numpy()
        else:
            f2, l2, h2 = fwd.copy(), lo.copy(), hi.copy()
            for x, y in zip(bnd[:-1], bnd[1:]):
                i = order[x:y]
                if len(i) < 3:
                    continue
                s = int(rng.integers(1, len(i) - 1))
                f2[i] = np.roll(fwd[i], s)
                l2[i] = np.roll(lo[i], s)
                h2[i] = np.roll(hi[i], s)
            t = sweep(pre, c, f2, l2, h2).t.to_numpy()
        null.append(float(np.nanmax(t)))
        if (j + 1) % 10 == 0:
            el = time.time() - t1
            log.info("  위약 %d/%d · %.1f분 · 남은 %.1f분", j + 1, c.n_perm,
                     el / 60, el / 60 * (c.n_perm - j - 1) / (j + 1))
            np.save(d / "null_max_t_partial.npy", np.asarray(null))

    null = np.asarray(null)
    obs_max = float(obs.t.iloc[0])
    pv = float((null >= obs_max).mean())
    top = obs.iloc[0]
    nm = {"rotate": "원형회전", "cross": "교차자산(교훈#93)"}[c.null]
    print("\n■ 최대통계량 (%s %d회 · 같은 %d칸을 매번 다시 뒤짐)"
          % (nm, c.n_perm, c.n_cells))
    print("  관측 최고 t  %.3f  (시각 %d · %s 다리 · %d종목)"
          % (obs_max, top.hour, top.side, top.n_side))
    print("  귀무 최고 t  중앙 %.3f · 90%% %.3f · 최대 %.3f"
          % (np.median(null), np.quantile(null, 0.9), null.max()))
    print("  **p = %.3f**" % pv)
    np.save(d / "null_max_t.npy", null)
    (d / "verdict.json").write_text(json.dumps(
        {"null_kind": c.null, "obs_max_t": obs_max, "p": pv,
         "n_perm": c.n_perm,
         "n_cells": c.n_cells, "best_hour": int(top.hour),
         "best_side": str(top.side), "best_n_side": int(top.n_side),
         "null_med": float(np.median(null)), "null_max": float(null.max())},
        ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
