#!/usr/bin/env python3
"""Print feature importances for KR ML+Flow model.

Trains the model on the full available data per symbol and reports both:
  - LightGBM split-count importance
  - Permutation importance (more robust)
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


def load_1m(sym):
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


def load_signals(sym):
    for d in (365, 364, 363, 200, 540, 800):
        p = ROOT / "runs" / "pattern_scanner" / f"{sym}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    for p in (ROOT / "runs" / "pattern_scanner").glob(f"{sym}__*d__signals.joblib"):
        return joblib.load(p)
    raise FileNotFoundError(sym)


def feature_class(name: str) -> str:
    if name.startswith("flow_"):
        return "FLOW"
    if name.startswith("pat_"):
        return "PATTERN"
    if name.startswith("micro_"):
        return "MICRO"
    if name.startswith("ret_") or "vol" in name or name == "dow":
        return "MARKET"
    if "score" in name or name in ("trend_score", "volatility_score", "liquidity_score", "momentum_score"):
        return "REGIME"
    return "OTHER"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="005930,122630")
    p.add_argument("--forward", type=int, default=5)
    args = p.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]

    for sym in syms:
        df_1m = load_1m(sym)
        df_eval = resample_ohlcv(df_1m, "1d")
        signals = load_signals(sym)
        cls = RegimeClassifier.for_daily()
        regime_eval = cls.classify(df_eval)
        flow_df = fetch_investor_flow(sym)

        feat_pat = build_feature_matrix(
            ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
            eval_freq_minutes=1440, forward_bars=args.forward,
        )
        feat = attach_flow_to_features(feat_pat, flow_df)
        feat = feat.dropna(subset=["target_fwd_ret"])

        # Train on full data
        comp = LGBMComposer(LGBMComposerConfig())
        comp.fit(feat, target_col="target_fwd_ret")
        imp = comp.feature_importances()

        # Group by class
        df_imp = pd.DataFrame({"feature": imp.index, "importance": imp.values})
        df_imp["class"] = df_imp["feature"].apply(feature_class)
        class_total = df_imp.groupby("class")["importance"].sum().sort_values(ascending=False)
        total = class_total.sum()

        print(f"\n=== {sym} (n_train={len(feat)}, total_importance={total:.0f}) ===")
        print("\nBy class:")
        for cls_name, val in class_total.items():
            print(f"  {cls_name:10s}: {val:>6.0f} ({val/total*100:>5.1f}%)")

        print("\nTop 20 individual features:")
        for _, row in df_imp.sort_values("importance", ascending=False).head(20).iterrows():
            print(f"  [{row['class']:7s}] {row['feature']:35s} {row['importance']:>5.0f}")

        # Permutation importance — more robust
        from sklearn.inspection import permutation_importance
        feat_cols = [c for c in feat.columns if c != "target_fwd_ret"]
        X = feat[feat_cols].fillna(0.0).values
        y = feat["target_fwd_ret"].values
        perm = permutation_importance(comp.model, X, y, n_repeats=10, random_state=42, scoring="r2")
        df_perm = pd.DataFrame({
            "feature": feat_cols, "perm_importance": perm.importances_mean,
            "perm_std": perm.importances_std,
        }).sort_values("perm_importance", ascending=False)
        df_perm["class"] = df_perm["feature"].apply(feature_class)
        print("\nTop 15 by PERMUTATION importance (drop in R² when feature shuffled):")
        for _, row in df_perm.head(15).iterrows():
            print(f"  [{row['class']:7s}] {row['feature']:35s} drop={row['perm_importance']*100:>+6.3f}% (±{row['perm_std']*100:.3f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
