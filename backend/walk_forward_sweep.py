"""
Walk-Forward OOS Validation.

Train 60d → grid sweep → 각 전략의 train-best params 발견.
Test 23d → 그 train-best params로 backtest.
전략별 IS vs OOS 결과 비교 → robust 전략 식별.
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
from grid_sweep import GRID, cartesian, run_one, composite_score


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--train-days", type=int, default=60,
                   help="train 거래일 수 (default 60d / 23d test)")
    p.add_argument("--run-id", default=None)
    args = p.parse_args()

    run_id = args.run_id or f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(__file__).resolve().parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading 1m feed for {args.symbol} from {args.start}...")
    feed_1m = fetch_1m_feed(engine, args.symbol, start_date=args.start)
    feed_5m = resample_ohlcv(feed_1m, "5min")
    days = sorted({c["timestamp"][:10] for c in feed_5m})
    print(f"  total: {len(feed_5m)} 5m bars / {len(days)} trading days")

    train_days = args.train_days
    test_days = len(days) - train_days
    train_cutoff = days[train_days - 1]   # last day of train
    test_start = days[train_days]
    test_end = days[-1]
    print(f"  train: {days[0]} ~ {train_cutoff} ({train_days} days)")
    print(f"  test : {test_start} ~ {test_end} ({test_days} days)\n")

    train_feed = [c for c in feed_5m if c["timestamp"][:10] <= train_cutoff]
    test_feed = [c for c in feed_5m if c["timestamp"][:10] > train_cutoff]

    train_results: Dict[str, List] = {}
    print(f"=== Phase 1: Train sweep ({train_days}d) ===")
    for idx, (cls, grid) in enumerate(GRID.items(), 1):
        combos = cartesian(grid)
        strat = getattr(cls, "name", cls.__name__)
        rs = []
        for combo in combos:
            r = await run_one(cls, train_feed, args.capital, args.symbol, combo)
            rs.append({"params": combo, "score": composite_score(r), **r})
        rs.sort(key=lambda x: x["score"], reverse=True)
        train_results[strat] = rs
        best = rs[0]
        print(f"  [{idx:>2}/{len(GRID)}] {strat:<28} train: ret={best['return_pct']:+6.2f}% "
              f"sh={best['sharpe']:>5.2f} mdd={best['max_drawdown']:+6.2f}% "
              f"n={best['trades']:>3} | {best['params']}")

    # Phase 2: Test backtest with train-best params
    print(f"\n=== Phase 2: OOS Test ({test_days}d) ===")
    print(f"{'strategy':<28} {'IS ret':>8} {'IS sh':>6} | {'OOS ret':>8} {'OOS sh':>6} {'OOS mdd':>8} {'OOS n':>5} | {'verdict'}")
    print("-" * 130)

    rows = []
    for cls in GRID.keys():
        strat = getattr(cls, "name", cls.__name__)
        train_best = train_results[strat][0]
        train_params = train_best["params"]
        is_ret = train_best["return_pct"]
        is_sh = train_best["sharpe"]

        oos = await run_one(cls, test_feed, args.capital, args.symbol, train_params)
        oos_ret = oos["return_pct"]
        oos_sh = oos["sharpe"] or 0
        oos_mdd = oos["max_drawdown"] or 0
        oos_n = oos["trades"]

        # robust 판정 — IS와 OOS 모두 흑자 또는 OOS sharpe > 1
        if oos_ret > 0 and oos_sh > 0.5:
            verdict = "✅ ROBUST"
        elif oos_ret > -2 and oos_sh > 0:
            verdict = "🟡 borderline"
        elif oos_n < 5:
            verdict = "⚠️  low_n"
        else:
            verdict = "❌ overfit"

        print(f"{strat:<28} {is_ret:>+7.2f}% {is_sh:>+6.2f} | "
              f"{oos_ret:>+7.2f}% {oos_sh:>+6.2f} {oos_mdd:>+7.2f}% {oos_n:>5} | {verdict}")

        rows.append({
            "strategy": strat,
            "train_params": train_params,
            "is_return": is_ret, "is_sharpe": is_sh, "is_max_dd": train_best["max_drawdown"],
            "is_trades": train_best["trades"],
            "oos_return": oos_ret, "oos_sharpe": oos_sh, "oos_max_dd": oos_mdd,
            "oos_trades": oos_n, "verdict": verdict,
        })

    out_path = out_dir / f"{run_id}.json"
    with open(out_path, "w") as f:
        json.dump({
            "train_days": train_days, "test_days": test_days,
            "train_range": [days[0], train_cutoff],
            "test_range": [test_start, test_end],
            "results": rows,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out_path}")

    # Robust 전략 요약
    robust = [r for r in rows if "ROBUST" in r["verdict"]]
    border = [r for r in rows if "borderline" in r["verdict"]]
    overfit = [r for r in rows if "overfit" in r["verdict"]]
    print(f"\n=== OOS Verdict Summary ===")
    print(f"  ✅ ROBUST    : {len(robust)} → {[r['strategy'] for r in robust]}")
    print(f"  🟡 borderline: {len(border)} → {[r['strategy'] for r in border]}")
    print(f"  ❌ overfit   : {len(overfit)} → {[r['strategy'] for r in overfit]}")


if __name__ == "__main__":
    asyncio.run(main())
