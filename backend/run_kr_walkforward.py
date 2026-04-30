"""
KR Walk-Forward 검증 + 파라미터 robustness mini-sweep.

대상: S2 BB Reversion (토너먼트 1위)
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import (
    fetch_1m_feed, resample_ohlcv, walk_forward_windows,
)
from app.core.kr_backtest_engine import KrBacktestEngine
from app.kr_strategy_pool.strategies.s2_bb_reversion import S2BBReversion


async def run_one(feed, capital, symbol, params):
    eng = KrBacktestEngine(S2BBReversion, exchange_name="Kiwoom")
    cfg = {"symbol": symbol, **params}
    return await eng.run_single_backtest(
        config=cfg, feed=feed, initial_capital=capital, symbol=symbol
    )


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--train-bars", type=int, default=3500, help="train window size in 5m bars (~50 days)")
    p.add_argument("--test-bars", type=int, default=1000, help="test window size in 5m bars (~14 days)")
    args = p.parse_args()

    print(f"Loading 1m feed for {args.symbol} from {args.start}...")
    feed_1m = fetch_1m_feed(engine, args.symbol, start_date=args.start)
    feed_5m = resample_ohlcv(feed_1m, "5min")
    print(f"  5m bars: {len(feed_5m)}")

    # Walk-forward windows
    windows = walk_forward_windows(feed_5m, args.train_bars, args.test_bars)
    print(f"  windows: {len(windows)} (train={args.train_bars} test={args.test_bars} bars)")

    # ───────────── Walk-Forward (BB 20, std 2.0 기본) ─────────────
    print("\n=== Walk-Forward (params: bb_period=20 bb_std=2.0) ===")
    print(f"{'fold':<6} {'train_ret':>10} {'test_ret':>10} {'tr_sharpe':>10} {'te_sharpe':>10} {'tr_winR':>8} {'te_winR':>8} {'tr_n':>5} {'te_n':>5}")
    print("-" * 80)
    test_returns = []
    for i, (train, test) in enumerate(windows, 1):
        tr_stats = await run_one(train, args.capital, args.symbol, {})
        te_stats = await run_one(test, args.capital, args.symbol, {})
        test_returns.append(te_stats.get("return_pct", 0.0))
        print(
            f"{i:<6} {tr_stats.get('return_pct',0):>+9.2f}% {te_stats.get('return_pct',0):>+9.2f}% "
            f"{tr_stats.get('sharpe_ratio',0) or 0:>10.2f} {te_stats.get('sharpe_ratio',0) or 0:>10.2f} "
            f"{tr_stats.get('win_rate',0) or 0:>7.1f}% {te_stats.get('win_rate',0) or 0:>7.1f}% "
            f"{tr_stats.get('trades_count',0):>5} {te_stats.get('trades_count',0):>5}"
        )
    if test_returns:
        avg_test = sum(test_returns) / len(test_returns)
        win_folds = sum(1 for r in test_returns if r > 0)
        print(f"\n  test avg return: {avg_test:+.2f}%   profitable folds: {win_folds}/{len(test_returns)}")

    # ───────────── Parameter mini-sweep on full data ─────────────
    print("\n=== Param sweep (full data, in-sample) ===")
    print(f"{'period':<8} {'std':<5} {'return':>8} {'sharpe':>7} {'winR':>7} {'maxDD':>8} {'trades':>7}")
    print("-" * 60)
    best = None
    for period in [15, 20, 25, 30]:
        for std in [1.5, 2.0, 2.5]:
            stats = await run_one(
                feed_5m, args.capital, args.symbol,
                {"bb_period": period, "bb_std": std},
            )
            row = (
                period, std,
                stats.get("return_pct", 0),
                stats.get("sharpe_ratio") or 0,
                stats.get("win_rate") or 0,
                stats.get("max_drawdown") or 0,
                stats.get("trades_count", 0),
            )
            print(f"{row[0]:<8} {row[1]:<5} {row[2]:>+7.2f}% {row[3]:>7.2f} {row[4]:>6.1f}% {row[5]:>7.2f}% {row[6]:>7}")
            if best is None or row[2] > best[2]:
                best = row
    if best:
        print(f"\n  best: bb_period={best[0]}, bb_std={best[1]} → return {best[2]:+.2f}% sharpe {best[3]:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
