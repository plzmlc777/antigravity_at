#!/usr/bin/env python3
"""Generic Pipeline runner — drives any (sources, composer, policy) combo.

Usage examples:
  # KR pattern + flow (the validated winning combo)
  python -m scripts.run_pipeline --symbol 005930 --pattern --kr-flow --static-split 0.5

  # Crypto pattern + microstructure
  python -m scripts.run_pipeline --symbol BTCUSDT --pattern --binance-micro --static-split 0.5

  # Walk-forward
  python -m scripts.run_pipeline --symbol 122630 --pattern --kr-flow --walk-forward --train-window 100 --retrain-step 10

The framework lets you swap any layer:
  --pattern / --no-pattern         (PatternSource)
  --market / --no-market           (MarketStateSource)
  --regime / --no-regime           (RegimeSource)
  --kr-flow / --no-kr-flow         (KRInvestorFlowSource)
  --binance-micro / --no-binance-micro
  --policy long_only|long_short
  Future: --composer linear|lgbm|neural ...
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.composer_framework import (  # noqa: E402
    GenericBacktester,
    LongOnlyThresholdPolicy,
    LongShortThresholdPolicy,
    Pipeline,
    PipelineConfig,
    SourceContext,
)
from app.composer_framework.composers import LGBMComposerAdapter  # noqa: E402
from app.composer_framework.sources import (  # noqa: E402
    BinanceMicrostructureSource,
    KRInvestorFlowSource,
    MarketStateSource,
    PatternSource,
    RegimeSource,
)
from app.db.session import SessionLocal  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("run_pipeline")

EVAL_TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def load_1m(symbol: str) -> pd.DataFrame:
    db = SessionLocal()
    try:
        sql = text("SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                   "WHERE symbol = :sym AND time_frame = '1m' ORDER BY timestamp")
        rows = db.execute(sql, {"sym": symbol}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def find_signals_path(symbol: str) -> Path | None:
    base = ROOT / "runs" / "pattern_scanner"
    for d in (365, 364, 363, 200, 540, 600, 800, 795):
        p = base / f"{symbol}__{d}d__signals.joblib"
        if p.exists():
            return p
    matches = list(base.glob(f"{symbol}__*d__signals.joblib"))
    return matches[0] if matches else None


def find_metrics_path(symbol: str) -> Path | None:
    p = ROOT / "runs" / "microstructure" / f"{symbol}_full_metrics.joblib"
    return p if p.exists() else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--eval-tf", default="1d", choices=list(EVAL_TF_MIN.keys()))
    p.add_argument("--forward", type=int, default=5)
    # source toggles (defaults reflect the validated winning combo for KR)
    p.add_argument("--pattern", dest="use_pattern", action="store_true", default=True)
    p.add_argument("--no-pattern", dest="use_pattern", action="store_false")
    p.add_argument("--market", dest="use_market", action="store_true", default=True)
    p.add_argument("--no-market", dest="use_market", action="store_false")
    p.add_argument("--regime", dest="use_regime", action="store_true", default=True)
    p.add_argument("--no-regime", dest="use_regime", action="store_false")
    p.add_argument("--kr-flow", dest="use_kr_flow", action="store_true", default=False)
    p.add_argument("--no-kr-flow", dest="use_kr_flow", action="store_false")
    p.add_argument("--binance-micro", dest="use_binance_micro", action="store_true", default=False)
    p.add_argument("--no-binance-micro", dest="use_binance_micro", action="store_false")
    # policy
    p.add_argument("--policy", choices=("long_only", "long_short"), default="long_only")
    p.add_argument("--threshold", type=float, default=0.005)
    p.add_argument("--sl", type=float, default=0.04)
    p.add_argument("--tp", type=float, default=0.10)
    # backtest mode
    p.add_argument("--static-split", type=float, default=None,
                   help="run static fit/test with given train fraction (e.g. 0.5)")
    p.add_argument("--walk-forward", action="store_true",
                   help="run walk-forward; requires --train-window and --retrain-step")
    p.add_argument("--train-window", type=int, default=100)
    p.add_argument("--retrain-step", type=int, default=10)
    # capital
    p.add_argument("--initial-capital", type=float, default=1_000_000)
    p.add_argument("--fee-rate", type=float, default=0.00015)
    args = p.parse_args()

    eval_min = EVAL_TF_MIN[args.eval_tf]

    # Load data
    print(f"Loading {args.symbol} 1m OHLCV...")
    df_1m = load_1m(args.symbol)
    df_eval = resample_ohlcv(df_1m, args.eval_tf)
    print(f"  1m bars: {len(df_1m):,}, {args.eval_tf} bars: {len(df_eval)}")

    # Build SourceContext
    ctx = SourceContext(
        symbol=args.symbol, eval_freq_minutes=eval_min,
        ohlcv_1m=df_1m, ohlcv_eval=df_eval,
    )

    # Assemble sources
    sources = []
    if args.use_market:
        sources.append(MarketStateSource())
    if args.use_regime:
        sources.append(RegimeSource(daily_preset=(args.eval_tf in ("4h", "1d"))))
    if args.use_pattern:
        sig_path = find_signals_path(args.symbol)
        if sig_path is None:
            print(f"  WARNING: no signals file for {args.symbol}, skipping PatternSource")
        else:
            print(f"  Pattern signals: {sig_path.name}")
            sources.append(PatternSource(joblib.load(sig_path)))
    if args.use_kr_flow:
        try:
            sources.append(KRInvestorFlowSource(symbol=args.symbol))
            print(f"  KR investor flow: enabled")
        except Exception as e:
            print(f"  WARNING: KR flow load failed for {args.symbol}: {e}")
    if args.use_binance_micro:
        m_path = find_metrics_path(args.symbol)
        if m_path is None:
            print(f"  WARNING: no Binance metrics for {args.symbol}")
        else:
            sources.append(BinanceMicrostructureSource(joblib.load(m_path)))
            print(f"  Binance microstructure: enabled")
    print(f"  sources: {[s.name for s in sources]}")

    # Composer + policy
    composer = LGBMComposerAdapter()
    if args.policy == "long_short":
        policy = LongShortThresholdPolicy(
            entry_threshold=args.threshold, sl_pct=args.sl, tp_pct=args.tp,
            max_hold_bars=args.forward,
        )
    else:
        policy = LongOnlyThresholdPolicy(
            entry_threshold=args.threshold, sl_pct=args.sl, tp_pct=args.tp,
            max_hold_bars=args.forward,
        )

    pipeline = Pipeline(
        sources=sources, composer=composer, policy=policy,
        config=PipelineConfig(eval_freq_minutes=eval_min, forward_bars=args.forward),
    )
    print(f"  pipeline: {pipeline}")

    backtester = GenericBacktester(
        initial_capital=args.initial_capital, fee_rate=args.fee_rate,
    )

    if args.walk_forward:
        print(f"\nRunning WALK-FORWARD (train_window={args.train_window}, retrain_step={args.retrain_step})...")
        kpi = backtester.run_walk_forward(
            pipeline=pipeline, ctx=ctx,
            train_window_bars=args.train_window, retrain_step_bars=args.retrain_step,
        )
    else:
        split = args.static_split if args.static_split is not None else 0.5
        print(f"\nRunning STATIC fit/test (train_frac={split})...")
        kpi = backtester.run_static(pipeline=pipeline, ctx=ctx, train_frac=split)

    print()
    print(kpi.summary())

    # Save result
    out_dir = ROOT / "runs" / "composer_framework"
    out_dir.mkdir(parents=True, exist_ok=True)
    src_tag = "+".join(s.name for s in sources)
    mode = "walk" if args.walk_forward else "static"
    out_path = out_dir / f"{args.symbol}__{args.eval_tf}__{src_tag}__{mode}.joblib"
    joblib.dump(kpi, out_path, compress=3)
    print(f"\nSaved → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
