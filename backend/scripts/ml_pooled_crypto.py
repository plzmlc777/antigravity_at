#!/usr/bin/env python3
"""Pool BTC+ETH+SOL training data and run walk-forward predictions per symbol.

Hypothesis: per-symbol models overfit (corr -0.1 on ETH, +0.06 on BTC). Pooling
3 symbols × 540-795 days gives more diverse training data → less overfitting,
hopefully generalizable cross-asset features (microstructure should be more
symmetric across crypto majors than price patterns).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.microstructure import attach_to_feature_matrix  # noqa: E402
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def load_1m(sym: str) -> pd.DataFrame:
    db = SessionLocal()
    try:
        sql = text("SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                   "WHERE symbol = :sym AND time_frame = '1m' ORDER BY timestamp")
        rows = db.execute(sql, {"sym": sym}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def load_signals(sym: str) -> pd.DataFrame:
    for d in (600, 800, 540, 795, 539):
        p = ROOT / "runs" / "pattern_scanner" / f"{sym}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    raise FileNotFoundError(sym)


def build_features_for_symbol(sym: str, eval_tf: str, forward: int) -> pd.DataFrame:
    df_1m = load_1m(sym)
    df_eval = resample_ohlcv(df_1m, eval_tf)
    signals = load_signals(sym)
    cls = RegimeClassifier.for_daily() if eval_tf in ("4h", "1d") else RegimeClassifier.for_intraday()
    regime_eval = cls.classify(df_eval)
    eval_min = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}[eval_tf]
    feat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=eval_min, forward_bars=forward,
    )
    metrics_path = ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib"
    if metrics_path.exists():
        metrics = joblib.load(metrics_path)
        feat = attach_to_feature_matrix(feat, metrics, eval_min)
    feat["__symbol__"] = sym
    return feat, df_eval


def diagnose(name: str, preds: np.ndarray, actuals: np.ndarray):
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p = preds[mask]; a = actuals[mask]
    if len(p) < 2:
        print(f"  {name}: too few"); return
    corr = float(np.corrcoef(p, a)[0, 1])
    sign_acc = float((np.sign(p) == np.sign(a)).mean())
    q75, q25 = np.quantile(p, [0.75, 0.25])
    top = float(a[p >= q75].mean()) if (p >= q75).any() else 0.0
    bot = float(a[p <= q25].mean()) if (p <= q25).any() else 0.0
    print(f"  {name}: n={len(p):3d} | corr={corr:+.4f} | sign_acc={sign_acc*100:.1f}% | "
          f"top25={top*100:+.3f}% | bot25={bot*100:+.3f}% | spread={(top-bot)*100:+.3f}%")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    p.add_argument("--eval-tf", default="1d")
    p.add_argument("--forward", type=int, default=5)
    p.add_argument("--train-window", type=int, default=400, help="larger window for pooled training")
    p.add_argument("--retrain-step", type=int, default=30)
    args = p.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]
    print(f"Pooled training across {syms}, eval_tf={args.eval_tf}, fwd={args.forward}")

    feats = {}
    bars = {}
    for s in syms:
        print(f"  Building features for {s}...")
        f, b = build_features_for_symbol(s, args.eval_tf, args.forward)
        feats[s] = f
        bars[s] = b
        print(f"    rows: {len(f)}, cols: {f.shape[1]}")

    # Common columns intersect (drop __symbol__ for fitting)
    common_cols = set(feats[syms[0]].columns)
    for s in syms[1:]:
        common_cols &= set(feats[s].columns)
    common_cols = sorted(common_cols - {"__symbol__"})
    print(f"  common feature cols: {len(common_cols) - 1}")  # minus target

    # Stack all symbols' rows into one big DF for pooled training
    pooled = pd.concat([f[common_cols + ["__symbol__"]] for f in [feats[s] for s in syms]], axis=0).sort_index()

    # Per-symbol walk-forward predictions
    cfg = LGBMComposerConfig()
    per_symbol_results = {}

    for sym in syms:
        f_sym = feats[sym][common_cols].copy()
        f_sym = f_sym.sort_index()
        actuals = f_sym["target_fwd_ret"].values
        preds = np.full(len(f_sym), np.nan)
        last_train = -10**9
        comp = None
        for i in range(args.train_window, len(f_sym)):
            ts = f_sym.index[i]
            if i - last_train >= args.retrain_step or comp is None:
                # train on POOLED data with timestamp <= ts (across all 3 symbols)
                train_pool = pooled[pooled.index < ts]
                # use last `train_window` bars per symbol from the pool
                train_parts = []
                for s in syms:
                    sub = train_pool[train_pool["__symbol__"] == s].tail(args.train_window)
                    train_parts.append(sub)
                train_df = pd.concat(train_parts).dropna(subset=["target_fwd_ret"])
                # drop __symbol__ for fitting
                train_df = train_df.drop(columns=["__symbol__"])
                if len(train_df) < 100:
                    continue
                comp = LGBMComposer(cfg)
                comp.fit(train_df, target_col="target_fwd_ret")
                last_train = i
            if comp is None:
                continue
            row = f_sym.iloc[[i]].drop(columns=[c for c in ["__symbol__"] if c in f_sym.columns], errors="ignore")
            preds[i] = comp.predict(row)[0]
        per_symbol_results[sym] = (preds, actuals, f_sym)

    print("\n=== Pooled-training walk-forward predictions per symbol ===")
    for sym in syms:
        preds, actuals, f_sym = per_symbol_results[sym]
        diagnose(sym, preds, actuals)

    # Backtest each (long-only first, simple)
    def bt(name, bars_df, preds, threshold=0.005, sl=0.05, tp=0.15, fee=0.0005, hold=5, long_only=True):
        cash = 10000; qty = 0; side = "flat"; entry_price = 0; entry_idx = -1
        trades = []
        for i in range(len(bars_df)):
            o = float(bars_df.iloc[i]["open"]); c = float(bars_df.iloc[i]["close"])
            pred = preds[i] if i < len(preds) else np.nan
            if side != "flat":
                held = i - entry_idx; ex_r = None; ex_p = o
                if side == "long":
                    if c <= entry_price * (1 - sl): ex_r = "sl"; ex_p = entry_price * (1 - sl)
                    elif c >= entry_price * (1 + tp): ex_r = "tp"; ex_p = entry_price * (1 + tp)
                else:
                    if c >= entry_price * (1 + sl): ex_r = "sl"; ex_p = entry_price * (1 + sl)
                    elif c <= entry_price * (1 - tp): ex_r = "tp"; ex_p = entry_price * (1 - tp)
                if ex_r is None and held >= hold: ex_r = "time"; ex_p = o
                if ex_r:
                    if side == "long":
                        proc = qty * ex_p * (1 - fee); cost = qty * entry_price * (1 + fee)
                        ret = (proc - cost) / cost; cash += proc
                    else:
                        proc = qty * (entry_price - ex_p); cost = qty * entry_price
                        ret = proc / cost; cash += cost + proc
                    trades.append({"ret": ret, "side": side})
                    qty = 0; side = "flat"
            if side == "flat" and not np.isnan(pred):
                if pred > threshold:
                    qty = (cash * 0.95) / (o * (1 + fee)); cash -= qty * o * (1 + fee)
                    side = "long"; entry_price = o; entry_idx = i
                elif (not long_only) and pred < -threshold:
                    qty = (cash * 0.95) / o; cash -= qty * o
                    side = "short"; entry_price = o; entry_idx = i
        if side != "flat":
            last = float(bars_df.iloc[-1]["close"])
            if side == "long":
                proc = qty * last * (1 - fee); cost = qty * entry_price * (1 + fee)
                cash += proc; trades.append({"ret": (proc - cost) / cost, "side": side})
            else:
                proc = qty * (entry_price - last); cost = qty * entry_price
                cash += cost + proc; trades.append({"ret": proc / cost, "side": side})
        rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
        return {"trades": len(trades), "ret": (cash - 10000) / 10000,
                "wr": float((rets > 0).mean()) if len(rets) else 0.0}

    print("\n=== Backtest (long-only) ===")
    for sym in syms:
        preds, actuals, _ = per_symbol_results[sym]
        kpi_lo = bt(sym, bars[sym], preds, long_only=True)
        kpi_ls = bt(sym, bars[sym], preds, long_only=False)
        bh = (bars[sym].iloc[-1]["close"] - bars[sym].iloc[0]["open"]) / bars[sym].iloc[0]["open"]
        print(f"  {sym}: BH={bh*100:+7.2f}% | LongOnly={kpi_lo['ret']*100:+8.2f}% (n={kpi_lo['trades']:3d}, wr={kpi_lo['wr']*100:.0f}%) | "
              f"LongShort={kpi_ls['ret']*100:+8.2f}% (n={kpi_ls['trades']:3d}, wr={kpi_ls['wr']*100:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
