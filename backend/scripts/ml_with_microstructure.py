#!/usr/bin/env python3
"""Re-run ML pattern backtest WITH microstructure features added.

Compares 3 configs end-to-end on the same data:
  A) Baseline = pattern features only
  B) Microstructure-only features
  C) Combined = pattern + microstructure

Hypothesis: if microstructure carries unique info, C should beat A and B.
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
from app.microstructure import attach_to_feature_matrix  # noqa: E402
from app.pattern_ml import LGBMComposerConfig, MLBacktestConfig, MLPatternBacktester  # noqa: E402
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")


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


def diagnose_predictions(name: str, preds: np.ndarray, actuals: np.ndarray):
    """Print prediction-vs-actual diagnostics (the same we did for ML baseline)."""
    if len(preds) < 2:
        print(f"  {name}: too few samples"); return
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p = preds[mask]; a = actuals[mask]
    if len(p) < 2:
        print(f"  {name}: too few non-NaN"); return
    corr = float(np.corrcoef(p, a)[0, 1])
    sign_acc = float((np.sign(p) == np.sign(a)).mean())
    q75, q25 = np.quantile(p, [0.75, 0.25])
    top_act = float(a[p >= q75].mean()) if (p >= q75).any() else 0.0
    bot_act = float(a[p <= q25].mean()) if (p <= q25).any() else 0.0
    print(f"  {name}: n={len(p)} | corr={corr:+.4f} | sign_acc={sign_acc*100:.1f}% | "
          f"top25 actual={top_act*100:+.3f}% | bot25 actual={bot_act*100:+.3f}%")


def walk_forward_predict(feat: pd.DataFrame, train_window: int, retrain_step: int,
                         lgbm_cfg: LGBMComposerConfig, label: str = "") -> tuple[np.ndarray, np.ndarray]:
    """Walk-forward predictions; returns (predictions, actuals) arrays."""
    preds = np.full(len(feat), np.nan)
    actuals = feat["target_fwd_ret"].values
    last_train = -10**9
    composer = None
    for i in range(train_window, len(feat)):
        if i - last_train >= retrain_step or composer is None:
            train = feat.iloc[max(0, i - train_window):i].dropna(subset=["target_fwd_ret"])
            if len(train) < 50:
                continue
            composer = LGBMComposer(lgbm_cfg)
            composer.fit(train, target_col="target_fwd_ret")
            last_train = i
        if composer is None:
            continue
        row = feat.iloc[[i]]
        preds[i] = composer.predict(row)[0]
    return preds, actuals


def trade_simulate(bars: pd.DataFrame, predictions: np.ndarray, *,
                   entry_threshold: float, sl_pct: float, tp_pct: float,
                   long_only: bool, holding_bars: int, fee_rate: float,
                   initial_capital: float = 10_000.0) -> dict:
    """Simple trade simulator with predictions array (eval-freq aligned)."""
    cash = initial_capital
    qty = 0.0
    side = "flat"
    entry_price = 0.0
    entry_idx = -1
    trades = []
    eq_curve = []
    for i in range(len(bars)):
        o = float(bars.iloc[i]["open"])
        c = float(bars.iloc[i]["close"])
        pred = predictions[i] if i < len(predictions) else np.nan

        # exit
        if side != "flat":
            held = i - entry_idx
            ex_reason = None; ex_price = o
            if side == "long":
                if c <= entry_price * (1 - sl_pct): ex_reason = "sl"; ex_price = entry_price * (1 - sl_pct)
                elif c >= entry_price * (1 + tp_pct): ex_reason = "tp"; ex_price = entry_price * (1 + tp_pct)
            else:
                if c >= entry_price * (1 + sl_pct): ex_reason = "sl"; ex_price = entry_price * (1 + sl_pct)
                elif c <= entry_price * (1 - tp_pct): ex_reason = "tp"; ex_price = entry_price * (1 - tp_pct)
            if ex_reason is None and held >= holding_bars:
                ex_reason = "time"; ex_price = o
            if ex_reason:
                if side == "long":
                    proc = qty * ex_price * (1 - fee_rate); cost = qty * entry_price * (1 + fee_rate)
                    ret = (proc - cost) / cost; cash += proc
                else:
                    proc = qty * (entry_price - ex_price); cost = qty * entry_price
                    ret = proc / cost; cash += cost + proc
                trades.append({"side": side, "ret": ret, "reason": ex_reason})
                qty = 0.0; side = "flat"

        # entry
        if side == "flat" and not np.isnan(pred):
            if pred > entry_threshold:
                qty = (cash * 0.95) / (o * (1 + fee_rate)); cash -= qty * o * (1 + fee_rate)
                side = "long"; entry_price = o; entry_idx = i
            elif (not long_only) and pred < -entry_threshold:
                qty = (cash * 0.95) / o; cash -= qty * o
                side = "short"; entry_price = o; entry_idx = i

        if side == "long": mtm = cash + qty * c
        elif side == "short": mtm = cash + qty * (entry_price - c) + qty * entry_price
        else: mtm = cash
        eq_curve.append(mtm)

    if side != "flat":
        last = float(bars.iloc[-1]["close"])
        if side == "long":
            proc = qty * last * (1 - fee_rate); cost = qty * entry_price * (1 + fee_rate)
            cash += proc
            trades.append({"side": side, "ret": (proc - cost) / cost, "reason": "eod"})
        else:
            proc = qty * (entry_price - last); cost = qty * entry_price
            cash += cost + proc
            trades.append({"side": side, "ret": proc / cost, "reason": "eod"})

    rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
    eq = np.array(eq_curve)
    peaks = np.maximum.accumulate(eq) if len(eq) else np.array([])
    dd = (peaks - eq) / peaks if len(eq) else np.array([])
    return {
        "n_trades": len(trades),
        "win_rate": float((rets > 0).mean()) if len(rets) else 0.0,
        "total_ret": (cash - initial_capital) / initial_capital,
        "mdd": float(dd.max()) if len(dd) else 0.0,
        "exits": pd.Series([t["reason"] for t in trades]).value_counts().to_dict() if trades else {},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--metrics-path", required=True, help="path to BTCUSDT_full_metrics.joblib")
    p.add_argument("--eval-tf", default="1d")
    p.add_argument("--forward", type=int, default=5)
    p.add_argument("--train-window", type=int, default=200)
    p.add_argument("--retrain-step", type=int, default=20)
    p.add_argument("--entry-threshold", type=float, default=0.005)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--tp-pct", type=float, default=0.15)
    p.add_argument("--long-only", action="store_true")
    args = p.parse_args()

    print(f"Loading {args.symbol} 1m + signals + microstructure...")
    df_1m = load_1m(args.symbol)
    df_eval = resample_ohlcv(df_1m, args.eval_tf)

    # signals — try common days suffixes, then fallback to glob
    days = (df_1m.index[-1] - df_1m.index[0]).days
    candidates = [
        ROOT / "runs" / "pattern_scanner" / f"{args.symbol}__{d}d__signals.joblib"
        for d in (600, 800, days)
    ]
    sig_path = next((p for p in candidates if p.exists()), None)
    if sig_path is None:
        for p in (ROOT / "runs" / "pattern_scanner").glob(f"{args.symbol}__*d__signals.joblib"):
            sig_path = p; break
    if sig_path is None:
        raise FileNotFoundError(f"No signals file for {args.symbol}")
    signals = joblib.load(sig_path)
    print(f"  1m bars: {len(df_1m):,}, eval bars: {len(df_eval)}, signals: {len(signals):,}")

    # microstructure
    metrics_5m = joblib.load(args.metrics_path)
    print(f"  microstructure rows: {len(metrics_5m):,}, range: {metrics_5m.index[0]} → {metrics_5m.index[-1]}")

    # regime
    cls = RegimeClassifier.for_daily() if args.eval_tf in ("4h", "1d") else RegimeClassifier.for_intraday()
    regime_eval = cls.classify(df_eval)

    eval_min = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}[args.eval_tf]

    # Build base features
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=eval_min, forward_bars=args.forward,
    )

    # Microstructure features attached
    feat_micro_only = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=pd.DataFrame(),  # empty signals
        regime_eval=regime_eval, eval_freq_minutes=eval_min, forward_bars=args.forward,
    )
    feat_micro_only = attach_to_feature_matrix(feat_micro_only, metrics_5m, eval_min)

    feat_combined = attach_to_feature_matrix(feat_pat, metrics_5m, eval_min)

    print(f"  feature dims: pattern_only={feat_pat.shape[1]-1}, "
          f"micro_only={feat_micro_only.shape[1]-1}, combined={feat_combined.shape[1]-1}")

    # walk-forward predictions for each variant
    cfg_lgbm = LGBMComposerConfig()
    print("\nRunning walk-forward predictions...")
    p_pat, _ = walk_forward_predict(feat_pat, args.train_window, args.retrain_step, cfg_lgbm, "pattern")
    p_mic, _ = walk_forward_predict(feat_micro_only, args.train_window, args.retrain_step, cfg_lgbm, "micro")
    p_com, actuals = walk_forward_predict(feat_combined, args.train_window, args.retrain_step, cfg_lgbm, "combined")

    print("\n=== Prediction quality (corr w/ forward return) ===")
    diagnose_predictions("Pattern only ", p_pat, actuals)
    diagnose_predictions("Micro only   ", p_mic, actuals)
    diagnose_predictions("Combined     ", p_com, actuals)

    print("\n=== Backtest comparison ===")
    bh = (df_eval.iloc[-1]["close"] - df_eval.iloc[0]["open"]) / df_eval.iloc[0]["open"]
    print(f"Buy & Hold: {bh*100:+.2f}%")
    for label, preds in [("Pattern", p_pat), ("Micro", p_mic), ("Combined", p_com)]:
        kpi = trade_simulate(
            df_eval, preds,
            entry_threshold=args.entry_threshold, sl_pct=args.sl_pct, tp_pct=args.tp_pct,
            long_only=args.long_only, holding_bars=args.forward, fee_rate=0.0005,
        )
        print(f"  {label:9s}: trades={kpi['n_trades']:4d} ret={kpi['total_ret']*100:+8.2f}% "
              f"wr={kpi['win_rate']*100:5.1f}% mdd={kpi['mdd']*100:5.1f}% exits={kpi['exits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
