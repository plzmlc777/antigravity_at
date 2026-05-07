#!/usr/bin/env python3
"""Train + walk-forward evaluate the ML composer on multiple symbols.

Usage:
    python -m scripts.ml_pattern_train --symbols BTCUSDT,ETHUSDT,SOLUSDT --eval-tf 1d --forward 5
    python -m scripts.ml_pattern_train --symbols 005930,001210 --eval-tf 1d --forward 5
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

from app.db.session import SessionLocal  # noqa: E402
from app.pattern_ml import (  # noqa: E402
    LGBMComposerConfig,
    MLBacktestConfig,
    MLPatternBacktester,
)
from app.pattern_scanner import PatternScanner  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("ml_pattern_train")


TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 60 * 24}


def load_1m(symbol: str) -> pd.DataFrame:
    db = SessionLocal()
    try:
        sql = text("""SELECT timestamp, open, high, low, close, volume FROM ohlcv
                     WHERE symbol = :sym AND time_frame = '1m'
                     ORDER BY timestamp ASC""")
        rows = db.execute(sql, {"sym": symbol}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def get_signals(symbol: str, df_1m: pd.DataFrame) -> pd.DataFrame:
    days = (df_1m.index[-1] - df_1m.index[0]).days
    sig_path = ROOT / "runs" / "pattern_scanner" / f"{symbol}__{days}d__signals.joblib"
    if sig_path.exists():
        return joblib.load(sig_path)
    print(f"  [scanning {symbol} ({days}d)...]")
    tensor = PatternScanner().scan(df_1m, symbol=symbol)
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(tensor, sig_path, compress=3)
    return tensor


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True)
    p.add_argument("--eval-tf", default="1d", choices=list(TF_MIN.keys()))
    p.add_argument("--forward", type=int, default=5, help="forward-return horizon (eval bars)")
    p.add_argument("--train-window", type=int, default=200)
    p.add_argument("--retrain-step", type=int, default=20)
    p.add_argument("--entry-threshold", type=float, default=0.005)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--tp-pct", type=float, default=0.15)
    p.add_argument("--long-only", action="store_true")
    p.add_argument("--initial-capital", type=float, default=10_000.0)
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {symbols}, eval_tf={args.eval_tf}, fwd={args.forward}, train_win={args.train_window}, retrain_step={args.retrain_step}")
    print(f"long_only={args.long_only}, entry={args.entry_threshold}, sl/tp={args.sl_pct}/{args.tp_pct}")
    print()

    print(f"{'Symbol':10s} {'Bars':>7s} {'BH%':>9s} {'ML Ret%':>10s} {'Sharpe':>7s} {'MDD%':>6s} {'Trades':>7s} {'WR%':>5s}")
    print("-" * 75)

    rows = []
    for sym in symbols:
        df_1m = load_1m(sym)
        if len(df_1m) == 0:
            print(f"{sym}: no data")
            continue

        df_eval = resample_ohlcv(df_1m, args.eval_tf)
        if len(df_eval) < args.train_window + 30:
            print(f"{sym}: insufficient eval bars ({len(df_eval)}, need >={args.train_window + 30})")
            continue

        signals = get_signals(sym, df_1m)

        # regime at eval frequency
        cls = RegimeClassifier.for_daily() if args.eval_tf in ("4h", "1d") else RegimeClassifier.for_intraday()
        regime_eval = cls.classify(df_eval)

        cfg = MLBacktestConfig(
            eval_freq_minutes=TF_MIN[args.eval_tf],
            forward_bars=args.forward,
            train_window_bars=args.train_window,
            retrain_step_bars=args.retrain_step,
            entry_threshold=args.entry_threshold,
            sl_pct=args.sl_pct,
            tp_pct=args.tp_pct,
            long_only=args.long_only,
            holding_bars=args.forward,
        )
        bt = MLPatternBacktester(initial_capital=args.initial_capital, config=cfg)
        kpi = bt.run(symbol=sym, ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval)

        rows.append(kpi)
        print(f"{sym:10s} {len(df_eval):>7d} {kpi['buy_hold_pct']*100:>+8.2f}% "
              f"{kpi['total_return_pct']*100:>+9.2f}% {kpi['sharpe_per_trade_annualized']:>7.2f} "
              f"{kpi['max_drawdown_pct']*100:>5.1f}% {kpi['n_trades']:>7d} "
              f"{kpi['win_rate']*100:>4.0f}%")

    print("-" * 75)
    if rows:
        avg_ml = np.mean([r["total_return_pct"] for r in rows]) * 100
        avg_bh = np.mean([r["buy_hold_pct"] for r in rows]) * 100
        n_beat = sum(r["total_return_pct"] > r["buy_hold_pct"] for r in rows)
        print(f"AVG: BH {avg_bh:+.2f}% / ML {avg_ml:+.2f}% / Alpha {avg_ml - avg_bh:+.2f}pts / Beat-BH {n_beat}/{len(rows)}")

        # Save
        out_dir = ROOT / "runs" / "pattern_ml"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{'_'.join(symbols)}__{args.eval_tf}__{args.forward}fwd.joblib"
        joblib.dump(rows, out_path, compress=3)
        print(f"Saved → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
