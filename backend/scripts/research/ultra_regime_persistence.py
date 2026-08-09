"""U1 `regime_persistence` 실측 — 종목 적합도가 창을 넘어 지속되는가.

초단기 트랙 설계(.claude/plans/ultrashort_tier_system_design.md)의 **생사를 가르는
측정**이다. 배정기(L2)는 "지난 창에 이 전략이 잘 먹힌 종목이 다음 창에도 잘 먹힌다"
는 전제 위에 서 있다. 그 전제가 거짓이면 배정기는 아무리 정교해도 무작위 선택과
같아지고, 초단기 트랙은 고정 유니버스로 되돌려야 한다.

측정 대상 전략 — paradigm 127 volume_burst 양의 연속 LONG.
  `app/composer_framework/sources/binance_alt_volume_burst_pos_continuation_long_source.py`
  의 트리거 로직을 그대로 재현한다. **2026-08-08 lookahead 수정(cd0ca27f) 반영본**이다
  — 트리거를 포함하는 봉이 아니라 **다음** 봉 시가에 체결한다. 수정 전 숫자(거래당
  0.7203%, 승률 88.4%)는 전량이 그 편향에서 나왔으므로 비교 대상이 아니다.

substrate — `runs/aggtrade_1m/{SYM}_agg1m.joblib` (backfill_aggtrades_1m.py).
  가격·거래량뿐 아니라 **실측 스프레드**(eff_spread_bp_adj)를 싣고 있어서 마찰을
  가정하지 않고 차감할 수 있다. 로컬 DB 는 최근이 비어 있으나 이 substrate 는
  아카이브 직접 수집이라 온전하다.

무엇을 보고하는가
  (a) 상관     edge[sym, w] 와 edge[sym, w+1] 의 Pearson / Spearman
  (b) 순위지속  창 쌍마다 종목 순위 Spearman → 평균과 t
  (c) **배정기 EV**  창 w 상위 K종목을 골랐을 때 창 w+1 실현 엣지 − 유니버스 평균.
      이것이 배정기가 실제로 버는 값이고, 판정의 근거다.
  (d) 대조군   무작위 K종목 추출 (동일 창 구조, 다수 시행)

사용:
  python3 scripts/research/ultra_regime_persistence.py --window-days 14 --step-days 7 --top-k 4
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ultra_regime_persistence")

# paradigm 127 동결 파라미터 (R-4 PASS 2026-05-21 시점 그대로)
VOL_LOOKBACK_BARS_1M = 30 * 24 * 60      # 43,200
VOL_MIN_PERIODS = int(VOL_LOOKBACK_BARS_1M * 0.25)
VOL_PERCENTILE = 0.99
MAGNITUDE_THRESHOLD = 0.005
AGG_BIN_MIN = 5
DEBOUNCE_MIN = 30
EVAL_FREQ_MIN = 5
MAX_HOLD_BARS = 15                       # 75분

TAKER_FEE_BP = 4.0                       # 편도. 왕복 2회.


def load_1m(path: str) -> pd.DataFrame:
    df = joblib.load(path)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def compute_triggers(df1m: pd.DataFrame) -> pd.DatetimeIndex:
    """소스의 _compute_triggers 재현: p99 거래량 + |ret|>0.5% + ret>0
    → 5분 bin 첫 건만 → 30분 debounce."""
    close = df1m["px_close"]
    vol = df1m["volume"]
    ret = close.pct_change()

    p99 = vol.rolling(VOL_LOOKBACK_BARS_1M, min_periods=VOL_MIN_PERIODS).quantile(VOL_PERCENTILE)
    fire = (vol > p99) & (ret.abs() > MAGNITUDE_THRESHOLD) & (ret > 0) & p99.notna()
    trig = df1m.index[fire.fillna(False).values]
    if len(trig) == 0:
        return pd.DatetimeIndex([])

    # 5분 bin 첫 건만 (Lesson #50 가드레일)
    s = pd.Series(trig, index=trig)
    first = s.groupby(pd.DatetimeIndex(trig).floor(f"{AGG_BIN_MIN}min")).first()
    cand = pd.DatetimeIndex(sorted(first.values))

    # 30분 debounce
    keep, last = [], None
    for ts in cand:
        if last is None or (ts - last).total_seconds() / 60.0 >= DEBOUNCE_MIN:
            keep.append(ts)
            last = ts
    return pd.DatetimeIndex(keep)


def build_trades(sym: str, df1m: pd.DataFrame) -> pd.DataFrame:
    """트리거 → 5분봉 진입/청산 → 마찰 차감 net_ret."""
    trig = compute_triggers(df1m)
    if len(trig) == 0:
        return pd.DataFrame()

    ev = pd.DataFrame({
        "open": df1m["px_open"].resample(f"{EVAL_FREQ_MIN}min").first(),
        "close": df1m["px_close"].resample(f"{EVAL_FREQ_MIN}min").last(),
    }).dropna()
    if len(ev) < MAX_HOLD_BARS + 2:
        return pd.DataFrame()

    # 마찰: 진입 시점 기준 직전 1일 스프레드 중앙값. 분 단위 추정치는 노이즈가
    # 크므로(모듈 docstring 참조) 일 단위로 눌러서 쓴다.
    spread_d = df1m["eff_spread_bp_adj"].resample("1D").median().ffill()

    idx = ev.index
    rows = []
    for ts in trig:
        # lookahead 수정본과 동일: 트리거를 **포함하는** 봉이 아니라 다음 봉.
        pos = idx.searchsorted(ts, side="right")
        if pos + MAX_HOLD_BARS >= len(idx):
            continue
        entry_ts = idx[pos]
        entry = float(ev["open"].iloc[pos])
        exit_ts = idx[pos + MAX_HOLD_BARS]
        exit_px = float(ev["open"].iloc[pos + MAX_HOLD_BARS])
        if entry <= 0:
            continue
        gross = exit_px / entry - 1.0
        day = entry_ts.normalize()
        sp_bp = float(spread_d.get(day, np.nan))
        if not np.isfinite(sp_bp):
            sp_bp = float(spread_d.median())
        fric = (sp_bp + 2.0 * TAKER_FEE_BP) / 10_000.0
        rows.append({"symbol": sym, "entry_ts": entry_ts, "exit_ts": exit_ts,
                     "gross": gross, "friction": fric, "net": gross - fric,
                     "spread_bp": sp_bp})
    return pd.DataFrame(rows)


def window_edges(trades: pd.DataFrame, window_days: int, step_days: int,
                 min_trades: int, metric: str = "net",
                 dvol: dict | None = None) -> pd.DataFrame:
    """(종목, 창) 격자의 거래당 엣지.

    metric="gross" 는 **교락 검사**용이다. 마찰(스프레드)은 틱사이즈÷가격으로
    결정되는 결정론적·거의 불변인 양이라, net 으로만 재면 배정기가 "레짐"이
    아니라 그냥 틱사이즈를 재발견한 것일 수 있다. gross 에서도 지속성이 살아
    있어야 진짜 알파 레짐 지속이다."""
    t0 = trades["entry_ts"].min().normalize()
    t1 = trades["entry_ts"].max().normalize()
    starts, cur = [], t0
    while cur + pd.Timedelta(days=window_days) <= t1 + pd.Timedelta(days=1):
        starts.append(cur)
        cur += pd.Timedelta(days=step_days)

    rows = []
    for wi, ws in enumerate(starts):
        we = ws + pd.Timedelta(days=window_days)
        sub = trades[(trades["entry_ts"] >= ws) & (trades["entry_ts"] < we)]
        for sym, g in sub.groupby("symbol"):
            if len(g) < min_trades:
                continue
            dv = np.nan
            if dvol is not None and sym in dvol:
                seg = dvol[sym].loc[(dvol[sym].index >= ws) & (dvol[sym].index < we)]
                if len(seg):
                    dv = float(seg.median())
            rows.append({"w": wi, "start": ws, "symbol": sym,
                         "n": len(g), "edge": float(g[metric].mean()),
                         "dvol_usd": dv})
    return pd.DataFrame(rows)


def allocator_ev(piv: pd.DataFrame, elig: pd.DataFrame, pairs: list,
                 top_k: int, n_random: int, rng) -> dict:
    """창 w 상위 K 선택 → 창 w+1 실현 엣지. 유니버스·무작위 대조 포함.

    `elig` 는 (창, 종목) 적격 마스크다. 유동성 관문을 여기서 먹인다 —
    719종목에는 체결 불가한 미소 종목이 다수라, 관문 없이 재면 배정기가 그런
    종목을 골라 EV 가 허수가 된다 (Lesson #78: 필터 하나로 +0.60% → -0.25% 부호반전)."""
    sel, uni, rnd = [], [], []
    for a, b in pairs:
        va, vb = piv.loc[a], piv.loc[b]
        ok_a, ok_b = elig.loc[a], elig.loc[b]
        cand = va[va.notna() & ok_a].index.intersection(vb[vb.notna() & ok_b].index)
        if len(cand) < top_k + 2:
            continue
        picks = va[cand].nlargest(top_k).index
        sel.append(float(vb[picks].mean()))
        uni.append(float(vb[cand].mean()))
        draws = [float(vb[rng.choice(cand, top_k, replace=False)].mean())
                 for _ in range(n_random)]
        rnd.append(float(np.mean(draws)))
    if len(sel) < 3:
        return {"top_k": top_k, "n": len(sel)}
    sel, uni, rnd = np.array(sel), np.array(uni), np.array(rnd)
    d_u, d_r = sel - uni, sel - rnd
    return {
        "top_k": top_k, "n": len(sel),
        "sel_bp": float(sel.mean() * 10_000),
        "uni_bp": float(uni.mean() * 10_000),
        "rnd_bp": float(rnd.mean() * 10_000),
        "ev_vs_uni_bp": float(d_u.mean() * 10_000),
        "ev_vs_uni_t": float(d_u.mean() / (d_u.std(ddof=1) / np.sqrt(len(d_u)))),
        "ev_vs_rnd_bp": float(d_r.mean() * 10_000),
        "ev_vs_rnd_t": float(d_r.mean() / (d_r.std(ddof=1) / np.sqrt(len(d_r)))),
    }


def measure(grid: pd.DataFrame, top_k: int, n_random: int, seed: int,
            k_sweep: list | None = None, min_dvol: float = 0.0) -> dict:
    piv = grid.pivot(index="w", columns="symbol", values="edge").sort_index()
    dv = (grid.pivot(index="w", columns="symbol", values="dvol_usd")
          .reindex_like(piv) if "dvol_usd" in grid.columns else None)
    # 유동성 적격 마스크. dvol 이 없으면 전부 적격.
    elig = (dv >= min_dvol) if (dv is not None and min_dvol > 0) else piv.notna()
    elig = elig.fillna(False)
    ws = list(piv.index)
    pairs = [(a, b) for a, b in zip(ws, ws[1:]) if b == a + 1]

    # (a)/(b) 는 배정기가 실제로 다루는 적격 집합 위에서 잰다.
    pv = piv.where(elig)

    # (a) 상관 — 모든 (종목, 연속 창 쌍)
    x, y = [], []
    for a, b in pairs:
        va, vb = pv.loc[a], pv.loc[b]
        m = va.notna() & vb.notna()
        x.extend(va[m].tolist()); y.extend(vb[m].tolist())
    x, y = np.array(x), np.array(y)
    pear = stats.pearsonr(x, y) if len(x) > 3 else (np.nan, np.nan)
    spear = stats.spearmanr(x, y) if len(x) > 3 else (np.nan, np.nan)

    # (b) 창 쌍별 종목 순위 Spearman
    rhos = []
    for a, b in pairs:
        va, vb = pv.loc[a], pv.loc[b]
        m = va.notna() & vb.notna()
        if m.sum() >= 4:
            r = stats.spearmanr(va[m], vb[m]).statistic
            if np.isfinite(r):
                rhos.append(r)
    rhos = np.array(rhos)
    rho_t = (rhos.mean() / (rhos.std(ddof=1) / np.sqrt(len(rhos)))) if len(rhos) > 2 else np.nan

    # (c) 배정기 EV — 창 w 상위 K → 창 w+1 실현. K 스윕으로 선택압/표본 절충을 본다.
    rng = np.random.default_rng(seed)
    ks = sorted(set([top_k] + list(k_sweep or [])))
    sweep = [allocator_ev(piv, elig, pairs, k, n_random, rng) for k in ks]
    primary = next((s for s in sweep if s["top_k"] == top_k), sweep[0])

    n_elig = int(elig.sum().sum())
    return {
        "n_windows": len(ws), "n_window_pairs": len(pairs), "n_cells": int(grid.shape[0]),
        "n_eligible_cells": n_elig, "min_dvol_usd": float(min_dvol),
        "median_cands_per_window": float(elig.sum(axis=1).median()),
        "pearson_r": float(pear[0]), "pearson_p": float(pear[1]),
        "spearman_r": float(spear[0]), "spearman_p": float(spear[1]),
        "rank_rho_mean": float(rhos.mean()) if len(rhos) else float("nan"),
        "rank_rho_t": float(rho_t), "rank_rho_n": int(len(rhos)),
        "topk_edge_bp": primary.get("sel_bp", float("nan")),
        "universe_edge_bp": primary.get("uni_bp", float("nan")),
        "random_edge_bp": primary.get("rnd_bp", float("nan")),
        "ev_vs_universe_bp": primary.get("ev_vs_uni_bp", float("nan")),
        "ev_vs_universe_t": primary.get("ev_vs_uni_t", float("nan")),
        "ev_vs_random_bp": primary.get("ev_vs_rnd_bp", float("nan")),
        "ev_vs_random_t": primary.get("ev_vs_rnd_t", float("nan")),
        "ev_n": primary.get("n", 0),
        "k_sweep": sweep,
    }


def _one(args, trades, dvol, ks, step_days: float, gate: float) -> dict | None:
    grid = window_edges(trades, args.window_days, int(step_days), args.min_trades,
                        metric=args.metric, dvol=dvol)
    if grid.empty or grid["w"].nunique() < 3:
        return None
    res = measure(grid, args.top_k, args.n_random, args.seed, k_sweep=ks, min_dvol=gate)
    res.update({"window_days": args.window_days, "step_days": int(step_days),
                "top_k": args.top_k, "min_trades": args.min_trades,
                "n_symbols": int(trades["symbol"].nunique()),
                "n_trades": int(len(trades)),
                "overall_net_bp": float(trades["net"].mean() * 10_000),
                "overall_gross_bp": float(trades["gross"].mean() * 10_000)})
    return res


def run_grid(args, trades: pd.DataFrame, dvol: dict, ks: list) -> int:
    """관문 x K (x 창 간격) 격자. 거래는 이미 만들어져 있으므로 메모리에서만 쓴다."""
    span = (trades["entry_ts"].max() - trades["entry_ts"].min()).days or 1
    log.info("\u2500\u2500 전체 %d거래 / %d종목 / %d일 | 거래당 net %+.2fbp | 종목·일당 %.2f건",
             len(trades), trades["symbol"].nunique(), span,
             trades["net"].mean() * 10_000,
             len(trades) / span / trades["symbol"].nunique())

    gates = [float(g) for g in args.gates.split(",") if g.strip()] or [args.min_dvol_usd]
    steps = [float(s) for s in args.steps.split(",") if s.strip()] or [args.step_days]

    out_all, first = [], None
    for st in steps:
        overlap = "겹침" if st < args.window_days else "비겹침"
        print("\n" + "=" * 96)
        print(f"U1 regime_persistence — volume_burst 127 [metric={args.metric}] "
              f"| 창 {args.window_days}일 / 간격 {int(st)}일 ({overlap})")
        print("=" * 96)
        for gate in gates:
            res = _one(args, trades, dvol, ks, st, gate)
            if res is None:
                print(f"  관문 ${gate:,.0f} — 창 부족")
                continue
            res["gate_usd"] = gate
            out_all.append(res)
            first = first or res
            print(f"\n  관문 ${gate:,.0f}/일  |  창당 후보 중앙 {res['median_cands_per_window']:.0f}종목"
                  f"  |  상관 r={res['pearson_r']:+.3f}"
                  f"  순위ρ={res['rank_rho_mean']:+.3f}(t={res['rank_rho_t']:+.2f})")
            print(f"      {'K':>4} {'선택 bp':>10} {'유니버스':>10} {'무작위':>10} "
                  f"{'EV vs유니':>10} {'t':>7} {'EV vs무작':>10} {'t':>7}")
            for s in res["k_sweep"]:
                if s.get("n", 0) < 3:
                    print(f"      {s['top_k']:>4}   (창쌍 부족)")
                    continue
                print(f"      {s['top_k']:>4} {s['sel_bp']:>+10.2f} {s['uni_bp']:>+10.2f} "
                      f"{s['rnd_bp']:>+10.2f} {s['ev_vs_uni_bp']:>+10.2f} {s['ev_vs_uni_t']:>+7.2f} "
                      f"{s['ev_vs_rnd_bp']:>+10.2f} {s['ev_vs_rnd_t']:>+7.2f}")
        print("=" * 96)

    if first:
        print(f"\n  표본 {first['n_trades']:,}거래 / {first['n_symbols']}종목 | "
              f"유니버스 거래당 gross {first['overall_gross_bp']:+.2f}bp "
              f"→ net {first['overall_net_bp']:+.2f}bp\n")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out_all, fh, indent=2, ensure_ascii=False, default=str)
    log.info("저장: %s (%d조건)", args.out, len(out_all))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="U1 regime_persistence 실측")
    p.add_argument("--data-dir", default=str(ROOT / "runs" / "aggtrade_1m"))
    p.add_argument("--window-days", type=int, default=14)
    p.add_argument("--step-days", type=int, default=7)
    p.add_argument("--min-trades", type=int, default=5)
    p.add_argument("--top-k", type=int, default=4)
    p.add_argument("--n-random", type=int, default=200)
    p.add_argument("--seed", type=int, default=20260809)
    p.add_argument("--metric", choices=["net", "gross"], default="net",
                   help="gross 는 마찰 교락 검사용 (window_edges docstring 참조)")
    p.add_argument("--k-sweep", default="4,8,12,24,48",
                   help="배정기 EV 를 여러 K 로 — 선택압 대 표본 절충 (좌석 수 근거)")
    p.add_argument("--min-dvol-usd", type=float, default=0.0,
                   help="유동성 관문(창 내 일 거래대금 중앙값). 0=관문 없음. "
                        "719종목엔 체결 불가 미소 종목이 다수라 Lesson #78 대로 필수")
    p.add_argument("--gates", default="",
                   help="유동성 관문 격자 (USD/일, 쉼표). 지정 시 --min-dvol-usd 대신 "
                        "격자 모드로 돈다 — 거래는 한 번만 만들고 관문×K 를 메모리에서 쓴다")
    p.add_argument("--steps", default="",
                   help="창 간격 격자 (일, 쉼표). 예 '7,14'. 14일 창을 7일씩 겹쳐 밟으면 "
                        "이웃 관측이 데이터의 절반을 공유해 t 가 부풀려진다 — "
                        "겹치지 않는 설정(step=window)과 나란히 봐야 한다")
    p.add_argument("--cache", default="", help="거래 캐시 joblib 경로 (재실행 즉시)")
    p.add_argument("--tag", default="", help="출력 파일 접미사")
    p.add_argument("--out", default=None)
    args = p.parse_args()
    ks = [int(x) for x in args.k_sweep.split(",") if x.strip()] if args.k_sweep else []
    if args.out is None:
        suffix = "" if args.metric == "net" else f"_{args.metric}"
        if args.tag:
            suffix += f"_{args.tag}"
        args.out = str(ROOT / "runs" / "research_track" /
                       f"ultra_regime_persistence{suffix}.json")

    files = sorted(glob.glob(os.path.join(args.data_dir, "*_agg1m.joblib")))
    if not files:
        log.error("substrate 없음: %s", args.data_dir)
        return 1

    if args.cache and os.path.exists(args.cache):
        trades, dvol = joblib.load(args.cache)
        log.info("캐시 적중 %s — %d거래 / %d종목", args.cache, len(trades), len(dvol))
        return run_grid(args, trades, dvol, ks)

    all_trades, dvol = [], {}
    for i, f in enumerate(files, 1):
        sym = os.path.basename(f).replace("_agg1m.joblib", "")
        df1m = load_1m(f)
        # 유동성 관문의 재료 — 일 거래대금. 연구 시점에 건다 (설계 §3.4).
        dvol[sym] = df1m["quote_volume"].resample("1D").sum()
        tr = build_trades(sym, df1m)
        if tr.empty:
            continue
        all_trades.append(tr)
        if len(files) <= 30 or i % 100 == 0:
            log.info("[%d/%d %s] 거래 %d건 | gross %+.2fbp | 마찰 %.2fbp | net %+.2fbp",
                     i, len(files), sym, len(tr), tr["gross"].mean() * 10_000,
                     tr["friction"].mean() * 10_000, tr["net"].mean() * 10_000)

    if not all_trades:
        log.error("전 종목 거래 0건 — 측정 불가")
        return 1
    trades = pd.concat(all_trades, ignore_index=True).sort_values("entry_ts")

    span = (trades["entry_ts"].max() - trades["entry_ts"].min()).days or 1
    log.info("── 전체 %d거래 / %d종목 / %d일 | 거래당 net %+.2fbp | 종목·일당 %.2f건",
             len(trades), trades["symbol"].nunique(), span,
             trades["net"].mean() * 10_000,
             len(trades) / span / trades["symbol"].nunique())

    if args.cache:
        os.makedirs(os.path.dirname(args.cache) or ".", exist_ok=True)
        joblib.dump((trades, dvol), args.cache, compress=3)
        log.info("거래 캐시 저장: %s", args.cache)

    return run_grid(args, trades, dvol, ks)


if __name__ == "__main__":
    sys.exit(main())
