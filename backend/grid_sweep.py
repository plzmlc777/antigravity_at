"""
Parameter Grid Sweep — 각 전략의 핵심 파라미터를 sweep해 sweet spot 발견.

대상: Quality 8-pool + 추가 가치 후보 4개 = 12개 전략.
각 전략당 1-2개 핵심 파라미터 × 3-5 values.

출력:
  runs/kr_paper/sweeps/grid_<run_id>.jsonl  — 모든 (strategy, params, result) 행
  + 콘솔 표 (best params per strategy)
"""
import argparse
import asyncio
import itertools
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Type

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.core.kr_backtest_engine import KrBacktestEngine
from app.kr_strategy_pool.base import KrStrategyBase
from app.kr_strategy_pool.data_utils import fetch_1m_feed, resample_ohlcv

# Strategies
from app.kr_strategy_pool.strategies.s2_bb_reversion import S2BBReversion
from app.kr_strategy_pool.strategies.s4_opening_range_breakout import S4OpeningRangeBreakout
from app.kr_strategy_pool.strategies.s9_volume_spike import S9VolumeSpike
from app.kr_strategy_pool.strategies.s13_last_hour_momentum import S13LastHourMomentum
from app.kr_strategy_pool.strategies.s16_stochastic_reversion import S16StochasticReversion
from app.kr_strategy_pool.strategies.s18_zscore_reversion import S18ZScoreReversion
from app.kr_strategy_pool.strategies.s20_ichimoku import S20IchimokuMomentum
from app.kr_strategy_pool.strategies.s25_lunch_fade import S25LunchFade
from app.kr_strategy_pool.strategies.s1_rsi_reversion import S1RsiReversion
from app.kr_strategy_pool.strategies.s5_vwap_reversion import S5VwapReversion
from app.kr_strategy_pool.strategies.s12_closing_range_breakout import S12ClosingRangeBreakout
from app.kr_strategy_pool.strategies.s26_open_drive import S26OpenDrive


# 각 전략의 핵심 파라미터 grid
# (다른 파라미터는 default 유지)
GRID: Dict[Type[KrStrategyBase], Dict[str, List]] = {
    S2BBReversion: {
        "bb_period": [15, 20, 25, 30],
        "bb_std": [1.5, 2.0, 2.5],
    },
    S4OpeningRangeBreakout: {
        "or_minutes": [20, 30, 45, 60],
        "buffer_pct": [0.0005, 0.001, 0.002],
        "sl_pct": [0.015, 0.02, 0.025],
    },
    S9VolumeSpike: {
        "vol_window": [10, 20, 30],
        "spike_mult": [2.0, 3.0, 4.0, 5.0],
    },
    S13LastHourMomentum: {
        "entry_time": ["13:30", "14:00", "14:30"],
        "min_intraday_gain": [0.003, 0.005, 0.01, 0.015],
    },
    S16StochasticReversion: {
        "k_period": [9, 14, 21],
        "oversold": [15, 20, 25],
        "overbought": [75, 80, 85],
    },
    S18ZScoreReversion: {
        "period": [20, 30, 50],
        "entry_z": [-1.5, -2.0, -2.5],
    },
    S20IchimokuMomentum: {
        "tenkan": [7, 9, 13],
        "kijun": [20, 26, 34],
    },
    S25LunchFade: {
        "lunch_start": ["11:00", "11:30", "12:00"],
        "lunch_end": ["12:00", "12:30", "13:00"],
    },
    S1RsiReversion: {
        "rsi_period": [10, 14, 21],
        "oversold": [25, 30, 35],
        "overbought": [65, 70, 75],
    },
    S5VwapReversion: {
        "lower_band_pct": [0.005, 0.01, 0.015, 0.02, 0.025],
    },
    S12ClosingRangeBreakout: {
        "cr_start": ["14:00", "14:30"],
        "cr_end": ["14:30", "15:00"],
        "buffer_pct": [0.0005, 0.001, 0.002],
    },
    S26OpenDrive: {
        "min_open_drive_pct": [0.003, 0.005, 0.008, 0.012, 0.018],
        "tp_pct": [0.02, 0.04, 0.06],
    },
}


def cartesian(grid: Dict[str, List]) -> List[Dict]:
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


