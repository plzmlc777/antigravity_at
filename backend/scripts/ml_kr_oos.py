#!/usr/bin/env python3
"""Rigorous IS/OOS validation: train on first half, test on second half (no walk-forward).

If the walk-forward results are real (not lookahead artifact), strict OOS
should also show positive correlation. If OOS collapses, walk-forward was
leaking somehow.
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
    for d in (365, 364, 363, 200, 540, 800):
        p = ROOT / "runs" / "pattern_scanner" / f"{sym}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    for p in (ROOT / "runs" / "pattern_scanner").glob(f"{sym}__*d__signals.joblib"):
        return joblib.load(p)
    raise FileNotFoundError(sym)


def diagnose(name, preds, actuals):
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p = preds[mask]; a = actuals[mask]
    if len(p) < 5:
        print(f"  {name}: too few (n={len(p)})"); return
    corr = float(np.corrcoef(p, a)[0, 1])
    sign = float((np.sign(p) == np.sign(a)).mean())
    # statistical test for sign accuracy vs 50%
    from scipy import stats as scistats
    binom_p = scistats.binomtest(int((np.sign(p) == np.sign(a)).sum()), len(p), 0.5).pvalue if len(p) > 0 else 1.0
    q75, q25 = np.quantile(p, [0.75, 0.25])
    top = float(a[p >= q75].mean()) if (p >= q75).any() else 0.0
    bot = float(a[p <= q25].mean()) if (p <= q25).any() else 0.0
    sig = "***" if binom_p < 0.001 else ("**" if binom_p < 0.01 else ("*" if binom_p < 0.05 else " "))
    print(f"  {name}: n={len(p):3d} | corr={corr:+.4f} | sign={sign*100:.1f}%{sig} | "
          f"top25={top*100:+.3f}% bot25={bot*100:+.3f}% spread={(top-bot)*100:+.3f}% | binomial p={binom_p:.4f}")


def trade_sim(bars, preds, *, threshold, sl, tp, hold, fee=0.00015):
    cash = 1_000_000
    qty = 0; ent_p = 0; ent_i = -1; side = "flat"
    trades = []
    eq = []
    for i in range(len(bars)):
        o = float(bars.iloc[i]["open"]); c = float(bars.iloc[i]["close"])
        pred = preds[i] if i < len(preds) else np.nan
        if side == "long":
            held = i - ent_i; ex_r = None; ex_p = o
            if c <= ent_p * (1 - sl): ex_r = "sl"; ex_p = ent_p * (1 - sl)
            elif c >= ent_p * (1 + tp): ex_r = "tp"; ex_p = ent_p * (1 + tp)
            elif held >= hold: ex_r = "time"; ex_p = o
            if ex_r:
                proc = qty * ex_p * (1 - fee); cost = qty * ent_p * (1 + fee)
                ret = (proc - cost) / cost; cash += proc
                trades.append({"ret": ret})
                qty = 0; side = "flat"
        if side == "flat" and not np.isnan(pred) and pred > threshold:
            qty = (cash * 0.95) / (o * (1 + fee)); cash -= qty * o * (1 + fee)
            side = "long"; ent_p = o; ent_i = i
        eq.append(cash + qty * c)
    if side == "long":
        last = float(bars.iloc[-1]["close"])
        proc = qty * last * (1 - fee); cost = qty * ent_p * (1 + fee)
        cash += proc; trades.append({"ret": (proc - cost) / cost})
    rets = np.array([t["ret"] for t in trades]) if trades else np.array([])
    eq = np.array(eq); peaks = np.maximum.accumulate(eq) if len(eq) else np.array([])
    dd = (peaks - eq) / peaks if len(eq) else np.array([])
    return {"trades": len(trades), "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float((rets > 0).mean()) if len(rets) else 0.0,
            "mdd": float(dd.max()) if len(dd) else 0.0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="005930,122630")
    p.add_argument("--forward", type=int, default=5)
    args = p.parse_args()

    syms = [s.strip() for s in args.symbols.split(",")]
    print(f"Strict IS/OOS — train first 50%, test second 50% (no walk-forward)")
    print()

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
        feat_combined = attach_flow_to_features(feat_pat, flow_df)

        # Strict 50/50 split
        n = len(feat_combined)
        split = n // 2
        train = feat_combined.iloc[:split].dropna(subset=["target_fwd_ret"])
        test = feat_combined.iloc[split:]

        print(f"=== {sym} (train: {train.index[0].date()} → {train.index[-1].date()}, "
              f"test: {test.index[0].date()} → {test.index[-1].date()}) ===")
        print(f"  train n={len(train)}, test n={len(test)}, feat dim={feat_combined.shape[1]-1}")

        # Train pattern only
        feat_pat_train = feat_pat.iloc[:split].dropna(subset=["target_fwd_ret"])
        feat_pat_test = feat_pat.iloc[split:]

        for name, ft, fte in [("Pattern only", feat_pat_train, feat_pat_test),
                              ("Combined    ", train, test)]:
            cfg = LGBMComposerConfig()
            comp = LGBMComposer(cfg)
            comp.fit(ft, target_col="target_fwd_ret")
            preds = comp.predict(fte)
            actuals = fte["target_fwd_ret"].values
            diagnose(name, preds, actuals)

        # Backtest the combined model OOS
        cfg = LGBMComposerConfig()
        comp = LGBMComposer(cfg)
        comp.fit(train, target_col="target_fwd_ret")
        preds = comp.predict(test)
        bars_test = df_eval.loc[test.index]
        kpi = trade_sim(bars_test, preds, threshold=0.005, sl=0.04, tp=0.10, hold=args.forward)
        bh_test = (bars_test.iloc[-1]["close"] - bars_test.iloc[0]["open"]) / bars_test.iloc[0]["open"]
        print(f"  OOS Backtest (Combined): trades={kpi['trades']:3d} | ret={kpi['ret']*100:+8.2f}% | "
              f"wr={kpi['wr']*100:.1f}% | mdd={kpi['mdd']*100:.1f}% | BH(OOS)={bh_test*100:+.2f}%")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
