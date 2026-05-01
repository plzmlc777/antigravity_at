"""
GP Multi-Symbol Universal Indicator Discovery.

여러 Binance 1m 종목 (ETH/SOL/LINK/DOGE)에서 동시 평가:
  - 한 indicator가 모든 종목에서 robust = 진정한 universal pattern
  - 단일 종목 우연 fitting 불가능

각 종목 60% train / 20% val / 20% test
fitness = mean(train_sharpe + val_sharpe across symbols)
        - parsimony * tree_size
"""
import argparse
import json
import operator
import random
from pathlib import Path
from typing import Tuple, List, Dict

import numpy as np
import pandas as pd
from deap import base, creator, tools, gp, algorithms

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.db.session import engine as db_engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from gp_universal_indicator import (
    pset, vectorized_sharpe, safe_div, safe_log, safe_sqrt, safe_neg,
    ma, rstd, rmax, rmin, pct_change_n, shift_n,
)

# Re-use creator types from gp_universal_indicator
if "FitnessMax" not in dir(creator):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if "Individual" not in dir(creator):
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)


# ────────────────────────── Multi-symbol fitness ──────────────────────────

def evaluate_multi_symbol(
    individual,
    splits: List[Dict[str, pd.DataFrame]],  # [{"train": df, "val": df, "test": df}, ...]
    cost: float, parsimony: float,
) -> Tuple[float]:
    """
    각 symbol에서 train+val sharpe 평균 → multi-symbol mean.
    한 symbol이라도 -50 미만 (zero trades) 이면 큰 페널티.
    """
    try:
        func = gp.compile(individual, pset)
        scores = []
        for split in splits:
            df_train = split["train"]
            df_val = split["val"]
            ind_train = func(df_train["close"], df_train["open"], df_train["high"],
                             df_train["low"], df_train["volume"])
            ind_val = func(df_val["close"], df_val["open"], df_val["high"],
                           df_val["low"], df_val["volume"])
            sh_train, _ = vectorized_sharpe(ind_train, df_train, cost=cost)
            sh_val, _ = vectorized_sharpe(ind_val, df_val, cost=cost)
            symbol_score = (sh_train + sh_val) / 2.0
            scores.append(symbol_score)

        # 모든 symbol에서 어느 정도 작동해야 robust
        # mean - std 페널티 (한 종목만 잘 되는 것 차단)
        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores))
        combined = mean_score - 0.3 * std_score - parsimony * len(individual)
        return (combined,)
    except Exception:
        return (-100.0,)


def make_toolbox(splits, cost, parsimony):
    tb = base.Toolbox()
    tb.register("expr", gp.genHalfAndHalf, pset=pset, min_=2, max_=4)
    tb.register("individual", tools.initIterate, creator.Individual, tb.expr)
    tb.register("population", tools.initRepeat, list, tb.individual)
    tb.register("compile", gp.compile, pset=pset)
    tb.register("evaluate", evaluate_multi_symbol,
                splits=splits, cost=cost, parsimony=parsimony)
    tb.register("select", tools.selTournament, tournsize=3)
    tb.register("mate", gp.cxOnePoint)
    tb.register("expr_mut", gp.genFull, min_=0, max_=2)
    tb.register("mutate", gp.mutUniform, expr=tb.expr_mut, pset=pset)
    tb.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"), max_value=8))
    tb.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=8))
    return tb


