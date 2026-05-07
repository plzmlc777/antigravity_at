#!/usr/bin/env python3
"""Diagnostic report for a Signal Tensor produced by scan_patterns.py.

Reads a saved tensor (.joblib), prints:
  - Total signals + duration coverage
  - Per-pattern signals/day rate (proxy for false-positive load)
  - Per-(pattern, timeframe) signal counts
  - Per-direction breakdown
  - Top noisy detectors (>= NOISE_THRESHOLD signals/day on any TF)
  - Confidence distribution (mean/median/percentiles per pattern)

Usage:
    python -m scripts.diagnose_scan path/to/signals.joblib
    python -m scripts.diagnose_scan --symbol 005930 --days 365  # auto-find
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# heuristic: a healthy chart pattern fires <0.5/day, candle <2/day, indicator <2/day
HEALTHY_RATE_PER_DAY = {
    "chart": 0.5,
    "candle": 2.0,
    "indicator": 2.0,
    "volume": 1.0,
}


def find_tensor_path(symbol: str, days: int, root: Path) -> Path:
    p = root / f"{symbol}__{days}d__signals.joblib"
    if not p.exists():
        raise FileNotFoundError(f"No tensor found at {p}")
    return p


def category_of(pattern_name: str) -> str:
    from app.patterns import PatternRegistry
    PatternRegistry.discover()
    try:
        cls = PatternRegistry.get(pattern_name)
        return cls.category
    except KeyError:
        return "unknown"


def diagnose(tensor: pd.DataFrame, total_days: float) -> None:
    print(f"\n=== Signal Tensor Diagnosis ===")
    print(f"Total signals: {len(tensor)}")
    print(f"Coverage: {total_days:.1f} days")
    if len(tensor) == 0:
        print("Empty tensor — nothing to diagnose.")
        return

    print(f"\nUnique patterns: {tensor['pattern_name'].nunique()}")
    print(f"Unique timeframes: {sorted(tensor['timeframe'].unique())}")
    print(f"Date range: {tensor['timestamp'].min()} → {tensor['timestamp'].max()}")

    # Per-pattern rate per day
    by_pat = tensor.groupby("pattern_name").size() / total_days
    by_pat = by_pat.sort_values(ascending=False)
    print(f"\n--- Signals per day per pattern (top 20) ---")
    for name, rate in by_pat.head(20).items():
        cat = category_of(name)
        threshold = HEALTHY_RATE_PER_DAY.get(cat, 1.0)
        flag = " 🚨 NOISY" if rate > threshold * 5 else (" ⚠️  high" if rate > threshold else "")
        print(f"  {name:32s} ({cat:9s}): {rate:7.2f}/day{flag}")

    # Per-(pattern, TF)
    print(f"\n--- (pattern, TF) signal count, top 20 ---")
    pivot = tensor.groupby(["pattern_name", "timeframe"]).size().unstack(fill_value=0)
    print(pivot.head(20).to_string())

    # Direction breakdown
    print(f"\n--- Direction breakdown ---")
    print(tensor.groupby(["timeframe", "direction"]).size().unstack(fill_value=0).to_string())

    # Confidence distribution
    print(f"\n--- Confidence distribution per pattern (top 10 by signal count) ---")
    top_pats = tensor["pattern_name"].value_counts().head(10).index.tolist()
    for pat in top_pats:
        sub = tensor[tensor["pattern_name"] == pat]["confidence"]
        n = len(sub)
        print(f"  {pat:32s}  n={n:5d}  mean={sub.mean():.3f}  "
              f"median={sub.median():.3f}  p10={sub.quantile(0.1):.3f}  "
              f"p90={sub.quantile(0.9):.3f}")

    # Quality summary
    print(f"\n--- Quality flags ---")
    flagged = []
    for name, rate in by_pat.items():
        cat = category_of(name)
        threshold = HEALTHY_RATE_PER_DAY.get(cat, 1.0)
        if rate > threshold * 5:
            flagged.append((name, cat, rate, "NOISY"))
        elif rate > threshold:
            flagged.append((name, cat, rate, "HIGH"))
    if flagged:
        print(f"  {len(flagged)} pattern(s) above healthy rate:")
        for name, cat, rate, lvl in flagged:
            print(f"    [{lvl:5s}] {name:32s} ({cat:9s}): {rate:.2f}/day")
    else:
        print("  All patterns within healthy ranges.")

    # Detectors that emitted ZERO signals over the entire period
    from app.patterns import PatternRegistry
    PatternRegistry.discover()
    seen = set(tensor["pattern_name"].unique())
    all_names = set(d.name for d in PatternRegistry.all())
    silent = sorted(all_names - seen)
    if silent:
        print(f"\n--- Silent detectors (0 signals in entire window) ---")
        for name in silent:
            print(f"  {name} ({category_of(name)})")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path", nargs="?", default=None, help="Path to .joblib tensor")
    p.add_argument("--symbol", default=None)
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--root", default=str(ROOT / "runs" / "pattern_scanner"))
    args = p.parse_args()

    if args.path:
        tensor_path = Path(args.path)
    elif args.symbol and args.days:
        tensor_path = find_tensor_path(args.symbol, args.days, Path(args.root))
    else:
        p.error("Either provide a path or both --symbol and --days")
        return 2

    print(f"Loading: {tensor_path}")
    tensor = joblib.load(tensor_path)
    if not isinstance(tensor, pd.DataFrame):
        print(f"Expected DataFrame, got {type(tensor)}")
        return 1

    if "timestamp" in tensor.columns and len(tensor):
        tensor["timestamp"] = pd.to_datetime(tensor["timestamp"])
        total_days = (tensor["timestamp"].max() - tensor["timestamp"].min()).total_seconds() / 86400.0
        if total_days <= 0:
            total_days = 1.0
    else:
        total_days = 1.0

    diagnose(tensor, total_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
