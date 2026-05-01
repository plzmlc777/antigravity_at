"""
Theory-guided GP — primitive set을 검증된 trading sub-component로 교체.

기존 단순 GP의 한계: raw 가격/볼륨 + 산술 → 광활한 noise 공간.
Theory-guided: 이미 trading 의미 있는 component (bb_position, rsi_z, vol_z 등)를
              primitive로 사용 → GP는 그 component들의 결합 방식만 진화.

각 primitive는 [-3, +3] 범위 z-score로 normalized → 동일 척도에서 결합 가능.
"""
import argparse
import json
import operator
import random
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from deap import base, creator, tools, gp, algorithms

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app.db.session import engine as db_engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.kr_strategy_pool.indicators import (
    rsi, bollinger, stochastic, williams_r, zscore as zscore_ind,
    atr, ema, mfi, natr,
)


# ────────────────────────── Theory-guided primitives ──────────────────────────
# 모든 primitive는 [-3, +3] 범위 z-score를 반환 (또는 그에 가까운 normalized 값)

def _z_clip(s: pd.Series) -> pd.Series:
    """안전 normalize — [-5, +5] 범위로 clip + NaN 처리."""
    return s.replace([np.inf, -np.inf], np.nan).clip(-5, 5).fillna(0)


def bb_position(close: pd.Series) -> pd.Series:
    """Bollinger Band position. -2 = lower band, 0 = mid, +2 = upper band."""
    u, m, l = bollinger(close, 20, 2.0)
    width = (u - l).replace(0, np.nan)
    return _z_clip((close - m) / (width / 4))  # normalize to ~ -2 ~ +2


def rsi_z(close: pd.Series) -> pd.Series:
    """RSI z-score (50 기준 normalized to roughly -3 ~ +3)."""
    r = rsi(close, 14)
    return _z_clip((r - 50) / 15)


