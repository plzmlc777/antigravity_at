"""
GP Universal Indicator Discovery — 풍부한 데이터 환경 (Binance 24/7 1분봉) 활용.

Train / Validation / Test 3-way split:
  - Train: GP 진화에 fitness 신호 (population 학습)
  - Validation: HoF 선정 기준 (overfit 검증 + parsimony)
  - Test: 최종 OOS 검증 (진화에 영향 없음)

Fitness = (train_sharpe + val_sharpe) / 2 - parsimony_weight * tree_size

거래 비용 인자화 — Binance (0.1% 또는 0.0%) vs KR (0.20%) 분기.
"""
import argparse
import json
import operator
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, List, Dict, Any

import numpy as np
import pandas as pd
from deap import base, creator, tools, gp, algorithms

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.db.session import engine as db_engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed


# ────────────────────────── Safe ops ──────────────────────────

def safe_div(a, b):
    if isinstance(b, pd.Series):
        return a / b.replace(0, np.nan)
    if b == 0:
        return a if isinstance(a, pd.Series) else 0
    return a / b


def safe_log(s):
    if isinstance(s, pd.Series):
        return np.log(s.abs().replace(0, np.nan))
    return np.log(abs(s)) if s != 0 else 0


def safe_sqrt(s):
    if isinstance(s, pd.Series):
        return np.sqrt(s.abs())
    return np.sqrt(abs(s))


def safe_neg(s):
    return -s


def _to_window(n):
    if isinstance(n, pd.Series):
        try:
            n = float(n.mean())
        except Exception:
            return 10
    try:
        n = int(abs(float(n)))
    except (ValueError, TypeError):
        return 10
    return max(2, min(n, 100))


def ma(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).mean()


def rstd(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).std()


def rmax(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).max()


def rmin(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).min()


def pct_change_n(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([0.0])
    return s.pct_change(_to_window(n))


def shift_n(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.shift(_to_window(n))


# ────────────────────────── Primitive set ──────────────────────────

pset = gp.PrimitiveSet("MAIN", arity=5)
pset.addPrimitive(operator.add, 2, name="add")
pset.addPrimitive(operator.sub, 2, name="sub")
pset.addPrimitive(operator.mul, 2, name="mul")
pset.addPrimitive(safe_div, 2, name="div")
pset.addPrimitive(safe_neg, 1, name="neg")
pset.addPrimitive(safe_log, 1, name="log")
pset.addPrimitive(safe_sqrt, 1, name="sqrt")
pset.addPrimitive(ma, 2, name="ma")
pset.addPrimitive(rstd, 2, name="rstd")
pset.addPrimitive(rmax, 2, name="rmax")
pset.addPrimitive(rmin, 2, name="rmin")
pset.addPrimitive(pct_change_n, 2, name="pct")
pset.addPrimitive(shift_n, 2, name="shift")
for _val in [5, 10, 14, 20, 30, 50, 60, 100]:
    pset.addTerminal(_val, name=f"int_{_val}")
pset.renameArguments(ARG0="close", ARG1="open", ARG2="high", ARG3="low", ARG4="volume")


# ────────────────────────── Creator ──────────────────────────

if "FitnessMax" not in dir(creator):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if "Individual" not in dir(creator):
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)


# ────────────────────────── Fitness ──────────────────────────

def vectorized_sharpe(
    indicator: pd.Series, df: pd.DataFrame,
    z_window: int = 60, entry_z: float = -1.5, exit_z: float = 0.0,
    min_trades: int = 20, cost: float = 0.001,
) -> Tuple[float, int]:
    """Returns (sharpe, n_trades)."""
    if not isinstance(indicator, pd.Series):
        return -100.0, 0
    if indicator.isna().sum() > len(indicator) * 0.6:
        return -100.0, 0
    if indicator.std() == 0 or np.isnan(indicator.std()) or np.isinf(indicator.std()):
        return -100.0, 0

    rmean = indicator.rolling(z_window).mean()
    rsd = indicator.rolling(z_window).std()
    z = ((indicator - rmean) / rsd.replace(0, np.nan)).fillna(0).values

    closes = df["close"].values
    in_pos = False
    entry_idx = None
    trades = []
    for i in range(len(z)):
        zv = z[i]
        if np.isnan(zv) or np.isinf(zv):
            continue
        if not in_pos and zv < entry_z:
            in_pos = True
            entry_idx = i
        elif in_pos and zv > exit_z:
            ep = closes[entry_idx]
            xp = closes[i]
            if ep > 0:
                trades.append(xp / ep - 1.0 - cost)
            in_pos = False

    n = len(trades)
    if n < min_trades:
        return -50.0 - (min_trades - n), n

    arr = np.array(trades)
    avg = arr.mean()
    sd = arr.std(ddof=0)
    if sd == 0:
        return -100.0, n
    return float(avg / sd * np.sqrt(n)), n


def evaluate_individual(
    individual, df_train: pd.DataFrame, df_val: pd.DataFrame,
    cost: float, parsimony: float,
) -> Tuple[float]:
    try:
        func = gp.compile(individual, pset)
        ind_train = func(df_train["close"], df_train["open"], df_train["high"],
                         df_train["low"], df_train["volume"])
        ind_val = func(df_val["close"], df_val["open"], df_val["high"],
                       df_val["low"], df_val["volume"])
        sh_train, n_train = vectorized_sharpe(ind_train, df_train, cost=cost)
        sh_val, n_val = vectorized_sharpe(ind_val, df_val, cost=cost)
        # 둘 다 흑자가 아니면 페널티
        if sh_train < 0 or sh_val < 0:
            combined = (sh_train + sh_val) / 2.0
        else:
            combined = (sh_train + sh_val) / 2.0
        # parsimony — tree size 페널티
        tree_size = len(individual)
        combined -= parsimony * tree_size
        return (combined,)
    except Exception:
        return (-100.0,)


# ────────────────────────── Toolbox factory ──────────────────────────

def make_toolbox(df_train, df_val, cost, parsimony):
    tb = base.Toolbox()
    tb.register("expr", gp.genHalfAndHalf, pset=pset, min_=2, max_=4)
    tb.register("individual", tools.initIterate, creator.Individual, tb.expr)
    tb.register("population", tools.initRepeat, list, tb.individual)
    tb.register("compile", gp.compile, pset=pset)
    tb.register("evaluate", evaluate_individual,
                df_train=df_train, df_val=df_val, cost=cost, parsimony=parsimony)
    tb.register("select", tools.selTournament, tournsize=3)
    tb.register("mate", gp.cxOnePoint)
    tb.register("expr_mut", gp.genFull, min_=0, max_=2)
    tb.register("mutate", gp.mutUniform, expr=tb.expr_mut, pset=pset)
    tb.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"), max_value=8))
    tb.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=8))
    return tb


