#!/usr/bin/env python3
"""KR ML test: pattern features + investor flow features (ka10059).

This is Option 1 from the user's plan. Investor flow data is the KR analog of
crypto microstructure — telling us who's buying/selling. We have 1 year of
daily flow data for 005930 and 122630.

Compares:
  - Pattern only
  - Flow only
  - Combined
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
from app.microstructure.kr_investor_flow import attach_flow_to_features, fetch_investor_flow  # noqa: E402
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
    for d in (365, 364, 363, 540, 800):
        p = ROOT / "runs" / "pattern_scanner" / f"{sym}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    for p in (ROOT / "runs" / "pattern_scanner").glob(f"{sym}__*d__signals.joblib"):
        return joblib.load(p)
    raise FileNotFoundError(sym)


def diagnose(name: str, preds: np.ndarray, actuals: np.ndarray):
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p = preds[mask]; a = actuals[mask]
    if len(p) < 2:
        print(f"  {name}: too few samples (n={len(p)})"); return
    corr = float(np.corrcoef(p, a)[0, 1])
    sign_acc = float((np.sign(p) == np.sign(a)).mean())
    q75, q25 = np.quantile(p, [0.75, 0.25])
    top = float(a[p >= q75].mean()) if (p >= q75).any() else 0.0
    bot = float(a[p <= q25].mean()) if (p <= q25).any() else 0.0
    print(f"  {name}: n={len(p):3d} | corr={corr:+.4f} | sign_acc={sign_acc*100:.1f}% | "
          f"top25={top*100:+.3f}% | bot25={bot*100:+.3f}% | spread={(top-bot)*100:+.3f}%")


def walk_forward(feat: pd.DataFrame, train_window: int, retrain_step: int):
    cfg = LGBMComposerConfig()
    preds = np.full(len(feat), np.nan)
    actuals = feat["target_fwd_ret"].values
    last_train = -10**9
    comp = None
    for i in range(train_window, len(feat)):
        if i - last_train >= retrain_step or comp is None:
            train = feat.iloc[max(0, i - train_window):i].dropna(subset=["target_fwd_ret"])
            if len(train) < 30:
                continue
            comp = LGBMComposer(cfg)
            comp.fit(train, target_col="target_fwd_ret")
            last_train = i
        if comp is None:
            continue
        preds[i] = comp.predict(feat.iloc[[i]])[0]
    return preds, actuals


def trade_sim(bars, preds, *, threshold, sl, tp, hold, long_only=True, fee=0.00015):
    cash = 1_000_000
    qty = 0; side = "flat"; ent_p = 0; ent_i = -1
    trades = []
    eq = []
    for i in range(len(bars)):
        o = float(bars.iloc[i]["open"]); c = float(bars.iloc[i]["close"])
        pred = preds[i] if i < len(preds) else np.nan
        if side != "flat":
            held = i - ent_i; ex_r = None; ex_p = o
            if side == "long":
                if c <= ent_p * (1 - sl): ex_r = "sl"; ex_p = ent_p * (1 - sl)
                elif c >= ent_p * (1 + tp): ex_r = "tp"; ex_p = ent_p * (1 + tp)
            else:
                if c >= ent_p * (1 + sl): ex_r = "sl"; ex_p = ent_p * (1 + sl)
                elif c <= ent_p * (1 - tp): ex_r = "tp"; ex_p = ent_p * (1 - tp)
            if ex_r is None and held >= hold: ex_r = "time"; ex_p = o
            if ex_r:
                if side == "long":
                    proc = qty * ex_p * (1 - fee); cost = qty * ent_p * (1 + fee)
                    ret = (proc - cost) / cost; cash += proc
                else:
                    proc = qty * (ent_p - ex_p); cost = qty * ent_p
                    ret = proc / cost; cash += cost + proc
                trades.append({"ret": ret, "side": side})
                qty = 0; side = "flat"
        if side == "flat" and not np.isnan(pred):
            if pred > threshold:
                qty = (cash * 0.95) / (o * (1 + fee)); cash -= qty * o * (1 + fee)
                side = "long"; ent_p = o; ent_i = i
            elif (not long_only) and pred < -threshold:
                qty = (cash * 0.95) / o; cash -= qty * o
                side = "short"; ent_p = o; ent_i = i
        mtm = cash + qty * c if side == "long" else (cash + qty * (ent_p - c) + qty * ent_p if side == "short" else cash)
        eq.append(mtm)
    if side != "flat":
        last = float(bars.iloc[-1]["close"])
        if side == "long":
            proc = qty * last * (1 - fee); cost = qty * ent_p * (1 + fee)
            cash += proc; trades.append({"ret": (proc - cost) / cost, "side": side})
        else:
            proc = qty * (ent_p - last); cost = qty * ent_p
            cash += cost + proc; trades.append({"ret": proc / cost, "side": side})
    rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
    eq = np.array(eq)
    peaks = np.maximum.accumulate(eq) if len(eq) else np.array([])
    dd = (peaks - eq) / peaks if len(eq) else np.array([])
    return {"trades": len(trades), "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float((rets > 0).mean()) if len(rets) else 0.0,
            "mdd": float(dd.max()) if len(dd) else 0.0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="005930,122630")
    p.add_argument("--eval-tf", default="1d")
    p.add_argument("--forward", type=int, default=5)
    p.add_argument("--train-window", type=int, default=120,
                   help="120 bars = 6 months on daily")
    p.add_argument("--retrain-step", type=int, default=20)
    p.add_argument("--threshold", type=float, default=0.005)
    p.add_argument("--sl", type=float, default=0.04)
    p.add_argument("--tp", type=float, default=0.10)
    p.add_argument("--long-only", action="store_true", default=True)
    args = p.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]
    print(f"Symbols: {syms}, eval_tf={args.eval_tf}, fwd={args.forward}, train_win={args.train_window}")
    print()

    eval_min = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}[args.eval_tf]

    for sym in syms:
        print(f"=== {sym} ===")
        df_1m = load_1m(sym)
        df_eval = resample_ohlcv(df_1m, args.eval_tf)
        signals = load_signals(sym)
        cls = RegimeClassifier.for_daily() if args.eval_tf in ("4h", "1d") else RegimeClassifier.for_intraday()
        regime_eval = cls.classify(df_eval)
        flow_df = fetch_investor_flow(sym)

        print(f"  1m bars: {len(df_1m):,}, eval: {len(df_eval)}, signals: {len(signals):,}, flow rows: {len(flow_df)}")
        if len(flow_df) == 0:
            print("  no flow data — skip")
            continue

        # Pattern features
        feat_pat = build_feature_matrix(
            ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
            eval_freq_minutes=eval_min, forward_bars=args.forward,
        )
        # Flow only (use empty signals)
        feat_flow_only = build_feature_matrix(
            ohlcv_eval=df_eval, signals_df=pd.DataFrame(), regime_eval=regime_eval,
            eval_freq_minutes=eval_min, forward_bars=args.forward,
        )
        feat_flow_only = attach_flow_to_features(feat_flow_only, flow_df)
        feat_combined = attach_flow_to_features(feat_pat, flow_df)

        print(f"  feat dims: pat={feat_pat.shape[1]-1}, flow_only={feat_flow_only.shape[1]-1}, combined={feat_combined.shape[1]-1}")

        p_pat, _ = walk_forward(feat_pat, args.train_window, args.retrain_step)
        p_flow, _ = walk_forward(feat_flow_only, args.train_window, args.retrain_step)
        p_com, actuals = walk_forward(feat_combined, args.train_window, args.retrain_step)

        print("\n  Prediction quality:")
        diagnose("Pattern only ", p_pat, actuals)
        diagnose("Flow only    ", p_flow, actuals)
        diagnose("Combined     ", p_com, actuals)

        bh = (df_eval.iloc[-1]["close"] - df_eval.iloc[0]["open"]) / df_eval.iloc[0]["open"]
        print(f"\n  Buy & Hold: {bh*100:+.2f}%")
        for label, preds in [("Pattern", p_pat), ("Flow", p_flow), ("Combined", p_com)]:
            kpi = trade_sim(df_eval, preds,
                            threshold=args.threshold, sl=args.sl, tp=args.tp,
                            hold=args.forward, long_only=args.long_only)
            print(f"  {label:9s}: trades={kpi['trades']:3d} ret={kpi['ret']*100:+8.2f}% "
                  f"wr={kpi['wr']*100:5.1f}% mdd={kpi['mdd']*100:5.1f}%")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