async def run_one(
    cls: Type[KrStrategyBase],
    feed_5m: List[Dict],
    initial_capital: int,
    symbol: str,
    overrides: Dict,
) -> Dict:
    eng = KrBacktestEngine(cls, exchange_name="Kiwoom")
    cfg = {"symbol": symbol, **overrides}
    stats = await eng.run_single_backtest(
        config=cfg, feed=feed_5m, initial_capital=initial_capital, symbol=symbol,
    )
    return {
        "return_pct": stats.get("return_pct", 0.0),
        "sharpe": stats.get("sharpe_ratio") or 0,
        "max_drawdown": stats.get("max_drawdown") or 0,
        "win_rate": stats.get("win_rate") or 0,
        "trades": stats.get("trades_count", 0),
        "friction": stats.get("kr_total_friction", 0.0),
    }


def composite_score(r: Dict) -> float:
    """Sharpe 우선 + return tiebreak + maxDD penalty."""
    sh = r.get("sharpe", 0) or 0
    ret = r.get("return_pct", 0) or 0
    mdd = r.get("max_drawdown", 0) or 0
    n = r.get("trades", 0)
    score = sh * 5 + ret * 0.3
    if mdd < -25:
        score -= abs(mdd + 25) * 0.5
    if n < 10:
        score -= 5  # 너무 적은 trade는 noise
    return score


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--run-id", default=None)
    args = p.parse_args()

    run_id = args.run_id or f"sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(__file__).resolve().parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.jsonl"

    print(f"Loading 1m feed for {args.symbol} from {args.start}...")
    feed_1m = fetch_1m_feed(engine, args.symbol, start_date=args.start)
    feed_5m = resample_ohlcv(feed_1m, "5min")
    print(f"  5m bars: {len(feed_5m)}")

    total_combos = sum(len(cartesian(grid)) for grid in GRID.values())
    print(f"\nGrid sweep: {len(GRID)} strategies, {total_combos} total backtests")
    print(f"Output: {out_path}\n")

    started = datetime.now()
    best_per_strategy = {}
    all_results = []

    with open(out_path, "w") as f_out:
        for idx, (cls, grid) in enumerate(GRID.items(), 1):
            combos = cartesian(grid)
            strat_name = getattr(cls, "name", cls.__name__)
            print(f"[{idx}/{len(GRID)}] {strat_name}: {len(combos)} combos")

            results = []
            for combo in combos:
                r = await run_one(cls, feed_5m, args.capital, args.symbol, combo)
                row = {
                    "strategy": strat_name,
                    "params": combo,
                    **r,
                    "score": composite_score(r),
                }
                f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                results.append(row)

            # best per strategy by score
            results.sort(key=lambda x: x["score"], reverse=True)
            best = results[0]
            best_per_strategy[strat_name] = best
            all_results.extend(results)

            # 상위 3 sample
            print(f"   best: {best['params']} → ret={best['return_pct']:+.2f}% "
                  f"sh={best['sharpe']:.2f} mdd={best['max_drawdown']:+.2f}% "
                  f"n={best['trades']} score={best['score']:.2f}")

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\nElapsed: {elapsed:.1f}s for {len(all_results)} backtests")
    print(f"Output : {out_path}")

    # 종합 표
    print(f"\n=== Best params per strategy (sorted by score) ===")
    print(f"{'strategy':<28} {'return':>8} {'sharpe':>7} {'maxDD':>8} {'trades':>7} {'score':>7} {'best params'}")
    print("-" * 130)
    bests = sorted(best_per_strategy.values(), key=lambda x: x["score"], reverse=True)
    for b in bests:
        params_str = ", ".join(f"{k}={v}" for k, v in b["params"].items())
        print(f"{b['strategy']:<28} {b['return_pct']:>+7.2f}% {b['sharpe']:>7.2f} "
              f"{b['max_drawdown']:>+7.2f}% {b['trades']:>7} {b['score']:>7.2f}  {params_str}")

    # Default vs Best 향상도 (default = 첫 번째 grid 값들)
    print(f"\n=== Sensitivity: best vs worst within each strategy's grid ===")
    print(f"{'strategy':<28} {'best ret':>9} {'worst ret':>9} {'spread':>8} {'best sh':>7} {'worst sh':>8}")
    print("-" * 90)
    for cls, grid in GRID.items():
        strat_name = getattr(cls, "name", cls.__name__)
        rs = [r for r in all_results if r["strategy"] == strat_name]
        rs.sort(key=lambda x: x["return_pct"])
        if not rs:
            continue
        wo, be = rs[0], rs[-1]
        spread = be["return_pct"] - wo["return_pct"]
        print(f"{strat_name:<28} {be['return_pct']:>+8.2f}% {wo['return_pct']:>+8.2f}% "
              f"{spread:>+7.2f}pp {be['sharpe']:>+7.2f} {wo['sharpe']:>+7.2f}")


if __name__ == "__main__":
    asyncio.run(main())
