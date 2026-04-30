"""
Genetic Programming Indicator Discovery.

가격 시계열에 대해 GP로 새로운 indicator 표현식을 진화시킨다.
인간이 designed한 RSI/BB/Stochastic 같은 indicator 대신,
조합되어 만들어지는 비선형 수식을 자동으로 탐색.

Primitive set:
  - 기본 변수: close, open, high, low, volume
  - 산술: add, sub, mul, protected_div
  - 단항: neg, abs, log_safe, sqrt_safe
  - Rolling statistics: ma(N), std(N), max(N), min(N), pct_change(N)
  - 시점 비교: shift(N)

Fitness function:
  - 5분봉 indicator series → 단순 매매 룰 (z-score 기반)
  - vectorized PnL 계산 (백테스트 엔진 우회)
  - Train 60일 Sharpe — 너무 적은 trade는 페널티

진화 후 best 표현식들을 KrBacktestEngine으로 정밀 검증.
"""
import argparse
import json
import operator
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from deap import algorithms, base, creator, gp, tools

import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from app.db.session import engine as db_engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed, resample_ohlcv


# ────────────────────────── Safe primitive operations ──────────────────────────

def safe_div(a, b):
    """Protected division — 0 또는 NaN 회피."""
    if isinstance(b, pd.Series):
        return a / b.replace(0, np.nan)
    if b == 0:
        return 1.0
    return a / b


def safe_log(a):
    if isinstance(a, pd.Series):
        return np.log(a.abs().replace(0, np.nan))
    return np.log(abs(a) + 1e-9)


def safe_sqrt(a):
    if isinstance(a, pd.Series):
        return np.sqrt(a.abs())
    return np.sqrt(abs(a))


def safe_neg(a):
    return -a


def _to_window(n):
    """Coerce any value to int window in [2, 100]. Series → use mean."""
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


# ────────────────────────── DEAP Primitive Set ──────────────────────────

# Untyped GP — 자유 조합, 잘못된 인자는 safe wrapper가 처리
pset = gp.PrimitiveSet("MAIN", arity=5)

# 산술 (binary)
pset.addPrimitive(operator.add, 2, name="add")
pset.addPrimitive(operator.sub, 2, name="sub")
pset.addPrimitive(operator.mul, 2, name="mul")
pset.addPrimitive(safe_div, 2, name="div")

# 단항
pset.addPrimitive(safe_neg, 1, name="neg")
pset.addPrimitive(safe_log, 1, name="log")
pset.addPrimitive(safe_sqrt, 1, name="sqrt")

# Rolling (s, n)
pset.addPrimitive(ma, 2, name="ma")
pset.addPrimitive(rstd, 2, name="rstd")
pset.addPrimitive(rmax, 2, name="rmax")
pset.addPrimitive(rmin, 2, name="rmin")
pset.addPrimitive(pct_change_n, 2, name="pct")
pset.addPrimitive(shift_n, 2, name="shift")

# Terminals — window constants
for _val in [5, 10, 14, 20, 30, 50, 60]:
    pset.addTerminal(_val, name=f"int_{_val}")

# 인자 이름 변경
pset.renameArguments(ARG0="close", ARG1="open", ARG2="high", ARG3="low", ARG4="volume")


# ────────────────────────── Creator (전역 1회) ──────────────────────────

if "FitnessMax" not in dir(creator):
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
if "Individual" not in dir(creator):
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax)


# ────────────────────────── Fitness function (vectorized) ──────────────────────────

# Korean stock 거래세 + 수수료 → 왕복 ~0.20%
ROUND_TRIP_COST = 0.0020


def vectorized_fitness(
    indicator: pd.Series, df: pd.DataFrame,
    z_window: int = 60, entry_z: float = -1.5, exit_z: float = 0.0,
    min_trades: int = 20,
) -> float:
    """
    indicator z-score < entry_z 시 매수, z > exit_z 시 청산.
    PnL = sum( exit_close / entry_close - 1 - friction )
    Sharpe = avg_pnl / std_pnl * sqrt(N)
    """
    if not isinstance(indicator, pd.Series):
        return -100.0
    if indicator.isna().sum() > len(indicator) * 0.6:
        return -100.0
    if indicator.std() == 0 or np.isnan(indicator.std()) or np.isinf(indicator.std()):
        return -100.0

    rmean = indicator.rolling(z_window).mean()
    rsd = indicator.rolling(z_window).std()
    z = ((indicator - rmean) / rsd.replace(0, np.nan)).fillna(0)

    # 단순 매매 룰
    in_pos = False
    entry_idx = None
    trades = []  # (entry_idx, exit_idx, pnl_pct)
    closes = df["close"].values

    for i in range(len(z)):
        z_val = z.iloc[i]
        if pd.isna(z_val) or np.isinf(z_val):
            continue
        if not in_pos and z_val < entry_z:
            in_pos = True
            entry_idx = i
        elif in_pos and z_val > exit_z:
            entry_price = closes[entry_idx]
            exit_price = closes[i]
            if entry_price > 0:
                pnl = exit_price / entry_price - 1.0 - ROUND_TRIP_COST
                trades.append(pnl)
            in_pos = False
            entry_idx = None

    n = len(trades)
    if n < min_trades:
        return -50.0 - (min_trades - n)

    arr = np.array(trades)
    avg = arr.mean()
    sd = arr.std(ddof=0)
    if sd == 0:
        return -100.0
    sharpe = avg / sd * np.sqrt(n)
    return float(sharpe)