def stoch_z(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Stochastic K z-score."""
    k, _ = stochastic(high, low, close, 14, 3)
    return _z_clip((k - 50) / 20)


def williams_z(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Williams %R z-score."""
    wr = williams_r(high, low, close, 14)
    return _z_clip((wr + 50) / 20)


def close_z(close: pd.Series) -> pd.Series:
    """Close z-score (30봉)."""
    return _z_clip(zscore_ind(close, 30))


def ret_5(close: pd.Series) -> pd.Series:
    """5봉 수익률 z-score."""
    r = close.pct_change(5)
    return _z_clip((r - r.rolling(60).mean()) / r.rolling(60).std().replace(0, np.nan))


def ret_20(close: pd.Series) -> pd.Series:
    """20봉 수익률 z-score."""
    r = close.pct_change(20)
    return _z_clip((r - r.rolling(60).mean()) / r.rolling(60).std().replace(0, np.nan))


def vol_z(volume: pd.Series) -> pd.Series:
    """Volume z-score (20봉)."""
    return _z_clip(zscore_ind(volume.astype(float), 20))


def atr_norm(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Normalized ATR — % of close, then z-score."""
    nt = natr(high, low, close, 14)
    return _z_clip(zscore_ind(nt, 30))


def mfi_z(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """MFI z-score."""
    m = mfi(high, low, close, volume.astype(float), 14)
    return _z_clip((m - 50) / 20)


def vwap_dist(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """VWAP-distance z-score (전체 누적 VWAP 사용 — phase 누적)."""
    typical = (high + low + close) / 3.0
    pv_cum = (typical * volume).cumsum()
    v_cum = volume.cumsum().replace(0, np.nan)
    vwap = pv_cum / v_cum
    dist = (close - vwap) / vwap.replace(0, np.nan)
    return _z_clip(zscore_ind(dist, 60))


def momentum_5_20(close: pd.Series) -> pd.Series:
    """단기 모멘텀 vs 중기 — (5봉 수익률 - 20봉 수익률) z-score."""
    r5 = close.pct_change(5)
    r20 = close.pct_change(20)
    diff = r5 - r20
    return _z_clip((diff - diff.rolling(60).mean()) / diff.rolling(60).std().replace(0, np.nan))


def hl_range_z(high: pd.Series, low: pd.Series) -> pd.Series:
    """High-Low range z-score (변동성 환경)."""
    hl = high - low
    return _z_clip(zscore_ind(hl, 30))


def above_sma_50(close: pd.Series) -> pd.Series:
    """close vs 50봉 SMA 거리 — z-score."""
    sma = close.rolling(50).mean()
    dist = (close - sma) / sma.replace(0, np.nan)
    return _z_clip(zscore_ind(dist, 60))


# ────────────────────────── GP combinator primitives ──────────────────────────

def add_z(a, b):
    """더하기. 두 z-score 합 (직관: 두 신호 동시)."""
    return _z_clip(a + b) if isinstance(a, pd.Series) or isinstance(b, pd.Series) else (a + b)


def sub_z(a, b):
    return _z_clip(a - b) if isinstance(a, pd.Series) or isinstance(b, pd.Series) else (a - b)


def mul_z(a, b):
    """곱. 두 신호의 결합 (sign 동일 시 강화)."""
    if isinstance(a, pd.Series) or isinstance(b, pd.Series):
        return _z_clip(a * b)
    return a * b


def neg_z(a):
    return -a if isinstance(a, pd.Series) else -a


def min_z(a, b):
    """둘 중 더 음수 (보수적 oversold)."""
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        return _z_clip(pd.concat([a, b], axis=1).min(axis=1))
    return min(a, b)


def max_z(a, b):
    """둘 중 더 양수."""
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        return _z_clip(pd.concat([a, b], axis=1).max(axis=1))
    return max(a, b)


def conditional(cond, a, b):
    """if cond > 0 then a else b. 환경 분기."""
    if isinstance(cond, pd.Series):
        c = cond > 0
        if isinstance(a, pd.Series) and isinstance(b, pd.Series):
            return _z_clip(np.where(c, a, b))
        elif isinstance(a, pd.Series):
            return _z_clip(np.where(c, a, b * np.ones_like(a)))
        else:
            return _z_clip(np.where(c, np.full(len(c), a), b))
    return a if cond > 0 else b


# ────────────────────────── Pset construction ──────────────────────────
# Untyped GP — terminal은 모두 5개 base series → 각 sub-component는 1차 primitive

# 입력: close, open, high, low, volume (5개)
pset = gp.PrimitiveSet("MAIN", arity=5)
pset.renameArguments(ARG0="close", ARG1="open", ARG2="high", ARG3="low", ARG4="volume")

# Theory-guided sub-components — 인자별 callable primitive로 추가
# (단순화: 단일 인자 wrapper만 사용, 복잡한 multi-arg는 fixed lambda 사용)
pset.addPrimitive(bb_position, 1, name="bb_pos")  # uses close
pset.addPrimitive(rsi_z, 1, name="rsi_z")
pset.addPrimitive(close_z, 1, name="close_z")
pset.addPrimitive(ret_5, 1, name="ret5")
pset.addPrimitive(ret_20, 1, name="ret20")
pset.addPrimitive(vol_z, 1, name="vol_z")
pset.addPrimitive(above_sma_50, 1, name="above_sma50")
pset.addPrimitive(momentum_5_20, 1, name="mom_5_20")

# Combinators
pset.addPrimitive(add_z, 2, name="add")
pset.addPrimitive(sub_z, 2, name="sub")
pset.addPrimitive(mul_z, 2, name="mul")
pset.addPrimitive(neg_z, 1, name="neg")
pset.addPrimitive(min_z, 2, name="min")
pset.addPrimitive(max_z, 2, name="max")
pset.addPrimitive(conditional, 3, name="ifgt")

# Terminals — constants (z-score thresholds)
for v in [-2.0, -1.0, 0.0, 1.0, 2.0]:
    pset.addTerminal(v, name=f"c_{v}")


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
    if not isinstance(indicator, pd.Series):
        return -100.0, 0
    if indicator.isna().sum() > len(indicator) * 0.6:
        return -100.0, 0
    if indicator.std() == 0 or np.isnan(indicator.std()) or np.isinf(indicator.std()):
        return -100.0, 0

    # primitive output이 이미 z-score라 추가 normalize 안 함 (단, 직접 사용)
    z = indicator.fillna(0).values

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


def evaluate_multi_symbol(
    individual,
    splits: List[Dict[str, pd.DataFrame]],
    cost: float, parsimony: float,
) -> Tuple[float]:
    try:
        func = gp.compile(individual, pset)
        scores = []
        n_trades_per = []
        for split in splits:
            df_train = split["train"]
            df_val = split["val"]
            ind_train = func(df_train["close"], df_train["open"], df_train["high"],
                             df_train["low"], df_train["volume"])
            ind_val = func(df_val["close"], df_val["open"], df_val["high"],
                           df_val["low"], df_val["volume"])
            sh_train, n_train = vectorized_sharpe(ind_train, df_train, cost=cost)
            sh_val, n_val = vectorized_sharpe(ind_val, df_val, cost=cost)
            scores.append((sh_train + sh_val) / 2.0)
            n_trades_per.append(min(n_train, n_val))

        # 모든 symbol에서 어느 정도 작동해야 robust
        mean_score = float(np.mean(scores))
        std_score = float(np.std(scores))
        # 한 symbol이라도 trades 너무 적으면 페널티
        min_n = min(n_trades_per)
        n_penalty = 0.0
        if min_n < 10:
            n_penalty = (10 - min_n) * 0.1
        combined = mean_score - 0.3 * std_score - parsimony * len(individual) - n_penalty
        return (combined,)
    except Exception:
        return (-100.0,)


def make_toolbox(splits, cost, parsimony):
    tb = base.Toolbox()
    tb.register("expr", gp.genHalfAndHalf, pset=pset, min_=2, max_=4)
    tb.register("individual", tools.initIterate, creator.Individual, tb.expr)
    tb.register("population", tools.initRepeat, list, tb.individual)
    tb.register("compile", gp.compile, pset=pset)
    tb.register("evaluate", evaluate_multi_symbol, splits=splits, cost=cost, parsimony=parsimony)
    tb.register("select", tools.selTournament, tournsize=3)
    tb.register("mate", gp.cxOnePoint)
    tb.register("expr_mut", gp.genFull, min_=0, max_=2)
    tb.register("mutate", gp.mutUniform, expr=tb.expr_mut, pset=pset)
    tb.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"), max_value=6))
    tb.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=6))
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
    p.add_argument("--symbols", default="ETHUSDT,SOLUSDT,LINKUSDT,DOGEUSDT")
    p.add_argument("--max-bars", type=int, default=100_000)
    p.add_argument("--population", type=int, default=300)
    p.add_argument("--generations", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--cost", type=float, default=0.001)
    p.add_argument("--parsimony", type=float, default=0.01)
    p.add_argument("--output", default="runs/kr_paper/sweeps/gp_theory_guided.json")
    args = p.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    symbols = [s.strip() for s in args.symbols.split(",")]
    print(f"Theory-guided GP — symbols: {symbols}")
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

    print(f"\n=== Theory-Guided GP: pop={args.population} gen={args.generations} ===\n")
    pop, log = algorithms.eaSimple(pop, tb, cxpb=0.5, mutpb=0.2,
                                     ngen=args.generations, stats=stats,
                                     halloffame=hof, verbose=True)

    print("\n=== HALL OF FAME ===")
    rows = []
    for i, ind in enumerate(hof, 1):
        try:
            func = gp.compile(ind, pset)
            per_sym = []
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
                per_sym.append({"symbol": sp["symbol"], "train": tr_sh, "val": val_sh, "test": test_sh, "test_n": test_n})
        except Exception:
            per_sym = []
        rows.append({"rank": i, "fitness": ind.fitness.values[0], "tree_size": len(ind),
                     "per_symbol": per_sym, "expr": str(ind)})

    print(f"{'rank':<4} {'fit':>6} | " + " ".join(f"{sp['symbol']:>10}" for sp in splits) + " | expr")
    print("-" * 130)
    for r in rows[:15]:
        per = " ".join(f"{ps['test']:>+10.2f}" for ps in r["per_symbol"])
        print(f"{r['rank']:>3}. {r['fitness']:>+6.2f} | {per} | {r['expr'][:70]}")

    robust = [r for r in rows
              if r["per_symbol"] and all(ps["test"] > 0.5 and ps["test_n"] > 10 for ps in r["per_symbol"])]
    print(f"\n=== ROBUST (모든 종목 test sh > 0.5, n > 10): {len(robust)}/20 ===")
    for r in robust[:10]:
        print(f"  rank {r['rank']}: " + " ".join(f"{ps['symbol']}={ps['test']:.2f}" for ps in r["per_symbol"]))
        print(f"    expr: {r['expr'][:120]}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"symbols": symbols, "max_bars": args.max_bars,
                   "population": args.population, "generations": args.generations,
                   "cost": args.cost, "parsimony": args.parsimony,
                   "hof": rows}, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out}")


if __name__ == "__main__":
    main()
