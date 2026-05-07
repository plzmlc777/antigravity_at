#!/usr/bin/env python3
"""Sweep multiple composer/backtester configs to find what beats buy-hold.

Loads data once, runs each variant, prints a comparison table.

Usage:
    python -m scripts.sweep_composer_variants --symbol 005930 --days 365
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.pattern_composer import (  # noqa: E402
    DefensiveConfig,
    DefensiveTimingBacktester,
    EventBacktestConfig,
    EventDrivenBacktester,
    FloorBacktestConfig,
    MultiBacktestConfig,
    MultiPositionEventBacktester,
    PositionFloorBacktester,
)
from app.pattern_fitness import FitnessLearner  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.pattern_scanner.types import SUPPORTED_TIMEFRAMES  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("sweep")


def load_1m(symbol: str, days: int) -> pd.DataFrame:
    db = SessionLocal()
    try:
        end = datetime.now().replace(second=0, microsecond=0)
        start = end - timedelta(days=days)
        sql = text("""SELECT timestamp, open, high, low, close, volume FROM ohlcv
                     WHERE symbol = :sym AND time_frame = '1m' AND timestamp >= :start
                     ORDER BY timestamp ASC""")
        rows = db.execute(sql, {"sym": symbol, "start": start}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--initial-capital", type=float, default=3_000_000)
    args = p.parse_args()

    sig_path = ROOT / "runs" / "pattern_scanner" / f"{args.symbol}__{args.days}d__signals.joblib"
    fit_path = ROOT / "runs" / "pattern_fitness" / f"{args.symbol}__{args.days}d__fitness.joblib"
    print(f"Loading signals + fitness + 1m + regimes...")
    signals = joblib.load(sig_path)
    fitness = FitnessLearner.load(fit_path)
    df_1m = load_1m(args.symbol, args.days)

    ohlcv_by_tf = {tf: resample_ohlcv(df_1m, tf) for tf in SUPPORTED_TIMEFRAMES}
    regime_by_tf = {}
    for tf in SUPPORTED_TIMEFRAMES:
        cls = RegimeClassifier.for_daily() if tf in ("4h", "1d") else RegimeClassifier.for_intraday()
        regime_by_tf[tf] = cls.classify(ohlcv_by_tf[tf])

    # Buy-and-hold benchmark
    bh = (df_1m.iloc[-1]["close"] - df_1m.iloc[0]["open"]) / df_1m.iloc[0]["open"]

    # Define variants
    variants = [
        {
            "name": "v2.0 single-position (baseline)",
            "type": "event",
            "config": EventBacktestConfig(sl_pct=0.02, tp_pct=0.04, long_only=True),
        },
        {
            "name": "v2.1 multi-position (5)",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=5, sl_pct=0.02, tp_pct=0.04, long_only=True),
        },
        {
            "name": "v2.2 multi-position (10)",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=10, sl_pct=0.02, tp_pct=0.04, long_only=True),
        },
        {
            "name": "v2.3 multi(10) + edge-amplifier 2.0",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=10, sl_pct=0.02, tp_pct=0.04,
                                          edge_amplifier=2.0, long_only=True),
        },
        {
            "name": "v2.4 multi(10) + adaptive SL/TP (2σ/4σ)",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=10, sl_std_mult=2.0, tp_std_mult=4.0,
                                          long_only=True),
        },
        {
            "name": "v2.5 multi(20) + edge-amp 2 + adaptive",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=20, edge_amplifier=2.0,
                                          sl_std_mult=2.0, tp_std_mult=4.0, long_only=True),
        },
        {
            "name": "v2.6 multi(20) wider SL/TP (3%/8%)",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=20, sl_pct=0.03, tp_pct=0.08,
                                          long_only=True),
        },
        {
            "name": "v2.7 multi(20) wide SL/TP + edge-amp 2",
            "type": "multi",
            "config": MultiBacktestConfig(max_concurrent=20, sl_pct=0.03, tp_pct=0.08,
                                          edge_amplifier=2.0, long_only=True),
        },
        # ── floor variants — buy-hold base + pattern overlay
        {
            "name": "v3.0 floor 50% (buy-hold half + overlay)",
            "type": "floor",
            "config": FloorBacktestConfig(floor_pct=0.50, up_pct=1.00, overlay_horizon_bars=30),
        },
        {
            "name": "v3.1 floor 70%",
            "type": "floor",
            "config": FloorBacktestConfig(floor_pct=0.70, up_pct=1.00, overlay_horizon_bars=30),
        },
        {
            "name": "v3.2 floor 90% (almost full buy-hold)",
            "type": "floor",
            "config": FloorBacktestConfig(floor_pct=0.90, up_pct=1.00, overlay_horizon_bars=30),
        },
        {
            "name": "v3.3 floor 70% wide overlay (300m)",
            "type": "floor",
            "config": FloorBacktestConfig(floor_pct=0.70, up_pct=1.00, overlay_horizon_bars=300),
        },
        {
            "name": "v3.4 floor 30% (mostly pattern-driven)",
            "type": "floor",
            "config": FloorBacktestConfig(floor_pct=0.30, up_pct=1.00, overlay_horizon_bars=60),
        },
        # ── defensive timing — buy-hold + drawdown avoidance
        {
            "name": "v4.0 defensive (1d window, exit≥3 bear)",
            "type": "defensive",
            "config": DefensiveConfig(pressure_window_min=60*24, exit_threshold=3,
                                       enter_threshold=0, use_negative_edge_cells=True),
        },
        {
            "name": "v4.1 defensive (3d window, exit≥10 bear)",
            "type": "defensive",
            "config": DefensiveConfig(pressure_window_min=60*24*3, exit_threshold=10,
                                       enter_threshold=2, use_negative_edge_cells=True),
        },
        {
            "name": "v4.2 defensive (1w window, exit≥30 bear)",
            "type": "defensive",
            "config": DefensiveConfig(pressure_window_min=60*24*7, exit_threshold=30,
                                       enter_threshold=10, use_negative_edge_cells=True),
        },
        {
            "name": "v4.3 defensive 3d (no negative edge; pure bear)",
            "type": "defensive",
            "config": DefensiveConfig(pressure_window_min=60*24*3, exit_threshold=2,
                                       enter_threshold=0, use_negative_edge_cells=False),
        },
    ]

    results = []
    for v in variants:
        print(f"  Running {v['name']}...")
        if v["type"] == "event":
            bt = EventDrivenBacktester(fitness=fitness, initial_capital=args.initial_capital, config=v["config"])
            r = bt.run(symbol=args.symbol, ohlcv_1m=df_1m, ohlcv_by_tf=ohlcv_by_tf,
                       signals_df=signals, regime_by_tf=regime_by_tf)
        elif v["type"] == "multi":
            bt = MultiPositionEventBacktester(fitness=fitness, initial_capital=args.initial_capital, config=v["config"])
            r = bt.run(symbol=args.symbol, ohlcv_1m=df_1m, ohlcv_by_tf=ohlcv_by_tf,
                       signals_df=signals, regime_by_tf=regime_by_tf)
        elif v["type"] == "floor":
            bt = PositionFloorBacktester(fitness=fitness, initial_capital=args.initial_capital, config=v["config"])
            r = bt.run(symbol=args.symbol, ohlcv_1m=df_1m, ohlcv_by_tf=ohlcv_by_tf,
                       signals_df=signals, regime_by_tf=regime_by_tf)
        else:  # defensive
            bt = DefensiveTimingBacktester(fitness=fitness, initial_capital=args.initial_capital, config=v["config"])
            r = bt.run(symbol=args.symbol, ohlcv_1m=df_1m,
                       signals_df=signals, regime_by_tf=regime_by_tf)
        results.append({"name": v["name"], "result": r})

    # Print comparison table
    print()
    print(f"{'Variant':40s} {'Trades':>7s} {'Return%':>9s} {'Sharpe':>7s} {'MDD%':>6s} {'WinRate':>8s} {'PF':>5s} {'AvgHold(min)':>12s}")
    print("─" * 110)
    print(f"{'BUY & HOLD':40s} {'-':>7s} {bh*100:+9.2f} {'-':>7s} {'-':>6s} {'-':>8s} {'-':>5s} {'-':>12s}")
    print("─" * 110)
    for x in results:
        r = x["result"]
        print(f"{x['name']:40s} {r.n_trades:>7d} {r.total_return_pct*100:+9.2f} "
              f"{r.sharpe_ratio:>7.2f} {r.max_drawdown_pct*100:>6.2f} "
              f"{r.win_rate*100:>7.1f}% {r.profit_factor:>5.2f} {r.avg_holding_bars:>12.0f}")

    # Best variant
    best = max(results, key=lambda x: x["result"].total_return_pct)
    print()
    print(f"BEST by return: {best['name']} → {best['result'].total_return_pct*100:+.2f}%")
    print(f"BUY & HOLD = {bh*100:+.2f}%")
    print(f"Gap to buy-hold: {(best['result'].total_return_pct - bh)*100:+.2f} pts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
