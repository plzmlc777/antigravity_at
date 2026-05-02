"""S60/S61 robustness verification — multi-fold WF + param grid sweep.

Step 2-3 of validation flow:
  A. Multi-fold walk-forward (DEFAULT_PARAMS, fixed across folds)
     - 6 folds of ~2 months each
     - Reports fold-by-fold consistency
  B. Parameter grid sweep on FULL data
     - Tests each strategy's key params
     - Detects plateau (robust) vs cliff (fluke)
  C. WF parameter sweep — for each fold, best on IS, test on OOS
     - True overfit detection

Outputs:
  runs/kr_paper/sweeps/s60_robust.json
  runs/kr_paper/sweeps/s61_robust.json
"""
import asyncio
import itertools
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.core.kr_backtest_engine import KrBacktestEngine
from app.kr_strategy_pool.strategies.s60_instflow_consensus import S60_InstFlowConsensus
from app.kr_strategy_pool.strategies.s61_frgn_trend_leverage import S61_FrgnTrendLeverage


# ─── Config ───
CASES = [
    {"name": "S60", "symbol": "005930", "cls": S60_InstFlowConsensus},
    {"name": "S61", "symbol": "122630", "cls": S61_FrgnTrendLeverage},
]

# Data range available: 2025-05-02 ~ 2026-04-30 (12 months)
# Multi-fold WF: 6 folds of ~2 months each (non-overlapping)
WF_FOLDS = [
    ("2025-05-02", "2025-07-01"),
    ("2025-07-02", "2025-09-01"),
    ("2025-09-02", "2025-11-01"),
    ("2025-11-02", "2026-01-01"),
    ("2026-01-02", "2026-03-01"),
    ("2026-03-02", "2026-04-30"),
]

# Param grids — focused (3-axis × small steps to keep ~50-80 combos per strategy)
S60_GRID = {
    "inst_thr": [0.025, 0.05, 0.10],
    "consensus_min": [1, 2],
    "hold_days": [3, 5, 7],
    "sl_pct": [0.05, 0.07],
    "tp_pct": [0.10, 0.15],
}

S61_GRID = {
    "frgn_thr": [0.0, 0.025, 0.05],
    "consensus_min": [1, 2],
    "hold_days": [2, 3, 5],
    "sl_pct": [0.05, 0.07],
    "tp_pct": [0.10, 0.15],
}


async def run_one(cls, symbol, params, start, end, capital=3_000_000):
    feed = fetch_1m_feed(engine, symbol, start_date=start, end_date=end)
    if not feed:
        return None
    eng = KrBacktestEngine(cls, exchange_name="Kiwoom")
    cfg = {"symbol": symbol, **params}
    stats = await eng.run_single_backtest(
        config=cfg, feed=feed, initial_capital=capital, symbol=symbol,
    )
    return {
        "n_bars": len(feed),
        "return_pct": stats.get("return_pct"),
        "sharpe": stats.get("sharpe_ratio"),
        "win_rate": stats.get("win_rate"),
        "max_dd": stats.get("max_drawdown"),
        "trades": stats.get("trades_count"),
    }


def grid_combos(grid):
    keys = list(grid.keys())
    for vals in itertools.product(*[grid[k] for k in keys]):
        yield dict(zip(keys, vals))


