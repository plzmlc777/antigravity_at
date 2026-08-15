"""호가 깊이 축 — **방향**과 **위험**을 한 번에 잰다.

⚠ 방향 축은 이미 분 단위에서 닫혔다
    초단타 트랙이 라이브 체결로 검정했다. 호가불균형(가설 6) 60,668건
    **수수료 前 -3.97bp**, 깊이1(가설 7) 34,667건 **-3.11bp**.
    수수료를 0으로 해도 음수다 — 마찰 문제도 속도 문제도 아니다.
    [[feedback-lesson-84-passive-fill-is-the-wrong-moment]]

    여기서 여는 것은 **일 단위** 한 칸뿐이다. 여는 근거는 희망이 아니라 산수다:
        분 단위  엣지 1~5bp        vs 마찰 11bp  → 마찰이 엣지의 200~1000%
        일 단위  일간변동 300~500bp vs 마찰 10bp  → 마찰이 변동의 2~3%
    교훈 #80(엣지/수수료 비율)이 처음으로 우리 쪽에 선다.

    **단 메커니즘은 따라오지 않는다.** 분 단위 불균형이 작동하는 원리는
    "대기열 압력 → 다음 틱"인데 일별 중앙값으로 뭉개면 남지 않는다.
    그래서 방향은 낮게 보고 **한 번만** 잰다.

위험 축이 본론이다
    깊이가 진짜로 예측하는 것은 **얼마나 크게 움직일까**지 어느 쪽으로가 아니다.
    마켓메이커가 스트레스에 호가를 뺀다 — 이건 메커니즘이 있다.
    이 축은 **거래 신호가 아니라 사이징·회피 필터**라 마찰을 물지 않는다.

⚠ 시점 — 하루치 깊이 집계는 그날이 **끝나야** 완성된다
    신호는 t일, 진입은 t+1일 시가, 청산은 t+1+hold 시가. 같은 날 진입은
    미래참조다. 교훈 #90 이 정확히 이 지점에서 결론을 뒤집었다.

⚠ **관측 단위는 (종목,일) 이 아니라 '일' 이다**
    같은 날 종목들은 시장 베타로 묶여 있다. (종목,일)을 독립 관측으로 세면
    t 가 부풀어 오른다 — 오늘 여덟 축 중 여럿이 그 함정이었다.
    분위 스프레드를 **날짜마다** 계산해 시계열로 만든 뒤 검정한다.

거는 장치 (오늘 여덟 축을 닫은 것들 그대로)
    `--split` 필수 · 다리별 분해(교훈 #91) · 겹치면 HAC(#92) ·
    뒤섞기 + **교차자산** 위약(#93) · 마찰 선차감(#82) · 죽은 축 경고

사용:
  python3 -m scripts.research.depth_signal_scan --split 2025-06-01 --hold 5
"""
from __future__ import annotations

import argparse
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
log = logging.getLogger("depth_scan")

OUT = ROOT / "runs" / "research_track" / "depth_signal_scan.json"

ZWIN = 30          # 자기 이력 대비 z — 종목마다 깊이 규모가 4,000배 다르다
N_BUCKET = 5
MIN_SIDE = 2       # 한 날짜에 Q1·Q5 각각 최소 종목 수
MIN_DATES = 30     # 이보다 적은 날짜로는 판정하지 않는다


def newey_west_t(a: np.ndarray, lags: int) -> float | None:
    a = a[~np.isnan(a)]
    n = len(a)
    if n < 3:
        return None
    if lags < 1:
        se = a.std(ddof=1) / np.sqrt(n)
        return float(a.mean() / se) if se > 0 else None
    x = a - a.mean()
    var = float(np.dot(x, x) / n)
    for j in range(1, min(lags, n - 1) + 1):
        var += 2.0 * (1.0 - j / (lags + 1.0)) * float(np.dot(x[j:], x[:-j]) / n)
    return float(a.mean() / np.sqrt(var / n)) if var > 0 else None


def leg_stats(a: np.ndarray, lags: int) -> dict:
    a = a[~np.isnan(a)]
    if len(a) < 3:
        return {"n": int(len(a))}
    return {"n": int(len(a)), "mean": float(a.mean()),
            "total": float(a.sum()), "win": float(100 * (a > 0).mean()),
            "t": newey_west_t(a, lags)}


