"""
MLDirect walk-forward validator.

Workflow:
  1. Load full feed (e.g. 6 months 1m bars)
  2. For each test window (5 days), train on all PRIOR data, backtest on window
  3. Aggregate per-window stats + monthly estimate

Usage:
  PYTHONPATH=. python3 run_mldirect_walkforward.py --market crypto --symbol BTCUSDT \\
      --start 2025-11-01 --end 2026-04-30 --history-days 60
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.meta_strategy_pool.mldirect_engine import MLDirectEngine, MLDirectConfig, FEATURE_NAMES


def fetch_feed(market, symbol, start, end):
    if market == "kr":
        from app.kr_strategy_pool.data_utils import fetch_1m_feed
    else:
        from app.crypto_strategy_pool.data_utils import fetch_1m_feed
    return fetch_1m_feed(engine, symbol, start, end)


def calendar_days(feed):
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["d"] = df["ts"].dt.date.astype(str)
    return sorted(df["d"].unique().tolist())


def slice_by_days(feed, days):
    keep = set(days)
    return [c for c in feed if c["timestamp"][:10] in keep]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--market", required=True, choices=["kr", "crypto"])
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--history-days", type=int, default=60)
    p.add_argument("--window-days", type=int, default=5)
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--fee-rate", type=float, default=None)
    # MLDirect hyperparams
    p.add_argument("--target-horizon-bars", type=int, default=30)
    p.add_argument("--target-threshold-pct", type=float, default=0.003)
    p.add_argument("--tp-pct", type=float, default=0.005)
    p.add_argument("--sl-pct", type=float, default=0.003)
    p.add_argument("--max-hold-bars", type=int, default=30)
    p.add_argument("--decision-step", type=int, default=5)
    p.add_argument("--min-prob", type=float, default=0.62)
    args = p.parse_args()

    fee = args.fee_rate
    if fee is None:
        fee = 0.0021 if args.market == "kr" else 0.0004

    cfg = MLDirectConfig(
        target_horizon_bars=args.target_horizon_bars,
        target_threshold_pct=args.target_threshold_pct,
        tp_pct=args.tp_pct,
        sl_pct=args.sl_pct,
        max_hold_bars=args.max_hold_bars,
        decision_step=args.decision_step,
        min_prob=args.min_prob,
    )

    print("=" * 80)
    print(f"MLDirect Walk-Forward: {args.market.upper()} {args.symbol}  fee={fee}")
    print(f"  data    : {args.start}..{args.end}")
    print(f"  history : {args.history_days}d initial → expanding")
    print(f"  window  : {args.window_days}d each test")
    print(f"  target  : up >={cfg.target_threshold_pct*100:.2f}% in {cfg.target_horizon_bars} bars")
    print(f"  trade   : tp={cfg.tp_pct} sl={cfg.sl_pct} max_hold={cfg.max_hold_bars} P>={cfg.min_prob}")
    print("=" * 80)

    print(f"\nLoading feed...")
    t0 = time.time()
    feed = fetch_feed(args.market, args.symbol, args.start, args.end)
    print(f"  {len(feed)} bars in {time.time()-t0:.1f}s")

    days = calendar_days(feed)
    print(f"  {len(days)} unique days")

    if len(days) < args.history_days + args.window_days:
        raise SystemExit(f"Not enough days: {len(days)}")

    windows = []
    i = args.history_days
    while i + args.window_days <= len(days):
        windows.append({
            "id": len(windows),
            "history_days": days[:i],
            "test_days": days[i : i + args.window_days],
        })
        i += args.window_days
    print(f"  {len(windows)} test windows")

    out_dir = Path(__file__).resolve().parent / "runs" / "mldirect" / args.symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"mldirect_{args.symbol}_{int(time.time())}.jsonl"

    print(f"\n--- Walk-forward results ---")
    print(f"{'win':<5} {'test_range':<25} {'n_train':<8} {'pos_rate':<9} "
          f"{'sigs':<6} {'tr':<5} {'winR':<6} {'ret%':<8} {'mdd%':<7}")
    print("-" * 95)

    started = time.time()
    last_imp = None
    win_results = []

    with open(log_path, "w") as logf:
        for w in windows:
            history_feed = slice_by_days(feed, w["history_days"])
            test_feed = slice_by_days(feed, w["test_days"])

            try:
                ml = MLDirectEngine(cfg).fit(history_feed)
            except ValueError as e:
                print(f"win {w['id']:<3} SKIP: {e}")
                continue

            result = ml.backtest(test_feed, initial_capital=args.capital, fee_rate=fee)
            win_results.append(result)

            test_range = f"{w['test_days'][0]}..{w['test_days'][-1]}"
            print(f"{w['id']:<5} {test_range:<25} {result['n_train']:<8} "
                  f"{result['train_pos_rate']:<9.3f} {result['signal_count']:<6} "
                  f"{result['trades_count']:<5} {result['win_rate']:>4.1f}%  "
                  f"{result['return_pct']:>+6.2f}%  {result['max_drawdown']:>+5.2f}%")

            log_row = {
                "window_id": w["id"],
                "test_range": test_range,
                "n_train": result["n_train"],
                "train_pos_rate": result["train_pos_rate"],
                "signal_count": result["signal_count"],
                "trades_count": result["trades_count"],
                "win_rate": result["win_rate"],
                "return_pct": result["return_pct"],
                "sharpe": result["sharpe"],
                "max_drawdown": result["max_drawdown"],
                "avg_proba_when_signal": result["avg_proba_when_signal"],
            }
            logf.write(json.dumps(log_row) + "\n")
            logf.flush()

            last_imp = ml._feature_importances

    elapsed = time.time() - started

    print("\n" + "=" * 80)
    print(f"=== SUMMARY ({len(win_results)} windows, {elapsed:.0f}s) ===")
    print("=" * 80)
    if win_results:
        rets = [r["return_pct"] for r in win_results]
        trades = [r["trades_count"] for r in win_results]
        winr = [r["win_rate"] for r in win_results if r["trades_count"] > 0]
        sigs = [r["signal_count"] for r in win_results]

        total_days = len(win_results) * args.window_days
        sum_ret = sum(rets)
        monthly_days = 22 if args.market == "kr" else 30
        monthly_ret = sum_ret / total_days * monthly_days

        cum_eq = args.capital
        for r in rets:
            cum_eq *= (1 + r / 100)

        print(f"  test days       : {total_days}")
        print(f"  total signals   : {sum(sigs)} (avg {np.mean(sigs):.1f}/window)")
        print(f"  total trades    : {sum(trades)} (avg {np.mean(trades):.1f}/window)")
        print(f"  avg win rate    : {np.mean(winr) if winr else 0:.1f}%")
        print(f"  ")
        print(f"  sum return      : {sum_ret:+.2f}%")
        print(f"  avg per window  : {np.mean(rets):+.3f}%")
        print(f"  >>> monthly est : {monthly_ret:+.2f}% <<<")
        print(f"  cumulative      : ${cum_eq:,.2f} (start ${args.capital:,.0f}, "
              f"+{(cum_eq/args.capital - 1)*100:+.2f}%)")
        win_pos = sum(1 for r in rets if r > 0)
        print(f"  positive wins   : {win_pos}/{len(rets)} ({win_pos/len(rets)*100:.0f}%)")

        if last_imp:
            print(f"\n  Feature importance (last train, top 10):")
            for f, v in sorted(last_imp.items(), key=lambda x: -x[1])[:10]:
                print(f"    {f:<28} {v:.4f}")

    print(f"\n  log saved: {log_path}")


if __name__ == "__main__":
    main()
