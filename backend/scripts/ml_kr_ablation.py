#!/usr/bin/env python3
"""Ablation/substitution study on the validated alpha pipeline.

Variants tested per symbol (same IS/OOS 50/50 split, forward=5):
  - baseline   : Pattern + Flow + Market + Regime, LGBM     (current production)
  - no_flow    : Pattern         + Market + Regime, LGBM    (A2: kr_flow ablation)
  - xgb        : Pattern + Flow + Market + Regime, XGBoost  (B1: composer substitution)
  - no_pattern :           Flow + Market + Regime, LGBM    (A1: pattern ablation)

Output: per-symbol grid for diagnose() + OOS Backtest, structured for direct
comparison with the baseline ml_kr_oos.py results.
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
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
warnings.filterwarnings("ignore", category=UserWarning)


class XGBComposerAdapter:
    """XGBoost regressor with same fit/predict signature as LGBMComposer."""
    def __init__(self, **kwargs):
        import xgboost as xgb
        self._xgb = xgb
        self._params = {
            "n_estimators": 300, "learning_rate": 0.03, "max_depth": 5,
            "subsample": 0.9, "colsample_bytree": 0.9,
            "reg_alpha": 0.1, "reg_lambda": 0.1, "random_state": 42,
            "verbosity": 0,
            **kwargs,
        }
        self.model = None
        self._feature_names: list[str] | None = None

    def fit(self, features_df: pd.DataFrame, target_col: str = "target_fwd_ret") -> None:
        df = features_df.copy()
        df = df.dropna(subset=[target_col])
        feat_cols = [c for c in df.columns if c != target_col]
        df[feat_cols] = df[feat_cols].fillna(0.0)
        X, y = df[feat_cols].values, df[target_col].values
        self.model = self._xgb.XGBRegressor(**self._params)
        self.model.fit(X, y)
        self._feature_names = feat_cols

    def predict(self, features_df: pd.DataFrame) -> np.ndarray:
        df = features_df.copy()
        for c in self._feature_names:
            if c not in df.columns:
                df[c] = 0.0
        df = df[self._feature_names].fillna(0.0)
        return self.model.predict(df.values)


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
    for d in (365, 364, 363, 200, 540, 800):
        p = ROOT / "runs" / "pattern_scanner" / f"{sym}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    for p in (ROOT / "runs" / "pattern_scanner").glob(f"{sym}__*d__signals.joblib"):
        return joblib.load(p)
    raise FileNotFoundError(sym)


def diagnose(name, preds, actuals):
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p = preds[mask]
    a = actuals[mask]
    if len(p) < 5:
        return {"n": len(p), "corr": np.nan, "sign": np.nan, "p": 1.0, "spread": np.nan}
    corr = float(np.corrcoef(p, a)[0, 1])
    sign = float((np.sign(p) == np.sign(a)).mean())
    from scipy import stats as scistats
    binom_p = scistats.binomtest(int((np.sign(p) == np.sign(a)).sum()), len(p), 0.5).pvalue
    q75, q25 = np.quantile(p, [0.75, 0.25])
    top = float(a[p >= q75].mean()) if (p >= q75).any() else 0.0
    bot = float(a[p <= q25].mean()) if (p <= q25).any() else 0.0
    return {"n": len(p), "corr": corr, "sign": sign * 100, "p": binom_p,
            "top25": top * 100, "bot25": bot * 100, "spread": (top - bot) * 100}


def trade_sim(bars, preds, *, threshold, sl, tp, hold, fee=0.00015):
    cash = 1_000_000
    qty = 0
    ent_p = 0
    ent_i = -1
    side = "flat"
    trades = []
    eq = []
    for i in range(len(bars)):
        o = float(bars.iloc[i]["open"])
        c = float(bars.iloc[i]["close"])
        pred = preds[i] if i < len(preds) else np.nan
        if side == "long":
            held = i - ent_i
            ex_r = None
            ex_p = o
            if c <= ent_p * (1 - sl):
                ex_r = "sl"
                ex_p = ent_p * (1 - sl)
            elif c >= ent_p * (1 + tp):
                ex_r = "tp"
                ex_p = ent_p * (1 + tp)
            elif held >= hold:
                ex_r = "time"
                ex_p = o
            if ex_r:
                proc = qty * ex_p * (1 - fee)
                cost = qty * ent_p * (1 + fee)
                ret = (proc - cost) / cost
                cash += proc
                trades.append({"ret": ret})
                qty = 0
                side = "flat"
        if side == "flat" and not np.isnan(pred) and pred > threshold:
            qty = (cash * 0.95) / (o * (1 + fee))
            cash -= qty * o * (1 + fee)
            side = "long"
            ent_p = o
            ent_i = i
        eq.append(cash + qty * c)
    if side == "long":
        last = float(bars.iloc[-1]["close"])
        proc = qty * last * (1 - fee)
        cost = qty * ent_p * (1 + fee)
        cash += proc
        trades.append({"ret": (proc - cost) / cost})
    rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
    eq_arr = np.array(eq)
    peaks = np.maximum.accumulate(eq_arr) if len(eq_arr) else np.array([])
    dd = (peaks - eq_arr) / peaks if len(eq_arr) else np.array([])
    return {"trades": len(trades), "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float((rets > 0).mean()) if len(rets) else 0.0,
            "mdd": float(dd.max()) if len(dd) else 0.0}


VARIANTS = ("baseline", "no_flow", "xgb", "no_pattern")


def build_features(sym: str, df_eval, signals, regime_eval, flow_df, *,
                   variant: str, forward: int) -> pd.DataFrame:
    """Construct the feature matrix for the given ablation variant."""
    if variant == "no_pattern":
        sigs = pd.DataFrame()  # zero-out pattern features
    else:
        sigs = signals

    feat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=sigs, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=forward,
    )

    if variant in ("baseline", "xgb"):
        feat = attach_flow_to_features(feat, flow_df)
    elif variant == "no_pattern":
        feat = attach_flow_to_features(feat, flow_df)  # keep flow even when pattern dropped
    # variant == "no_flow" → skip flow attach
    return feat


def make_composer(variant: str):
    if variant == "xgb":
        return XGBComposerAdapter()
    return LGBMComposer(LGBMComposerConfig())


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="122630,007210,055550,000660,196170")
    p.add_argument("--forward", type=int, default=5)
    p.add_argument("--variants", default=",".join(VARIANTS),
                   help=f"comma list of variants from: {VARIANTS}")
    args = p.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]
    variants = [v.strip() for v in args.variants.split(",") if v.strip() in VARIANTS]

    print(f"Ablation/substitution study — strict IS/OOS 50/50, forward={args.forward}")
    print(f"Variants: {variants}")
    print()

    rows = []
    for sym in syms:
        df_1m = load_1m(sym)
        df_eval = resample_ohlcv(df_1m, "1d")
        signals = load_signals(sym)
        cls = RegimeClassifier.for_daily()
        regime_eval = cls.classify(df_eval)
        flow_df = fetch_investor_flow(sym)

        print(f"=== {sym} ===")
        for variant in variants:
            feat = build_features(sym, df_eval, signals, regime_eval, flow_df,
                                  variant=variant, forward=args.forward)
            n = len(feat)
            split = n // 2
            train = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
            test = feat.iloc[split:]
            if len(train) < 30 or len(test) < 30:
                print(f"  {variant:11s}: train/test too small (train={len(train)}, test={len(test)})")
                continue

            comp = make_composer(variant)
            comp.fit(train, target_col="target_fwd_ret")
            preds = comp.predict(test)
            actuals = test["target_fwd_ret"].values
            d = diagnose(variant, preds, actuals)

            bars_test = df_eval.loc[test.index]
            kpi = trade_sim(bars_test, preds, threshold=0.005, sl=0.04, tp=0.10, hold=args.forward)
            bh_test = (bars_test.iloc[-1]["close"] - bars_test.iloc[0]["open"]) / bars_test.iloc[0]["open"]
            alpha = (kpi["ret"] - bh_test) * 100

            sig_marker = "***" if d["p"] < 0.001 else ("**" if d["p"] < 0.01 else ("*" if d["p"] < 0.05 else " "))
            print(f"  {variant:11s}: feat={feat.shape[1]-1:3d} | sign={d['sign']:.1f}%{sig_marker:3s} p={d['p']:.4f} | "
                  f"trades={kpi['trades']:3d} ret={kpi['ret']*100:+7.2f}% wr={kpi['wr']*100:.1f}% mdd={kpi['mdd']*100:.1f}% | "
                  f"BH={bh_test*100:+.2f}% alpha={alpha:+7.2f}pts")

            rows.append({
                "symbol": sym, "variant": variant, "feat_dim": feat.shape[1] - 1,
                "sign": d["sign"], "p": d["p"], "trades": kpi["trades"],
                "ret_pct": kpi["ret"] * 100, "wr_pct": kpi["wr"] * 100, "mdd_pct": kpi["mdd"] * 100,
                "bh_pct": bh_test * 100, "alpha_pts": alpha,
            })
        print()

    # Summary grid
    print("=" * 100)
    print("SUMMARY GRID (alpha_pts vs baseline)")
    print("=" * 100)
    df = pd.DataFrame(rows)
    if len(df) > 0:
        pivot_alpha = df.pivot(index="symbol", columns="variant", values="alpha_pts").round(2)
        pivot_sign = df.pivot(index="symbol", columns="variant", values="sign").round(1)
        print("\nAlpha (pts) by variant:")
        print(pivot_alpha.to_string())
        print("\nSign accuracy (%) by variant:")
        print(pivot_sign.to_string())
        if "baseline" in pivot_alpha.columns:
            print("\nDelta alpha vs baseline (pts):")
            for v in [c for c in pivot_alpha.columns if c != "baseline"]:
                delta = (pivot_alpha[v] - pivot_alpha["baseline"]).round(2)
                print(f"  {v:11s}: {delta.to_dict()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
