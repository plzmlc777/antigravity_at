"""
Phase 3 (Crypto): build perf_matrix_<symbol>.jsonl — walk-forward performance matrix.

For each N-day window (no overlap), encode environment at window start
and run a 1m backtest of every multi-TF crypto strategy on that window's feed.

KR build_perf_matrix.py의 mirror — 24/7 시장이라 trading_days 대신 calendar days.

Output rows: {window_id, env_ts, env: [10], strategies: {name: {sharpe, ...}}}
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.crypto_strategy_pool.data_utils import fetch_1m_feed
from app.crypto_strategy_pool.env_encoder import encode_environment, FEATURE_NAMES
from app.crypto_strategy_pool.tournament import CryptoTournament
from app.crypto_strategy_pool.meta_strategy_registry import META_STRATEGY_REGISTRY


def calendar_days(feed: List[Dict[str, Any]]) -> List[str]:
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["d"] = df["ts"].dt.date.astype(str)
    return sorted(df["d"].unique().tolist())


def window_feed(feed: List[Dict[str, Any]], days: List[str]) -> List[Dict[str, Any]]:
    keep = set(days)
    return [c for c in feed if c["timestamp"][:10] in keep]


async def run_window(
    feed_full: List[Dict[str, Any]],
    win_days: List[str],
    capital: int,
    symbol: str,
) -> Dict[str, Any]:
    feed_win = window_feed(feed_full, win_days)
    if len(feed_win) < 100:
        return {}
    tour = CryptoTournament(symbol, feed_win, capital, exchange_name="BinanceFutures")
    for cls in META_STRATEGY_REGISTRY.values():
        tour.add(cls)
    results = await tour.run_all()
    out = {}
    for r in results:
        out[r.name] = {
            "sharpe": r.sharpe if r.sharpe is not None else 0.0,
            "return_pct": r.return_pct,
            "trades": r.trades,
            "max_drawdown": r.max_drawdown if r.max_drawdown is not None else 0.0,
        }
    return out


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--warmup-days", type=int, default=30)
    p.add_argument("--window-days", type=int, default=5)
    p.add_argument("--capital", type=int, default=10_000)
    p.add_argument("--out", default=None,
                   help="filename (default: perf_matrix_<symbol>.jsonl)")
    args = p.parse_args()

    out_name = args.out or f"perf_matrix_{args.symbol}.jsonl"

    print(f"Loading feed {args.symbol} {args.start}..{args.end}")
    feed = fetch_1m_feed(engine, args.symbol, args.start, args.end)
    print(f"  bars: {len(feed)}")

    days = calendar_days(feed)
    print(f"  calendar days: {len(days)}")

    if len(days) < args.warmup_days + args.window_days:
        raise SystemExit(f"not enough calendar days: {len(days)}")

    windows = []
    i = args.warmup_days
    while i + args.window_days <= len(days):
        win_days = days[i : i + args.window_days]
        windows.append({"window_id": len(windows), "days": win_days})
        i += args.window_days
    print(f"  windows: {len(windows)} (warmup={args.warmup_days}, size={args.window_days})")

    out_dir = Path(__file__).resolve().parent / "runs" / "crypto_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name

    started = datetime.now()
    rows = []
    with open(out_path, "w") as f:
        for w in windows:
            d0 = w["days"][0]
            env_ts = f"{d0}T00:00:00"
            env_vec = encode_environment(feed, env_ts)

            sharpes = await run_window(feed, w["days"], args.capital, args.symbol)
            row = {
                "window_id": w["window_id"],
                "env_ts": env_ts,
                "env_features": FEATURE_NAMES,
                "env": env_vec.tolist(),
                "win_start": w["days"][0],
                "win_end": w["days"][-1],
                "strategies": sharpes,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            rows.append(row)

            if sharpes:
                best = max(sharpes.items(), key=lambda x: x[1]["sharpe"])
                print(f"  win {w['window_id']:>3d} [{w['days'][0]}..{w['days'][-1]}] "
                      f"best={best[0]:<28} sh={best[1]['sharpe']:+.2f}")
            else:
                print(f"  win {w['window_id']:>3d} [{w['days'][0]}..{w['days'][-1]}] EMPTY")

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\nElapsed: {elapsed:.1f}s")
    print(f"Output : {out_path}")

    best_per_window = []
    for r in rows:
        if r["strategies"]:
            best = max(r["strategies"].items(), key=lambda x: x[1]["sharpe"])
            best_per_window.append(best[0])
    from collections import Counter
    counter = Counter(best_per_window)
    print(f"\n=== Best strategy per window distribution ===")
    for name, count in counter.most_common():
        print(f"  {name:<32}  {count} / {len(rows)}")

    if counter and counter.most_common(1)[0][1] >= 0.7 * len(rows):
        print("\nWARN: single strategy dominates >70% of windows")
    else:
        print("\nDIVERSITY OK: best-strategy distribution is spread")


if __name__ == "__main__":
    asyncio.run(main())
