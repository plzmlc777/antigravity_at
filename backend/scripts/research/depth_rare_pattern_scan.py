"""희귀 극단 패턴 — "빈도는 적어도 승률이 높은 칸"을 정직하게 찾는다.

왜 따로 만드나
    `depth_signal_scan` 은 **분위 정렬**이라 상위 20%를 강제로 잡는다.
    상위 1%짜리 희귀 패턴은 Q5 안에서 평균에 묻힌다. 그 칸은 아직 안 봤다.

⚠ 이 질문에는 고유한 함정이 있다 — **저빈도·고승률은 과최적화의 모양이다**
    격자를 400칸 뒤지면 우연만으로도 t 3.0 짜리가 나온다. 그래서 이 스크립트의
    본체는 신호 탐색이 아니라 **최대통계량 귀무분포**다:

        관측  = 격자 전체에서 나온 **최고** |t|
        귀무  = 신호를 섞고 **같은 격자를 다시 전부 뒤져서** 나온 최고 |t|

    비교 대상은 "이 칸 vs 0" 이 아니라 **"최고의 칸 vs 우연이 만드는 최고의 칸"**
    이다. 이걸 안 깔면 400칸을 뒤진 사실이 결과에 안 들어간다.

⚠ 두 번째 함정 — **같은 날 여러 종목은 한 사건이다**
    희귀 극단은 시장 전체 스트레스에 몰린다. 10종목이 같은 날 걸리면 거래 10건이
    아니라 사건 1건이다. 날짜로 묶고(cluster), 겹치면 HAC 를 건다.
    [[feedback-lesson-candidate-concentration-temporal-cluster-artifact]]

⚠ 세 번째 함정 — **승률과 수익은 다르다**
    승률 90% 인데 지는 10% 가 크면 진다. 승률만 보지 말고 중앙값·최악·손익비를
    같이 낸다. [[feedback-lesson-81-per-trade-edge-vs-portfolio-survival]]

관문 (전부 통과해야 후보)
    ① 사건 30건 이상  ② 서로 다른 날짜 15일 이상  ③ IS 와 OOS 부호 일치
    ④ 최대통계량 귀무분포 대비 p ≤ 0.05   ⑤ 마찰 차감 후 양수

사용:
  python3 -m scripts.research.depth_rare_pattern_scan --split 2025-06-01
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("rare_scan")

OUT = ROOT / "runs" / "research_track" / "depth_rare_pattern_scan.json"

ZWIN = 30
TAILS = [0.01, 0.02, 0.05, 0.10]
HOLDS = [1, 3, 5, 10, 20]
PAIR_TAIL = 0.10
PAIR_HOLDS = [3, 5, 10]
MIN_EVENTS = 30
MIN_DATES = 15


def nw_t(a: np.ndarray, lags: int) -> float:
    """날짜 평균 계열의 Newey-West t. 표본 부족이면 0."""
    a = a[np.isfinite(a)]
    n = len(a)
    if n < 5:
        return 0.0
    x = a - a.mean()
    var = float(x @ x / n)
    for j in range(1, min(lags, n - 1) + 1):
        var += 2.0 * (1.0 - j / (lags + 1.0)) * float(x[j:] @ x[:-j] / n)
    if var <= 0:
        return 0.0
    return float(a.mean() / np.sqrt(var / n))


def date_means(vals: np.ndarray, dcode: np.ndarray, ndates: int) -> np.ndarray:
    """날짜별 평균 — 같은 날 여러 종목을 **한 사건**으로 접는다."""
    s = np.bincount(dcode, weights=vals, minlength=ndates)
    c = np.bincount(dcode, minlength=ndates)
    m = np.full(ndates, np.nan)
    nz = c > 0
    m[nz] = s[nz] / c[nz]
    return m[nz]


def cell_stat(mask: np.ndarray, ret: np.ndarray, dcode: np.ndarray,
              ndates: int, sign: int, fric: float, lags: int) -> dict | None:
    if mask.sum() < MIN_EVENTS:
        return None
    v = ret[mask] * sign - fric
    dc = dcode[mask]
    nd = len(np.unique(dc))
    if nd < MIN_DATES:
        return None
    dm = date_means(v, dc, ndates)
    return {"n": int(mask.sum()), "n_dates": int(nd),
            "mean": float(v.mean()), "med": float(np.median(v)),
            "win": float(100 * (v > 0).mean()), "worst": float(v.min()),
            "best": float(v.max()),
            "t": nw_t(dm, lags)}


def main() -> int:
    p = argparse.ArgumentParser(description="희귀 극단 패턴 + 최대통계량 위약")
    p.add_argument("--split", required=True)
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--reps", type=int, default=200, help="최대통계량 반복")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    split = pd.Timestamp(datetime.fromisoformat(a.split))
    fric = 2 * a.fee_bp / 100.0

    from sqlalchemy import text

    from app.db.session import engine
    with engine.connect() as conn:
        d = pd.DataFrame(conn.execute(text(
            "SELECT symbol, date, depth1_usd, depth5_bid_usd, depth5_ask_usd, "
            "depth1_imbalance, depth1_bid_cv FROM binance_archive_depth "
            "ORDER BY symbol, date")).fetchall(),
            columns=["symbol", "date", "d1", "d5b", "d5a", "imb", "cv"])
        px = pd.DataFrame(conn.execute(text(
            "SELECT symbol, date, open FROM ohlcv_daily "
            "WHERE is_partial = false ORDER BY symbol, date")).fetchall(),
            columns=["symbol", "date", "open"])
    for f in (d, px):
        f["date"] = pd.to_datetime(f["date"])
    df = px.merge(d, on=["symbol", "date"], how="inner")
    for c in ("open", "d1", "d5b", "d5a", "imb", "cv"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    df["ld1"] = np.log(df["d1"].where(df["d1"] > 0))
    sh = (df["d5b"] + df["d5a"]) / df["d1"].where(df["d1"] > 0)
    df["shape"] = np.log(sh.where(sh > 0))

    def z(col):
        s = df.groupby("symbol", sort=False)[col]
        m = s.transform(lambda x: x.rolling(ZWIN, min_periods=ZWIN).mean())
        sd = s.transform(lambda x: x.rolling(ZWIN, min_periods=ZWIN).std())
        return (df[col] - m) / sd.where(sd > 0)

    df["imb_raw"] = df["imb"]
    df["imb_z"] = z("imb")
    df["depth_z"] = z("ld1")
    df["cv_z"] = z("cv")
    df["shape_z"] = z("shape")
    df["depth_chg"] = df.groupby("symbol", sort=False)["ld1"].transform(
        lambda x: x - x.shift(7))
    SIGS = ["imb_raw", "imb_z", "depth_z", "depth_chg", "cv_z", "shape_z"]

    # ⚠ 신호 t일 → 진입 t+1 시가 → 청산 t+1+H 시가 (교훈 #90)
    po = df.pivot(index="date", columns="symbol", values="open")
    fwds = {}
    for h in set(HOLDS + PAIR_HOLDS):
        m = (po.shift(-(1 + h)) / po.shift(-1) - 1) * 100
        fwds[h] = (m.stack().rename(f"f{h}").reset_index()
                   .set_axis(["date", "symbol", f"f{h}"], axis=1))

    base = df[["date", "symbol"] + SIGS].copy()
    for h, m in fwds.items():
        base = base.merge(m, on=["date", "symbol"], how="left")
    base = base.dropna(subset=SIGS, how="all")
    base["is_oos"] = base["date"] >= split

    dates = np.sort(base["date"].unique())
    dmap = {d: i for i, d in enumerate(dates)}
    base["dcode"] = base["date"].map(dmap).astype(int)
    smap = {s: i for i, s in enumerate(sorted(base["symbol"].unique()))}
    base["scode"] = base["symbol"].map(smap).astype(int)
    ndates = len(dates)

    print("=" * 96)
    print(f"희귀 극단 패턴 — 종목 {base['symbol'].nunique()} · 관측 "
          f"{len(base):,} · 날짜 {ndates:,} · "
          f"{base['date'].min().date()} ~ {base['date'].max().date()}")
    print(f"분할 {a.split} · 마찰 {2*a.fee_bp:.0f}bp · "
          f"관문 사건≥{MIN_EVENTS} · 날짜≥{MIN_DATES}")
    print("=" * 96)

    sig_arr = {s: base[s].to_numpy(dtype=float) for s in SIGS}
    ret_arr = {h: base[f"f{h}"].to_numpy(dtype=float) for h in fwds}
    dcode = base["dcode"].to_numpy()
    scode = base["scode"].to_numpy()
    is_mask = ~base["is_oos"].to_numpy()

    # ── 격자 정의 ─────────────────────────────────────────────────────
    cells = []
    for s, tail, side, h in itertools.product(SIGS, TAILS, (-1, +1), HOLDS):
        cells.append(("single", s, tail, side, h, None, None))
    for (s1, s2), h in itertools.product(itertools.combinations(SIGS, 2),
                                         PAIR_HOLDS):
        for sd1, sd2 in itertools.product((-1, +1), repeat=2):
            cells.append(("pair", s1, PAIR_TAIL, sd1, h, s2, sd2))
    log.info("격자 %d칸 (단일 %d · 결합 %d)", len(cells),
             sum(1 for c in cells if c[0] == "single"),
             sum(1 for c in cells if c[0] == "pair"))

    def tail_mask(v: np.ndarray, tail: float, side: int,
                  ref: np.ndarray) -> np.ndarray:
        """극단 꼬리. **경계는 표본 안에서만** 잡는다 (표본 밖 훔쳐보기 금지)."""
        r = ref[np.isfinite(ref)]
        if len(r) < 200:
            return np.zeros(len(v), dtype=bool)
        if side > 0:
            return np.isfinite(v) & (v >= np.quantile(r, 1 - tail))
        return np.isfinite(v) & (v <= np.quantile(r, tail))

    def eval_grid(sigs_now: dict, split_mask: np.ndarray,
                  collect: bool) -> tuple[float, list]:
        """격자 전체를 돌려 (최고 |t|, 상세) 반환."""
        best, rows = 0.0, []
        for kind, s1, tail, sd1, h, s2, sd2 in cells:
            v1 = sigs_now[s1]
            m = tail_mask(v1, tail, sd1, v1[is_mask])
            if kind == "pair":
                v2 = sigs_now[s2]
                m = m & tail_mask(v2, PAIR_TAIL, sd2, v2[is_mask])
            m = m & split_mask & np.isfinite(ret_arr[h])
            # 방향은 신호 부호를 따라간다 — 꼬리 위쪽이면 롱, 아래쪽이면 숏
            for trade in (+1, -1):
                st = cell_stat(m, ret_arr[h], dcode, ndates, trade, fric,
                               max(0, h - 1))
                if st is None:
                    continue
                if abs(st["t"]) > best:
                    best = abs(st["t"])
                if collect:
                    rows.append({"kind": kind, "sig": s1, "sig2": s2,
                                 "tail": tail, "side": sd1, "side2": sd2,
                                 "hold": h, "trade": trade, **st})
        return best, rows

    # ── 관측 (표본 안) ────────────────────────────────────────────────
    obs_best, rows = eval_grid(sig_arr, is_mask, collect=True)
    if not rows:
        raise SystemExit("관문을 통과한 칸이 하나도 없다 (사건/날짜 부족)")
    R = pd.DataFrame(rows)
    R["absT"] = R["t"].abs()
    R = R.sort_values("absT", ascending=False)

    print(f"\n【1】 표본 안 상위 12칸 (총 {len(R)}칸이 관문 ①② 통과)")
    print(f"  {'신호':<24}{'꼬리':>6}{'보유':>5}{'방향':>5}{'사건':>6}"
          f"{'날짜':>6}{'평균%':>8}{'중앙%':>8}{'승률%':>7}{'최악%':>8}{'t':>7}")
    print("  " + "-" * 92)
    for _, r in R.head(12).iterrows():
        nm = (f"{r['sig']}{'+' if r['side']>0 else '-'}"
              + (f"×{r['sig2']}{'+' if r['side2']>0 else '-'}"
                 if r["kind"] == "pair" else ""))
        print(f"  {nm:<24}{r['tail']*100:>5.0f}%{r['hold']:>5}"
              f"{'롱' if r['trade']>0 else '숏':>5}{r['n']:>6}{r['n_dates']:>6}"
              f"{r['mean']:>8.2f}{r['med']:>8.2f}{r['win']:>7.1f}"
              f"{r['worst']:>8.1f}{r['t']:>7.2f}")

    # ── 최대통계량 귀무분포 ───────────────────────────────────────────
    print(f"\n【2】 최대통계량 귀무분포 — 신호를 섞고 **같은 {len(cells)}칸을 "
          f"다시 전부** 뒤진다 ({a.reps}회)")
    rng = np.random.default_rng(a.seed)
    order = np.argsort(scode, kind="stable")
    bounds = np.searchsorted(scode[order], np.arange(len(smap) + 1))
    nulls = []
    for i in range(a.reps):
        shuffled = {}
        for s in SIGS:
            v = sig_arr[s].copy()
            for k in range(len(smap)):
                idx = order[bounds[k]:bounds[k + 1]]
                v[idx] = rng.permutation(v[idx])   # 종목 안에서 시점만 섞는다
            shuffled[s] = v
        b, _ = eval_grid(shuffled, is_mask, collect=False)
        nulls.append(b)
        if (i + 1) % 50 == 0:
            log.info("  위약 %d/%d · 현재 귀무 최대 t 평균 %.2f",
                     i + 1, a.reps, float(np.mean(nulls)))
    nulls = np.array(nulls)
    pval = float(np.mean(nulls >= obs_best))
    print(f"  관측 최고 |t| **{obs_best:.2f}**  ·  귀무 최고 |t| 평균 "
          f"{nulls.mean():.2f} · p95 {np.percentile(nulls,95):.2f} · "
          f"최대 {nulls.max():.2f}")
    print(f"  **경험 p = {pval:.3f}**  "
          + ("→ 우연이 만드는 최고의 칸과 **구별되지 않는다**"
             if pval > 0.05 else "→ 우연을 넘는다"))

    # ── 표본 밖 확인 ──────────────────────────────────────────────────
    print("\n【3】 표본 밖 — 상위 8칸이 부호를 유지하는가")
    print(f"  {'신호':<24}{'IS평균%':>9}{'IS승률':>8}{'IS t':>7}"
          f"{'OOS사건':>8}{'OOS평균%':>10}{'OOS승률':>9}{'OOS t':>8}{'':>4}")
    print("  " + "-" * 92)
    oos_mask = ~is_mask
    survivors = []
    for _, r in R.head(8).iterrows():
        v1 = sig_arr[r["sig"]]
        m = tail_mask(v1, r["tail"], r["side"], v1[is_mask])
        if r["kind"] == "pair":
            v2 = sig_arr[r["sig2"]]
            m = m & tail_mask(v2, PAIR_TAIL, r["side2"], v2[is_mask])
        m = m & oos_mask & np.isfinite(ret_arr[r["hold"]])
        st = cell_stat(m, ret_arr[r["hold"]], dcode, ndates, int(r["trade"]),
                       fric, max(0, int(r["hold"]) - 1))
        nm = (f"{r['sig']}{'+' if r['side']>0 else '-'}"
              + (f"×{r['sig2']}{'+' if r['side2']>0 else '-'}"
                 if r["kind"] == "pair" else ""))
        if st is None:
            print(f"  {nm:<24}{r['mean']:>9.2f}{r['win']:>8.1f}{r['t']:>7.2f}"
                  f"{'표본부족':>28}")
            continue
        ok = (st["mean"] > 0) and (r["mean"] > 0)
        if ok:
            survivors.append(nm)
        print(f"  {nm:<24}{r['mean']:>9.2f}{r['win']:>8.1f}{r['t']:>7.2f}"
              f"{st['n']:>8}{st['mean']:>10.2f}{st['win']:>9.1f}"
              f"{st['t']:>8.2f}{'  ✓' if ok else '  ✗':>4}")

    print("\n" + "=" * 96)
    verdict = ("기각 — 최대통계량 위약을 못 넘는다" if pval > 0.05
               else ("후보 있음: " + ", ".join(survivors) if survivors
                     else "기각 — 위약은 넘었으나 표본 밖에서 부호 유지 실패"))
    print(f"  판정: **{verdict}**")
    print("=" * 96)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(
        {"params": vars(a), "n_cells": len(cells), "obs_best_t": obs_best,
         "null_mean": float(nulls.mean()),
         "null_p95": float(np.percentile(nulls, 95)),
         "null_max": float(nulls.max()), "p_value": pval,
         "verdict": verdict, "survivors": survivors,
         "top": R.head(20).to_dict("records")},
        ensure_ascii=False, indent=2, default=str))
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