# ────────────────────────── Main ──────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="ETHUSDT")
    p.add_argument("--start", default=None, help="ISO date or empty for full data")
    p.add_argument("--max-bars", type=int, default=200_000,
                   help="시뮬 효율을 위해 처음 N개 bars만 사용 (default 200K)")
    p.add_argument("--population", type=int, default=200)
    p.add_argument("--generations", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cost", type=float, default=0.001,
                   help="round-trip cost (Binance 0.001=0.1%, KR 0.002=0.20%)")
    p.add_argument("--parsimony", type=float, default=0.01,
                   help="parsimony penalty per tree node")
    p.add_argument("--output", default=None)
    args = p.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    print(f"Loading 1m feed for {args.symbol}{' from ' + args.start if args.start else ''}...")
    feed = fetch_1m_feed(db_engine, args.symbol, start_date=args.start)
    print(f"  total bars: {len(feed):,}")

    if len(feed) > args.max_bars:
        feed = feed[-args.max_bars:]  # 최근 N개만 사용
        print(f"  trimmed to last {len(feed):,} bars")

    df = pd.DataFrame(feed)

    # 60% train / 20% val / 20% test
    n = len(df)
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)
    df_train = df.iloc[:train_end].reset_index(drop=True)
    df_val = df.iloc[train_end:val_end].reset_index(drop=True)
    df_test = df.iloc[val_end:].reset_index(drop=True)
    print(f"  train: {len(df_train):,}  val: {len(df_val):,}  test: {len(df_test):,}")

    tb = make_toolbox(df_train, df_val, args.cost, args.parsimony)
    pop = tb.population(n=args.population)
    hof = tools.HallOfFame(20)

    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", np.mean)
    stats.register("max", np.max)
    stats.register("min", np.min)

    print(f"\n=== GP Evolution: {args.symbol} pop={args.population} gen={args.generations} cost={args.cost} parsimony={args.parsimony} ===\n")
    pop, log = algorithms.eaSimple(pop, tb, cxpb=0.5, mutpb=0.2,
                                     ngen=args.generations, stats=stats,
                                     halloffame=hof, verbose=True)

    print("\n=== HALL OF FAME (top 20 by combined fitness) ===")
    print(f"{'rank':<4} {'combined':>9} | {'tr_sh':>7} {'val_sh':>7} | {'test_sh':>8} {'test_n':>7} | expr (truncated)")
    print("-" * 130)
    rows = []
    for i, ind in enumerate(hof, 1):
        combined = ind.fitness.values[0]
        try:
            func = gp.compile(ind, pset)
            ind_train = func(df_train["close"], df_train["open"], df_train["high"],
                             df_train["low"], df_train["volume"])
            ind_val = func(df_val["close"], df_val["open"], df_val["high"],
                           df_val["low"], df_val["volume"])
            ind_test = func(df_test["close"], df_test["open"], df_test["high"],
                            df_test["low"], df_test["volume"])
            tr_sh, _ = vectorized_sharpe(ind_train, df_train, cost=args.cost)
            val_sh, _ = vectorized_sharpe(ind_val, df_val, cost=args.cost)
            test_sh, test_n = vectorized_sharpe(ind_test, df_test, cost=args.cost)
        except Exception:
            tr_sh, val_sh, test_sh, test_n = -100, -100, -100, 0
        expr = str(ind)
        rows.append({
            "rank": i, "combined": combined, "tree_size": len(ind),
            "train_sh": tr_sh, "val_sh": val_sh, "test_sh": test_sh, "test_n": test_n,
            "expr": expr,
        })
        print(f"{i:>3}. {combined:>+8.2f}  | {tr_sh:>+6.2f} {val_sh:>+6.2f}  | "
              f"{test_sh:>+7.2f} {test_n:>7} | {expr[:80]}{'...' if len(expr) > 80 else ''}")

    out_path = args.output or f"runs/kr_paper/sweeps/gp_universal_{args.symbol}.json"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "symbol": args.symbol, "population": args.population, "generations": args.generations,
            "cost": args.cost, "parsimony": args.parsimony,
            "n_train": len(df_train), "n_val": len(df_val), "n_test": len(df_test),
            "hof": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out_path}")

    robust = [r for r in rows if r["train_sh"] > 0.5 and r["val_sh"] > 0.5 and r["test_sh"] > 0.5]
    print(f"\n=== ROBUST (train, val, test 모두 sharpe > 0.5): {len(robust)}/20 ===")
    for r in robust[:10]:
        print(f"  rank {r['rank']}: tr={r['train_sh']:+.2f} val={r['val_sh']:+.2f} test={r['test_sh']:+.2f} n={r['test_n']}")


if __name__ == "__main__":
    main()
