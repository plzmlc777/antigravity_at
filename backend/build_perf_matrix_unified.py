"""
Phase A: Unified perf_matrix builder — KR/Crypto 양쪽에서 동일한 unified env_encoder 사용.

Usage:
    # KR
    PYTHONPATH=. python3 build_perf_matrix_unified.py --market kr --symbol 061090 \\
        --start 2025-11-14 --end 2026-04-30

    # Crypto
    PYTHONPATH=. python3 build_perf_matrix_unified.py --market crypto --symbol BTCUSDT \\
        --start 2025-05-01 --end 2026-04-30

기존 build_perf_matrix.py / build_perf_matrix_crypto.py 와 동일한 windows + tournament
로직을 사용하지만, encode_environment 만 unified 버전으로 교체.
출력: runs/<market>_paper/sweeps/perf_matrix_<symbol>_unified.jsonl
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
from app.meta_strategy_pool.env_encoder import get_encoder


def _market_setup(market: str):
    """Return (fetch_1m_feed, tournament_class, registry, exchange_name, encoder_instance, run_root)."""
    encoder = get_encoder(market)
    if market == "kr":
        from app.kr_strategy_pool.data_utils import fetch_1m_feed
        from app.kr_strategy_pool.tournament import KrTournament
        from app.kr_strategy_pool.meta_strategy_registry import META_STRATEGY_REGISTRY
        return (fetch_1m_feed, KrTournament, META_STRATEGY_REGISTRY,
                "Kiwoom", encoder, "kr_paper")
    elif market == "crypto":
        from app.crypto_strategy_pool.data_utils import fetch_1m_feed
        from app.crypto_strategy_pool.tournament import CryptoTournament
        from app.crypto_strategy_pool.meta_strategy_registry import META_STRATEGY_REGISTRY
        return (fetch_1m_feed, CryptoTournament, META_STRATEGY_REGISTRY,
                "BinanceFutures", encoder, "crypto_paper")
    elif market == "us":
        # Stub: US strategy pool not yet built
        raise NotImplementedError("US strategy pool not yet implemented")
    raise ValueError(f"unknown market: {market}")


def _calendar_days(feed: List[Dict[str, Any]], market: str) -> List[str]:
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    if market == "kr":
        # KR: use trading dates only (weekday non-holiday — proxied by data presence)
        df["d"] = df["ts"].dt.date.astype(str)
    else:
        df["d"] = df["ts"].dt.date.astype(str)
    return sorted(df["d"].unique().tolist())


def _window_feed(feed: List[Dict[str, Any]], days: List[str]) -> List[Dict[str, Any]]:
    keep = set(days)
    return [c for c in feed if c["timestamp"][:10] in keep]


async def _run_window(
    feed_full: List[Dict[str, Any]],
    win_days: List[str],
    capital: int,
    symbol: str,
    tournament_cls,
    registry,
    exchange_name: str,
) -> Dict[str, Any]:
    feed_win = _window_feed(feed_full, win_days)
    if len(feed_win) < 100:
        return {}
    tour = tournament_cls(symbol, feed_win, capital, exchange_name=exchange_name)
    for cls in registry.values():
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
    p.add_argument("--market", required=True, choices=["kr", "crypto"])
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--warmup-days", type=int, default=30)
    p.add_argument("--window-days", type=int, default=5)
    p.add_argument("--capital", type=int, default=None,
                   help="default: KR 3000000, Crypto 10000")
    p.add_argument("--out", default=None,
                   help="filename (default: perf_matrix_<symbol>_unified.jsonl)")
    args = p.parse_args()

    fetch_fn, tournament_cls, registry, exchange_name, encoder, run_root = _market_setup(args.market)
    capital = args.capital or (3_000_000 if args.market == "kr" else 10_000)
    out_name = args.out or f"perf_matrix_{args.symbol}_unified.jsonl"
    print(f"[unified] encoder={encoder.MARKET_TAG} dim={encoder.feature_dim}")

    print(f"[unified] market={args.market}  symbol={args.symbol}  capital={capital}")
    print(f"[unified] feed range: {args.start}..{args.end}")
    feed = fetch_fn(engine, args.symbol, args.start, args.end)
    print(f"  bars: {len(feed)}")

    days = _calendar_days(feed, args.market)
    print(f"  calendar days: {len(days)}")

    if len(days) < args.warmup_days + args.window_days:
        raise SystemExit(f"not enough days: {len(days)}")

    windows = []
    i = args.warmup_days
    while i + args.window_days <= len(days):
        win_days = days[i : i + args.window_days]
        windows.append({"window_id": len(windows), "days": win_days})
        i += args.window_days
    print(f"  windows: {len(windows)} (warmup={args.warmup_days}, size={args.window_days})")

    out_dir = Path(__file__).resolve().parent / "runs" / run_root / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / out_name

    started = datetime.now()
    rows = []
    with open(out_path, "w") as f:
        for w in windows:
            d0 = w["days"][0]
            # KR env_ts at session open, Crypto at calendar day start (UTC)
            env_ts = f"{d0}T09:00:00" if args.market == "kr" else f"{d0}T00:00:00"
            env_vec = encoder.encode(feed, env_ts)

            sharpes = await _run_window(
                feed, w["days"], capital, args.symbol,
                tournament_cls, registry, exchange_name,
            )
            row = {
                "window_id": w["window_id"],
                "env_ts": env_ts,
                "env_features": encoder.feature_names,
                "env": env_vec.tolist(),
                "encoder_tag": encoder.MARKET_TAG,
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
                print(f"  win {w['window_id']:>3d} EMPTY")

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
