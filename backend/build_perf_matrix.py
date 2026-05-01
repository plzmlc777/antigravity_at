"""
Phase 3: build perf_matrix_v1.jsonl — walk-forward performance matrix.

For each 5-trading-day window (no overlap), encode environment at window start
and run a 1m backtest of every multi-TF strategy on that window's feed.

Output rows: {window_id, env_ts, env: [13], strategy_sharpes: {name: sharpe}}
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.kr_strategy_pool.env_encoder import encode_environment, FEATURE_NAMES
from app.kr_strategy_pool.tournament import KrTournament

from app.kr_strategy_pool.strategies.s40_vwap_atr_1m5m import S40_VWAP_ATR_1m5m
from app.kr_strategy_pool.strategies.s41_bb_trend_5m1h import S41_BB_Trend_5m1h
from app.kr_strategy_pool.strategies.s42_rsi_macd_1m import S42_RSI_MACD_1m
from app.kr_strategy_pool.strategies.s43_donchian_atr_1m1h import S43_Donchian_ATR_1m1h
from app.kr_strategy_pool.strategies.s44_ema_time_1m1h import S44_EMA_Time_1m1h
from app.kr_strategy_pool.strategies.s45_macd_donchian_5m1d import S45_MACD_Donchian_5m1d
from app.kr_strategy_pool.strategies.s46_triple_vote_1m5m1h import S46_TripleVote_1m5m1h
from app.kr_strategy_pool.strategies.s47_bb_volume_5m import S47_BB_Volume_5m
from app.kr_strategy_pool.strategies.s48_macd_atr_1h import S48_MACD_ATR_1h
from app.kr_strategy_pool.strategies.s49_vwap_lunch_1m5m import S49_VWAP_Lunch_1m5m
from app.kr_strategy_pool.strategies.s50_supertrend_adx_1m1h import S50_Supertrend_ADX_1m1h
from app.kr_strategy_pool.strategies.s51_williams_volume_5m import S51_Williams_Volume_5m

POOL = [
    S40_VWAP_ATR_1m5m, S41_BB_Trend_5m1h, S42_RSI_MACD_1m,
    S43_Donchian_ATR_1m1h, S44_EMA_Time_1m1h, S45_MACD_Donchian_5m1d,
    S46_TripleVote_1m5m1h, S47_BB_Volume_5m, S48_MACD_ATR_1h,
    S49_VWAP_Lunch_1m5m, S50_Supertrend_ADX_1m1h, S51_Williams_Volume_5m,
]


def trading_days(feed: List[Dict[str, Any]]) -> List[str]:
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
) -> Dict[str, float]:
    feed_win = window_feed(feed_full, win_days)
    if len(feed_win) < 100:
        return {}
    tour = KrTournament(symbol, feed_win, capital, exchange_name="Kiwoom")
    for cls in POOL:
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
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-11-14")
    p.add_argument("--end", default="2026-04-30")
    p.add_argument("--warmup-days", type=int, default=30)
    p.add_argument("--window-days", type=int, default=5)
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--out", default="perf_matrix_v1.jsonl")
    args = p.parse_args()

    print(f"Loading feed {args.symbol} {args.start}..{args.end}")
    feed = fetch_1m_feed(engine, args.symbol, args.start, args.end)
    print(f"  bars: {len(feed)}")

    days = trading_days(feed)
    print(f"  trading days: {len(days)}")

    if len(days) < args.warmup_days + args.window_days:
        raise SystemExit(f"not enough trading days: {len(days)}")

    # build windows
    windows = []
    i = args.warmup_days
    while i + args.window_days <= len(days):
        win_days = days[i : i + args.window_days]
        windows.append({"window_id": len(windows), "days": win_days})
        i += args.window_days
    print(f"  windows: {len(windows)} (warmup={args.warmup_days}, size={args.window_days})")

    out_dir = Path(__file__).resolve().parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / args.out

    started = datetime.now()
    rows = []
    with open(out_path, "w") as f:
        for w in windows:
            # env_ts = first 1m bar timestamp of window's first day at 09:00
            d0 = w["days"][0]
            env_ts = f"{d0}T09:00:00"
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
            rows.append(row)

            best = max(sharpes.items(), key=lambda x: x[1]["sharpe"], default=(None, None))
            best_name = best[0] if best[0] else "n/a"
            best_sh = best[1]["sharpe"] if best[1] else 0.0
            print(f"  win {w['window_id']:>2d} [{w['days'][0]}..{w['days'][-1]}] "
                  f"best={best_name:<28} sh={best_sh:+.2f}")

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\nElapsed: {elapsed:.1f}s")
    print(f"Output : {out_path}")

    # summary: best strategy per window distribution
    best_per_window = []
    for r in rows:
        best = max(r["strategies"].items(), key=lambda x: x[1]["sharpe"], default=(None, None))
        if best[0]:
            best_per_window.append(best[0])
    from collections import Counter
    counter = Counter(best_per_window)
    print(f"\n=== Best strategy per window distribution ===")
    for name, count in counter.most_common():
        print(f"  {name:<32}  {count} / {len(rows)}")

    # acceptance: not a single strategy dominant
    if counter and counter.most_common(1)[0][1] >= 0.7 * len(rows):
        print("\nWARN: single strategy dominates >70% of windows")
    else:
        print("\nDIVERSITY OK: best-strategy distribution is spread")


if __name__ == "__main__":
    asyncio.run(main())