def make_split(symbol: str, max_bars: int):
    feed = fetch_1m_feed(db_engine, symbol)
    if len(feed) > max_bars:
        feed = feed[-max_bars:]
    df = pd.DataFrame(feed)
    n = len(df)
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)
    return {
        "symbol": symbol,
        "train": df.iloc[:train_end].reset_index(drop=True),
        "val": df.iloc[train_end:val_end].reset_index(drop=True),
        "test": df.iloc[val_end:].reset_index(drop=True),
        "n_total": n,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="ETHUSDT,SOLUSDT,LINKUSDT,DOGEUSDT",
                   help="comma-separated Binance 1m symbols")
    p.add_argument("--max-bars", type=int, default=200_000)
    p.add_argument("--population", type=int, default=300)
    p.add_argument("--generations", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cost", type=float, default=0.001)
    p.add_argument("--parsimony", type=float, default=0.005)
    p.add_argument("--output", default="runs/kr_paper/sweeps/gp_multi_symbol.json")
    args = p.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    symbols = [s.strip() for s in args.symbols.split(",")]
    print(f"Symbols: {symbols}")
    splits = []
    for sym in symbols:
        sp = make_split(sym, args.max_bars)
        print(f"  {sym}: total={sp['n_total']:,} train={len(sp['train']):,} val={len(sp['val']):,} test={len(sp['test']):,}")
        splits.append(sp)

    tb = make_toolbox(splits, args.cost, args.parsimony)
    pop = tb.population(n=args.population)
    hof = tools.HallOfFame(20)

    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", np.mean)
    stats.register("max", np.max)
    stats.register("min", np.min)

    print(f"\n=== GP Multi-Symbol Evolution: pop={args.population} gen={args.generations} ===\n")
    pop, log = algorithms.eaSimple(pop, tb, cxpb=0.5, mutpb=0.2,
                                     ngen=args.generations, stats=stats,
                                     halloffame=hof, verbose=True)

    print("\n=== HALL OF FAME — multi-symbol robustness ===")
    rows = []
    for i, ind in enumerate(hof, 1):
        try:
            func = gp.compile(ind, pset)
            per_symbol = []
            for sp in splits:
                ind_train = func(sp["train"]["close"], sp["train"]["open"], sp["train"]["high"],
                                 sp["train"]["low"], sp["train"]["volume"])
                ind_val = func(sp["val"]["close"], sp["val"]["open"], sp["val"]["high"],
                               sp["val"]["low"], sp["val"]["volume"])
                ind_test = func(sp["test"]["close"], sp["test"]["open"], sp["test"]["high"],
                                sp["test"]["low"], sp["test"]["volume"])
                tr_sh, _ = vectorized_sharpe(ind_train, sp["train"], cost=args.cost)
                val_sh, _ = vectorized_sharpe(ind_val, sp["val"], cost=args.cost)
                test_sh, test_n = vectorized_sharpe(ind_test, sp["test"], cost=args.cost)
                per_symbol.append({
                    "symbol": sp["symbol"], "train": tr_sh, "val": val_sh,
                    "test": test_sh, "test_n": test_n,
                })
        except Exception:
            per_symbol = []
        expr = str(ind)
        rows.append({
            "rank": i, "fitness": ind.fitness.values[0], "tree_size": len(ind),
            "per_symbol": per_symbol, "expr": expr,
        })

    # 출력 — 종목별 test sharpe
    print(f"\n{'rank':<4} {'fit':>6} | " +
          " ".join(f"{sp['symbol']:>11}" for sp in splits) + " | expr")
    print("-" * 130)
    for r in rows[:15]:
        per_sym_str = " ".join(f"{ps['test']:>+11.2f}" for ps in r["per_symbol"])
        print(f"{r['rank']:>3}. {r['fitness']:>+6.2f} | {per_sym_str} | {r['expr'][:60]}")

    # ROBUST: 모든 symbol에서 test sharpe > 0.5
    robust = []
    for r in rows:
        if not r["per_symbol"]:
            continue
        if all(ps["test"] > 0.5 and ps["test_n"] > 10 for ps in r["per_symbol"]):
            robust.append(r)
    print(f"\n=== ROBUST (모든 종목 test sh > 0.5, n > 10): {len(robust)}/20 ===")
    for r in robust[:10]:
        print(f"  rank {r['rank']}: " + " ".join(f"{ps['symbol']}={ps['test']:.2f}" for ps in r["per_symbol"]))
        print(f"    expr: {r['expr'][:100]}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({
            "symbols": symbols, "max_bars": args.max_bars,
            "population": args.population, "generations": args.generations,
            "cost": args.cost, "parsimony": args.parsimony,
            "hof": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    main()