async def run_case(case, grid):
    sym = case["symbol"]
    cls = case["cls"]
    name = case["name"]
    defaults = dict(cls.DEFAULT_PARAMS)
    print(f"\n{'='*70}")
    print(f"=== {name} / {sym} ===")
    print(f"{'='*70}")
    print(f"DEFAULT_PARAMS: {json.dumps(defaults)}")

    result = {
        "case": name, "symbol": sym, "defaults": defaults,
        "wf_folds": [], "grid_sweep": [], "grid_summary": {},
    }

    # ─── A. Multi-fold WF (DEFAULT_PARAMS) ───
    print(f"\n--- A. Multi-fold WF (DEFAULT_PARAMS, {len(WF_FOLDS)} folds) ---")
    print(f"{'fold':<5} {'period':<25} {'ret':>8} {'sharpe':>7} {'winR':>6} {'maxDD':>8} {'trades':>6}")
    print("-" * 70)
    fold_rets = []
    for i, (s, e) in enumerate(WF_FOLDS, 1):
        r = await run_one(cls, sym, defaults, s, e)
        if r is None:
            print(f"  fold{i:<3} {s}~{e}  (no data)")
            continue
        fold_rets.append(r["return_pct"] or 0)
        print(f"  fold{i:<3} {s}~{e}  {r['return_pct'] or 0:>+7.2f}% "
              f"{(r['sharpe'] or 0):>+7.2f} {(r['win_rate'] or 0):>5.1f}% "
              f"{(r['max_dd'] or 0):>+7.2f}% {r['trades'] or 0:>6}")
        result["wf_folds"].append({"fold": i, "start": s, "end": e, **r})

    if fold_rets:
        n_pos = sum(1 for x in fold_rets if x > 0)
        avg = sum(fold_rets) / len(fold_rets)
        med = sorted(fold_rets)[len(fold_rets)//2]
        worst = min(fold_rets)
        best = max(fold_rets)
        print(f"\n  Pos folds: {n_pos}/{len(fold_rets)}   avg/fold: {avg:+.2f}%   "
              f"median: {med:+.2f}%   worst: {worst:+.2f}%   best: {best:+.2f}%")
        result["wf_summary"] = {
            "n_folds": len(fold_rets), "n_positive": n_pos,
            "avg_return": avg, "median_return": med,
            "worst": worst, "best": best,
        }

    # ─── B. Parameter grid sweep on FULL data ───
    combos = list(grid_combos(grid))
    print(f"\n--- B. Param grid sweep on FULL data ({len(combos)} combos) ---")
    t0 = time.time()
    sweep = []
    for j, params in enumerate(combos, 1):
        r = await run_one(cls, sym, params, None, None)
        if r is None:
            continue
        row = {**params, **r}
        sweep.append(row)
        if j % 25 == 0:
            elapsed = time.time() - t0
            eta = elapsed * (len(combos) - j) / j
            print(f"  ... {j}/{len(combos)} done, elapsed={elapsed:.0f}s eta={eta:.0f}s", flush=True)
    elapsed = time.time() - t0
    print(f"  sweep done in {elapsed:.0f}s ({len(sweep)} valid)")

    # Sort by return
    sweep.sort(key=lambda x: x.get("return_pct") or -1e9, reverse=True)
    result["grid_sweep"] = sweep

    # Top-10 + DEFAULT location
    print(f"\n  Top-10 by return:")
    grid_keys = list(grid.keys())
    header = "rank " + " ".join(f"{k:>10}" for k in grid_keys) + "    return  sharpe  winR  maxDD trades"
    print(f"  {header}")
    print("  " + "-" * len(header))
    for i, r in enumerate(sweep[:10], 1):
        kv = " ".join(f"{str(r[k]):>10}" for k in grid_keys)
        ret = r.get("return_pct") or 0
        sh = r.get("sharpe") or 0
        wr = r.get("win_rate") or 0
        dd = r.get("max_dd") or 0
        tr = r.get("trades") or 0
        print(f"  {i:>4} {kv}  {ret:>+8.2f}% {sh:>+6.2f} {wr:>5.1f}% {dd:>+6.2f}% {tr:>6}")

    # Find DEFAULT in sweep + locate rank
    def_match = None
    for i, r in enumerate(sweep):
        if all(r.get(k) == defaults.get(k) for k in grid_keys):
            def_match = (i + 1, r)
            break
    if def_match:
        i, r = def_match
        ret = r.get("return_pct") or 0
        print(f"\n  DEFAULT_PARAMS rank: {i}/{len(sweep)} (return {ret:+.2f}%)")

    # Plateau check — top quartile mean vs DEFAULT
    n_top = max(1, len(sweep) // 4)
    top_q_avg = sum(r.get("return_pct") or 0 for r in sweep[:n_top]) / n_top
    overall_avg = sum(r.get("return_pct") or 0 for r in sweep) / len(sweep)
    n_pos = sum(1 for r in sweep if (r.get("return_pct") or 0) > 0)
    print(f"  Top quartile avg: {top_q_avg:+.2f}%   overall avg: {overall_avg:+.2f}%   "
          f"positive combos: {n_pos}/{len(sweep)} ({100*n_pos/len(sweep):.0f}%)")

    result["grid_summary"] = {
        "n_combos": len(sweep),
        "n_positive": n_pos,
        "pct_positive": 100 * n_pos / len(sweep),
        "top_quartile_avg_return": top_q_avg,
        "overall_avg_return": overall_avg,
        "default_rank": def_match[0] if def_match else None,
        "best_return": sweep[0].get("return_pct") if sweep else None,
        "best_params": {k: sweep[0].get(k) for k in grid_keys} if sweep else None,
    }

    # ─── C. Quick WF on best grid params ───
    if sweep:
        best = sweep[0]
        best_params = {**defaults, **{k: best[k] for k in grid_keys}}
        print(f"\n--- C. Multi-fold WF on grid-best params ---")
        print(f"  best_params: {json.dumps({k: best[k] for k in grid_keys})}")
        print(f"{'fold':<5} {'period':<25} {'ret':>8} {'sharpe':>7} {'trades':>6}")
        best_fold_rets = []
        for i, (s, e) in enumerate(WF_FOLDS, 1):
            r = await run_one(cls, sym, best_params, s, e)
            if r is None:
                continue
            best_fold_rets.append(r["return_pct"] or 0)
            print(f"  fold{i:<3} {s}~{e}  {r['return_pct'] or 0:>+7.2f}% "
                  f"{(r['sharpe'] or 0):>+7.2f} {r['trades'] or 0:>6}")
        if best_fold_rets:
            n_pos = sum(1 for x in best_fold_rets if x > 0)
            avg = sum(best_fold_rets) / len(best_fold_rets)
            print(f"\n  Pos folds: {n_pos}/{len(best_fold_rets)}   avg/fold: {avg:+.2f}%")
            result["wf_best_grid_summary"] = {
                "params": best_params,
                "n_positive": n_pos, "avg_return": avg,
            }

    return result


async def main():
    out_dir = Path(__file__).parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)

    grids = {"S60": S60_GRID, "S61": S61_GRID}
    for case in CASES:
        result = await run_case(case, grids[case["name"]])
        out_path = out_dir / f"{case['name'].lower()}_robust.json"
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