def evaluate_individual(individual, df: pd.DataFrame) -> Tuple[float]:
    try:
        func = gp.compile(individual, pset)
        indicator = func(df["close"], df["open"], df["high"], df["low"], df["volume"])
        sharpe = vectorized_fitness(indicator, df)
        return (sharpe,)
    except Exception:
        return (-100.0,)


# ────────────────────────── Toolbox ──────────────────────────

def make_toolbox(df: pd.DataFrame) -> base.Toolbox:
    tb = base.Toolbox()
    tb.register("expr", gp.genHalfAndHalf, pset=pset, min_=2, max_=4)
    tb.register("individual", tools.initIterate, creator.Individual, tb.expr)
    tb.register("population", tools.initRepeat, list, tb.individual)
    tb.register("compile", gp.compile, pset=pset)
    tb.register("evaluate", evaluate_individual, df=df)
    tb.register("select", tools.selTournament, tournsize=3)
    tb.register("mate", gp.cxOnePoint)
    tb.register("expr_mut", gp.genFull, min_=0, max_=2)
    tb.register("mutate", gp.mutUniform, expr=tb.expr_mut, pset=pset)
    # depth bloat 방지
    tb.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"), max_value=8))
    tb.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=8))
    return tb


# ────────────────────────── Main evolution ──────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29")
    p.add_argument("--population", type=int, default=100)
    p.add_argument("--generations", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output", default="runs/kr_paper/sweeps/gp_indicators_v1.json")
    args = p.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    print(f"Loading 1m feed for {args.symbol}, resampling 5m...")
    feed_1m = fetch_1m_feed(db_engine, args.symbol, start_date=args.start)
    feed_5m = resample_ohlcv(feed_1m, "5min")
    days = sorted({c["timestamp"][:10] for c in feed_5m})
    train_cutoff = days[59]
    train_5m = [c for c in feed_5m if c["timestamp"][:10] <= train_cutoff]
    test_5m = [c for c in feed_5m if c["timestamp"][:10] > train_cutoff]
    print(f"  train: {len(train_5m)} bars / test: {len(test_5m)} bars\n")

    train_df = pd.DataFrame(train_5m)
    test_df = pd.DataFrame(test_5m)

    tb = make_toolbox(train_df)
    pop = tb.population(n=args.population)
    hof = tools.HallOfFame(20)

    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("max", np.max)
    stats.register("avg", np.mean)
    stats.register("min", np.min)

    print(f"=== GP Evolution start: pop={args.population}, gens={args.generations} ===")
    started = time.time()
    pop, log = algorithms.eaSimple(
        pop, tb, cxpb=0.5, mutpb=0.2, ngen=args.generations,
        stats=stats, halloffame=hof, verbose=True,
    )
    elapsed = time.time() - started
    print(f"\nElapsed: {elapsed:.1f}s")

    # Hall of Fame 분석
    print(f"\n=== HALL OF FAME (top 20 by train Sharpe) ===")
    print(f"{'rank':>4} {'train sh':>9} {'test sh':>9} {'expr':<60}")
    print('-' * 100)

    results = []
    for i, ind in enumerate(hof, 1):
        train_sh = ind.fitness.values[0]
        # OOS test 평가
        try:
            func = gp.compile(ind, pset)
            test_ind = func(test_df["close"], test_df["open"], test_df["high"], test_df["low"], test_df["volume"])
            test_sh = vectorized_fitness(test_ind, test_df)
        except Exception:
            test_sh = -100.0

        expr_str = str(ind)
        if len(expr_str) > 58:
            expr_str = expr_str[:55] + "..."
        print(f"{i:>4} {train_sh:>+8.2f} {test_sh:>+8.2f}  {expr_str}")

        results.append({
            "rank": i, "train_sharpe": train_sh, "test_sharpe": test_sh,
            "expr": str(ind), "height": ind.height,
        })

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "symbol": args.symbol,
            "train_range": [days[0], train_cutoff],
            "test_range": [days[60], days[-1]],
            "population": args.population, "generations": args.generations,
            "elapsed_s": elapsed,
            "results": results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out_path}")

    # Robust 분석 (train + test 둘 다 양수 sharpe)
    robust = [r for r in results if r["train_sharpe"] > 1 and r["test_sharpe"] > 0.5]
    print(f"\nROBUST (train_sh>1, test_sh>0.5): {len(robust)}")


if __name__ == "__main__":
    main()