def load(conn) -> pd.DataFrame:
    from sqlalchemy import text
    d = pd.DataFrame(conn.execute(text(
        "SELECT symbol, date, depth1_usd, depth5_bid_usd, depth5_ask_usd, "
        "depth1_imbalance, depth1_bid_cv FROM binance_archive_depth "
        "ORDER BY symbol, date")).fetchall(),
        columns=["symbol", "date", "d1", "d5b", "d5a", "imb", "cv"])
    p = pd.DataFrame(conn.execute(text(
        "SELECT symbol, date, open, close FROM ohlcv_daily "
        "WHERE is_partial = false ORDER BY symbol, date")).fetchall(),
        columns=["symbol", "date", "open", "close"])
    for f in (d, p):
        f["date"] = pd.to_datetime(f["date"])
    df = p.merge(d, on=["symbol", "date"], how="inner")
    for c in ("open", "close", "d1", "d5b", "d5a", "imb", "cv"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def build_signals(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """전부 **자기 이력 대비 z** — 깊이 규모가 종목간 4,000배다."""
    df["ld1"] = np.log(df["d1"].where(df["d1"] > 0))
    shape = (df["d5b"] + df["d5a"]) / df["d1"].where(df["d1"] > 0)
    df["shape"] = np.log(shape.where(shape > 0))

    def z(col: str) -> pd.Series:
        s = df.groupby("symbol", sort=False)[col]
        m = s.transform(lambda x: x.rolling(ZWIN, min_periods=ZWIN).mean())
        sd = s.transform(lambda x: x.rolling(ZWIN, min_periods=ZWIN).std())
        return (df[col] - m) / sd.where(sd > 0)

    df["imb_raw"] = df["imb"]                      # 원값 (-1~1)
    df["imb_z"] = z("imb")                         # 불균형 (자기 기준)
    df["depth_z"] = z("ld1")                       # 유동성 수준
    df["cv_z"] = z("cv")                           # 유동성 불안정
    df["shape_z"] = z("shape")                     # 책 모양 (바깥/안쪽)
    df["depth_chg"] = df.groupby("symbol", sort=False)["ld1"].transform(
        lambda x: x - x.shift(7))                  # 깊이 변화 (7일)
    return df, ["imb_raw", "imb_z", "depth_z", "depth_chg", "cv_z", "shape_z"]


def date_spread(s: pd.DataFrame, sigcol: str, valcol: str,
                edges: np.ndarray) -> tuple[np.ndarray, np.ndarray,
                                            np.ndarray, np.ndarray]:
    """날짜별 (스프레드, Q5다리, Q1다리, 시장평균). 마찰 미차감."""
    q = pd.cut(s[sigcol], edges, labels=False, include_lowest=True)
    t = s.assign(q=q).dropna(subset=["q", valcol])
    g = t.groupby(["date", "q"])[valcol].agg(["mean", "size"])
    piv_m = g["mean"].unstack()
    piv_n = g["size"].unstack()
    mkt = t.groupby("date")[valcol].mean()
    lo_c, hi_c = 0.0, float(N_BUCKET - 1)
    if lo_c not in piv_m.columns or hi_c not in piv_m.columns:
        return (np.array([]),) * 4
    ok = (piv_n[lo_c].fillna(0) >= MIN_SIDE) & (piv_n[hi_c].fillna(0) >= MIN_SIDE)
    hi = piv_m.loc[ok, hi_c].values
    lo = piv_m.loc[ok, lo_c].values
    return hi - lo, hi, lo, mkt.loc[ok].values


def main() -> int:
    p = argparse.ArgumentParser(description="호가 깊이 — 방향·위험 동시 검정")
    p.add_argument("--split", required=True, help="표본 밖 시작일 (필수)")
    p.add_argument("--hold", type=int, default=5)
    p.add_argument("--stride", type=int, default=0, help="0=hold (비겹침)")
    p.add_argument("--fee-bp", type=float, default=5.0)
    p.add_argument("--placebo", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args()

    stride = a.stride or a.hold
    lags = max(0, a.hold // stride - 1)
    split = pd.Timestamp(datetime.fromisoformat(a.split))

    from app.db.session import engine
    with engine.connect() as conn:
        df = load(conn)
    if df.empty:
        raise SystemExit("깊이 × 일봉 교집합이 없다")
    df, sigs = build_signals(df)

    # ── 미래 수익·미래 변동성 ─────────────────────────────────────────
    # ⚠ 신호 t일 → 진입 t+1 시가 → 청산 t+1+hold 시가 (교훈 #90)
    piv_o = df.pivot(index="date", columns="symbol", values="open")
    piv_c = df.pivot(index="date", columns="symbol", values="close")
    lr = np.log(piv_c / piv_c.shift(1))

    fwd = (piv_o.shift(-(1 + a.hold)) / piv_o.shift(-1) - 1) * 100
    fwd_vol = lr.rolling(a.hold).std().shift(-(1 + a.hold)) * 100
    fwd_dd = (piv_c.rolling(a.hold).min().shift(-(1 + a.hold))
              / piv_o.shift(-1) - 1) * 100

    idx = piv_o.index
    keep = np.zeros(len(idx), dtype=bool)
    keep[ZWIN::stride] = True          # 워밍업 후 stride 간격 (겹침 통제)
    sel = idx[keep]

    def melt(m: pd.DataFrame, name: str) -> pd.DataFrame:
        return (m.loc[sel].stack().rename(name).reset_index()
                .set_axis(["date", "symbol", name], axis=1))

    base = melt(fwd, "fwd")
    for m, n in ((fwd_vol, "vol"), (fwd_dd, "dd")):
        base = base.merge(melt(m, n), on=["date", "symbol"], how="left")
    base = base.merge(df[["date", "symbol"] + sigs],
                      on=["date", "symbol"], how="inner")
    base["split"] = np.where(base["date"] >= split, "OOS", "IS")

    n_sym = base["symbol"].nunique()
    print("=" * 94)
    print(f"호가 깊이 축 — 종목 {n_sym} · 관측 {len(base):,} · 날짜 "
          f"{base['date'].nunique():,} · {base['date'].min().date()} ~ "
          f"{base['date'].max().date()}")
    print(f"보유 {a.hold}일 · 간격 {stride}일 · 분할 {a.split} · "
          f"마찰 {2*a.fee_bp:.0f}bp/다리"
          + (f" · HAC lags={lags}" if lags else " · 비겹침"))
    print("⚠ 관측 단위 = **날짜** (같은 날 종목은 시장 베타로 묶임)")
    print("=" * 94)

    fric_leg = 2 * a.fee_bp / 100.0        # 한 다리 왕복
    fric_spread = 2 * fric_leg             # 롱+숏 두 다리
    res: dict = {"n_symbols": n_sym, "n_obs": len(base), "hac_lags": lags,
                 "n_dates": int(base["date"].nunique())}

    # ── 1. 방향 축 ────────────────────────────────────────────────────
    print("\n【1】 방향 축 — 롱 Q5 / 숏 Q1 (마찰 20bp 차감, %/기간)")
    print(f"  {'신호':<10}{'구간':<5}{'날짜':>6}{'스프레드':>10}{'t':>8}"
          f"{'Q5다리':>9}{'Q1다리':>9}{'시장':>8}")
    print("  " + "-" * 88)

    alive, edge_cache = [], {}
    for sig in sigs:
        sub = base.dropna(subset=[sig, "fwd"])
        is_v = sub.loc[sub["split"] == "IS", sig]
        if len(is_v) < 200 or is_v.std() == 0:
            print(f"  {sig:<10}  표본/분산 부족 (IS n={len(is_v)}) — 건너뜀")
            continue
        edges = np.unique(np.quantile(is_v, np.linspace(0, 1, N_BUCKET + 1)))
        if len(edges) < N_BUCKET + 1:
            print(f"  {sig:<10}  **죽은 축** — 분위 경계 붕괴")
            continue
        edges[0], edges[-1] = -np.inf, np.inf
        edge_cache[sig] = edges

        for sp in ("IS", "OOS"):
            s = sub[sub["split"] == sp]
            sprd, hi, lo, mkt = date_spread(s, sig, "fwd", edges)
            if len(sprd) < MIN_DATES:
                print(f"  {sig:<10}{sp:<5}{len(sprd):>6}   날짜 부족 — 판정 보류")
                continue
            net = sprd - fric_spread
            tv = newey_west_t(net, lags)
            res[f"dir/{sig}/{sp}"] = {
                "n_dates": int(len(net)), "spread": float(net.mean()),
                "t": tv, "total": float(net.sum()),
                "q5_leg": leg_stats(hi - fric_leg, lags),
                "q1_leg": leg_stats(lo - fric_leg, lags),
                "market": float(mkt.mean())}
            print(f"  {sig:<10}{sp:<5}{len(net):>6}{net.mean():>10.3f}"
                  f"{(tv or 0):>8.2f}{(hi-fric_leg).mean():>9.3f}"
                  f"{(lo-fric_leg).mean():>9.3f}{mkt.mean():>8.3f}")
            if sp == "IS" and tv is not None and abs(tv) >= 2.0:
                alive.append(sig)
        print()

    # ── 2. 위험 축 ────────────────────────────────────────────────────
    print("\n【2】 위험 축 — 분위별 미래 실현변동성·최악낙폭 (마찰 무관)")
    print(f"  {'신호':<10}{'구간':<5}" + "".join(f"{'Q'+str(i+1):>8}"
          for i in range(N_BUCKET)) + f"{'Q5/Q1':>8}{'단조':>6}{'최악Q5':>9}")
    print("  " + "-" * 88)

    for sig in sigs:
        if sig not in edge_cache:
            continue
        edges = edge_cache[sig]
        sub = base.dropna(subset=[sig, "vol"]).copy()
        sub["q"] = pd.cut(sub[sig], edges, labels=False, include_lowest=True)
        for sp in ("IS", "OOS"):
            s = sub[sub["split"] == sp]
            means, ns = [], []
            for q in range(N_BUCKET):
                v = s.loc[s["q"] == q, "vol"].dropna().values
                ns.append(len(v))
                means.append(float(v.mean()) if len(v) >= 30 else np.nan)
            if any(m != m for m in means):
                continue
            ratio = means[-1] / means[0] if means[0] else np.nan
            mono = ("↑" if all(means[i] < means[i+1] for i in range(4))
                    else "↓" if all(means[i] > means[i+1] for i in range(4))
                    else "—")
            dd5 = s.loc[s["q"] == N_BUCKET - 1, "dd"].dropna()
            dd5v = float(dd5.mean()) if len(dd5) >= 30 else float("nan")
            res[f"vol/{sig}/{sp}"] = {"buckets": means, "n": ns,
                                      "ratio": float(ratio), "mono": mono,
                                      "q5_dd": dd5v}
            print(f"  {sig:<10}{sp:<5}"
                  + "".join(f"{m:>8.3f}" for m in means)
                  + f"{ratio:>8.2f}{mono:>6}{dd5v:>9.2f}")
        print()

    # ── 3. 위약 — 방향 축에서 살아남은 것만 ───────────────────────────
    print("\n【3】 위약 — 방향 축 IS |t| ≥ 2.0 인 신호만")
    alive = sorted(set(alive))
    if not alive:
        print("  **살아남은 방향 신호가 없다.** 위약 대상 없음.")
        res["placebo"] = {}
    else:
        rng = np.random.default_rng(a.seed)
        for sig in alive:
            obs = res[f"dir/{sig}/IS"]["t"]
            sub = base.dropna(subset=[sig, "fwd"])
            sub = sub[sub["split"] == "IS"].copy()
            edges = edge_cache[sig]

            def t_of(col: pd.Series) -> float | None:
                tmp = sub.assign(**{"_s": col})
                sprd, *_ = date_spread(tmp, "_s", "fwd", edges)
                if len(sprd) < MIN_DATES:
                    return None
                return newey_west_t(sprd - fric_spread, lags)

            wide = sub.pivot_table(index="date", columns="symbol",
                                   values=sig, aggfunc="first")
            syms = list(wide.columns)
            shuf, cross = [], []
            for _ in range(a.placebo):
                # (a) 뒤섞기 — 종목 안에서 시점만 섞는다
                c = sub.groupby("symbol")[sig].transform(
                    lambda x: pd.Series(rng.permutation(x.values), index=x.index))
                t = t_of(c)
                if t is not None:
                    shuf.append(t)
                # (b) 교차자산 — 다른 종목 신호로 이 종목을 거래 (교훈 #93)
                perm = dict(zip(syms, rng.permutation(syms)))
                mapped = pd.Series(
                    wide.reindex(index=sub["date"]).to_numpy()[
                        np.arange(len(sub)),
                        [wide.columns.get_loc(perm[s]) for s in sub["symbol"]]],
                    index=sub.index)
                t = t_of(mapped)
                if t is not None:
                    cross.append(t)

            entry = {"obs_t": obs}
            for lab, arr in (("shuffle", shuf), ("cross_asset", cross)):
                if not arr:
                    print(f"  {sig:<10}{lab:<13} 위약 표본 없음")
                    continue
                v = np.abs(np.array(arr))
                pv = float(np.mean(v >= abs(obs)))
                entry[lab] = {"null_mean_abs": float(v.mean()),
                              "null_p95": float(np.percentile(v, 95)),
                              "p_value": pv, "n_rep": len(v)}
                mark = "**구별 안 됨**" if pv > 0.05 else "통과"
                print(f"  {sig:<10}{lab:<13} 관측|t| {abs(obs):.2f} · "
                      f"위약평균 {v.mean():.2f} · p95 "
                      f"{np.percentile(v,95):.2f} · p {pv:.3f}  {mark}")
            res.setdefault("placebo", {})[sig] = entry

    # ── 4. 위험 축 대조 — 과거 실현변동성을 이기는가 ──────────────────
    #
    # ⚠ 이게 위험 축의 진짜 관문이다.
    #   변동성 군집(어제 출렁였으면 내일도 출렁인다)은 40년 된 사실이다.
    #   깊이가 미래 변동성을 맞힌다는 것만으로는 아무 값이 없다 —
    #   **과거 변동성이 이미 아는 것 위에 뭘 더 얹는가**를 물어야 한다.
    #   못 이기면 비싼 포장이다. SMB 를 '알트-BTC' 와 대조한 것과 같은 자리.
    pv = (lr.rolling(ZWIN).std() * 100).shift(1)      # t일까지의 과거 변동성
    base = base.merge(melt(pv, "past_vol"), on=["date", "symbol"], how="left")

    print("\n【4】 위험 축 대조 — 과거 실현변동성(30일) 대비 증분")
    dd = base.dropna(subset=["past_vol", "vol"])
    print(f"  기준선  과거변동성 분위별 미래변동성:")
    for sp in ("IS", "OOS"):
        s = dd[dd["split"] == sp]
        if len(s) < 300:
            continue
        eg = np.unique(np.quantile(dd.loc[dd["split"] == "IS", "past_vol"],
                                   np.linspace(0, 1, N_BUCKET + 1)))
        eg[0], eg[-1] = -np.inf, np.inf
        q = pd.cut(s["past_vol"], eg, labels=False, include_lowest=True)
        m = [float(s.loc[q == i, "vol"].mean()) for i in range(N_BUCKET)]
        print(f"    {sp:<5}" + "".join(f"{v:>8.3f}" for v in m)
              + f"{m[-1]/m[0]:>8.2f}배")

    print(f"\n  이중정렬  과거변동성 분위 **안에서** cv_z 가 더 가르는가:")
    print(f"    {'구간':<6}{'과거변동성분위':<14}"
          + "".join(f"{'cvQ'+str(i+1):>9}" for i in range(N_BUCKET))
          + f"{'Q5/Q1':>8}")
    incr = {}
    for sp in ("IS", "OOS"):
        s = dd[dd["split"] == sp].copy()
        if len(s) < 300:
            continue
        eg = np.unique(np.quantile(dd.loc[dd["split"] == "IS", "past_vol"],
                                   np.linspace(0, 1, N_BUCKET + 1)))
        eg[0], eg[-1] = -np.inf, np.inf
        s["pvq"] = pd.cut(s["past_vol"], eg, labels=False, include_lowest=True)
        s["cvq"] = pd.cut(s["cv_z"], edge_cache.get("cv_z", eg),
                          labels=False, include_lowest=True)
        ratios = []
        for pq in range(N_BUCKET):
            t = s[s["pvq"] == pq]
            m = [float(t.loc[t["cvq"] == i, "vol"].mean())
                 if (t["cvq"] == i).sum() >= 20 else np.nan
                 for i in range(N_BUCKET)]
            r = (m[-1] / m[0]) if (m[0] == m[0] and m[-1] == m[-1]
                                   and m[0]) else np.nan
            if r == r:
                ratios.append(r)
            print(f"    {sp:<6}{'과거Q'+str(pq+1):<14}"
                  + "".join(f"{v:>9.3f}" if v == v else f"{'—':>9}" for v in m)
                  + (f"{r:>8.2f}" if r == r else f"{'—':>8}"))
        if ratios:
            incr[sp] = float(np.mean(ratios))
            print(f"    → {sp} 평균 증분배율 **{np.mean(ratios):.3f}배**"
                  f"  (1.00 이면 과거변동성 위에 아무것도 못 얹은 것)")
    res["risk_control"] = {"incremental_ratio": incr}

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"params": vars(a), "results": res},
                                      ensure_ascii=False, indent=2,
                                      default=str))
    print("=" * 94)
    print(f"  → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
