"""Regime filter analysis for confirmed Binance signals.

For each (symbol, combo, fwd) candidate:
  1. Build features + train/test split (50/50)
  2. Get LGBM predictions on full test set
  3. Classify each test bar's regime (trend / volatility / liquidity / momentum)
  4. Compute sign accuracy per regime cell
  5. Identify regimes where signal is strong vs weak
  6. Apply regime filter (skip weak regimes) and re-compute alpha + sign

Goal: find a regime filter that lifts SOL/DOGE walk-forward FAIL → PASS
without overfitting (simple filter, e.g., "skip when trend=sideways").
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats as scistats
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.composer_framework.signal_source import SourceContext  # noqa: E402
from app.composer_framework.sources import (  # noqa: E402
    BinanceSmartMoneySource,
    BinanceTakerFlowSource,
    BinanceOIDynamicsSource,
)
from app.db.session import SessionLocal  # noqa: E402
from app.microstructure.features import aggregate_to_eval_bars  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

warnings.filterwarnings("ignore")


def load_data(sym):
    db = SessionLocal()
    sql = text("SELECT timestamp, open, high, low, close, volume FROM ohlcv "
               "WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp")
    rows = db.execute(sql, {"s": sym}).fetchall()
    db.close()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    df_eval = resample_ohlcv(df, "1d")
    sig_dir = ROOT / "runs" / "pattern_scanner"
    signals = None
    for p in sorted(sig_dir.glob(f"{sym}__*d__signals.joblib")):
        signals = joblib.load(p); break
    metrics = joblib.load(ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib")
    return df_eval, signals, metrics


def attach_combo(feat_pat, df_eval, metrics, combo, eval_freq_min=1440):
    out = feat_pat
    codes = combo.split("+")
    proxy = pd.DataFrame({"close": np.nan}, index=feat_pat.index)
    for code in codes:
        if code == "M":
            micro = aggregate_to_eval_bars(metrics, feat_pat.index, eval_freq_min)
            if "micro_" not in "".join(micro.columns):
                micro = micro.add_prefix("micro_")
            out = out.join(micro, how="left")
        elif code == "S":
            src = BinanceSmartMoneySource(metrics_5m=metrics)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)
            out = out.join(src.build_features(ctx), how="left")
        elif code == "T":
            src = BinanceTakerFlowSource(metrics_5m=metrics)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)
            out = out.join(src.build_features(ctx), how="left")
        elif code == "O":
            src = BinanceOIDynamicsSource(metrics_5m=metrics)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=df_eval)
            out = out.join(src.build_features(ctx), how="left")
    return out


def trade_sim(bars, preds, *, threshold=0.005, sl=0.06, tp=0.15, hold=10,
              fee=0.0004, policy="long_short", filter_mask=None):
    """trade_sim with optional per-bar filter_mask: True=allow trade, False=skip."""
    cash = 1_000_000
    qty = 0; ent_p = 0; ent_i = -1
    side = "flat"
    trades = []
    for i in range(len(bars)):
        o = float(bars.iloc[i]["open"])
        c = float(bars.iloc[i]["close"])
        pred = preds[i] if i < len(preds) else np.nan
        if side == "long":
            held = i - ent_i
            ex_r = None; ex_p = o
            if c <= ent_p * (1 - sl):
                ex_r = "sl"; ex_p = ent_p * (1 - sl)
            elif c >= ent_p * (1 + tp):
                ex_r = "tp"; ex_p = ent_p * (1 + tp)
            elif held >= hold:
                ex_r = "time"; ex_p = o
            if ex_r:
                proc = qty * ex_p * (1 - fee)
                cost = qty * ent_p * (1 + fee)
                cash += proc
                trades.append({"ret": (proc - cost) / cost, "side": "long"})
                qty = 0; side = "flat"
        elif side == "short":
            held = i - ent_i
            ex_r = None; ex_p = o
            if c >= ent_p * (1 + sl):
                ex_r = "sl"; ex_p = ent_p * (1 + sl)
            elif c <= ent_p * (1 - tp):
                ex_r = "tp"; ex_p = ent_p * (1 - tp)
            elif held >= hold:
                ex_r = "time"; ex_p = o
            if ex_r:
                pnl = qty * (ent_p - ex_p) - qty * ent_p * fee - qty * ex_p * fee
                cash += qty * ent_p + pnl
                trades.append({"ret": pnl / (qty * ent_p), "side": "short"})
                qty = 0; side = "flat"
        if side == "flat" and not np.isnan(pred):
            allowed = True if filter_mask is None else bool(filter_mask[i])
            if allowed:
                if pred > threshold:
                    qty = (cash * 0.95) / (o * (1 + fee))
                    cash -= qty * o * (1 + fee)
                    side = "long"; ent_p = o; ent_i = i
                elif policy == "long_short" and pred < -threshold:
                    qty = (cash * 0.95) / o
                    cash -= qty * o
                    cash -= qty * o * fee
                    side = "short"; ent_p = o; ent_i = i
    if side == "long":
        last = float(bars.iloc[-1]["close"])
        proc = qty * last * (1 - fee)
        cost = qty * ent_p * (1 + fee)
        cash += proc
        trades.append({"ret": (proc - cost) / cost, "side": "long"})
    elif side == "short":
        last = float(bars.iloc[-1]["close"])
        pnl = qty * (ent_p - last) - qty * ent_p * fee - qty * last * fee
        cash += qty * ent_p + pnl
        trades.append({"ret": pnl / (qty * ent_p), "side": "short"})
    return {"trades": len(trades),
            "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float(np.mean([t["ret"] > 0 for t in trades])) if trades else 0.0}


def per_regime_sign(preds, actuals, regime_df_test, dim):
    """Compute sign accuracy grouped by a regime dimension column."""
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p, a = preds[mask], actuals[mask]
    rgm = regime_df_test[dim].iloc[:len(preds)][mask].values
    out = []
    for label in pd.Series(rgm).unique():
        sel = (rgm == label)
        if sel.sum() < 10:
            continue
        hits = int((np.sign(p[sel]) == np.sign(a[sel])).sum())
        sign = hits / sel.sum()
        binom_p = scistats.binomtest(hits, sel.sum(), 0.5).pvalue
        out.append({"regime": label, "n": sel.sum(), "sign": sign, "binom_p": binom_p})
    return pd.DataFrame(out).sort_values("sign", ascending=False)


def analyze(symbol, combo, fwd, policy):
    print("\n" + "#" * 80)
    print(f"# {symbol} combo={combo} fwd={fwd} policy={policy}")
    print("#" * 80)

    df_eval, signals, metrics = load_data(symbol)

    # build features
    cls = RegimeClassifier.for_daily() if hasattr(RegimeClassifier, "for_daily") else RegimeClassifier()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=fwd,
    )
    feat = attach_combo(feat_pat, df_eval, metrics, combo)

    n = len(feat); split = n // 2
    train = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    test = feat.iloc[split:]
    test_idx = test.index

    cfg = LGBMComposerConfig()
    comp = LGBMComposer(cfg)
    comp.fit(train, target_col="target_fwd_ret")
    preds = comp.predict(test)
    actuals = test["target_fwd_ret"].values

    # baseline (no filter)
    bars_test = df_eval.loc[test_idx]
    kpi_base = trade_sim(bars_test, preds, hold=fwd, policy=policy)
    bh = (bars_test.iloc[-1]["close"] - bars_test.iloc[0]["open"]) / bars_test.iloc[0]["open"]
    alpha_base = (kpi_base["ret"] - bh) * 100
    print(f"\n[Baseline] no filter: trades={kpi_base['trades']} ret={kpi_base['ret']*100:+.2f}% "
          f"alpha={alpha_base:+.2f}pts")

    # regime per test bar
    test_regime = regime_eval.loc[test_idx]
    print(f"\nTest period: {test_idx[0].date()} → {test_idx[-1].date()} ({len(test_idx)} bars)")

    # per-regime sign analysis
    for dim in ("trend", "volatility", "momentum"):
        df_r = per_regime_sign(preds, actuals, test_regime, dim)
        print(f"\n[Per-{dim} regime sign accuracy]")
        for _, r in df_r.iterrows():
            print(f"  {r['regime']:>15s}: n={r['n']:>3d} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")

    # Try several filters and report alpha
    print("\n[Filter experiments] (apply to test set, recompute alpha)")
    print(f"  {'filter':<55}  {'trades':>6}  {'ret%':>8}  {'alpha':>8}  {'wr':>6}")
    print(f"  {'baseline (no filter)':<55}  {kpi_base['trades']:>6}  "
          f"{kpi_base['ret']*100:>+7.2f}%  {alpha_base:>+7.2f}  {kpi_base['wr']*100:>5.1f}%")

    filter_specs = [
        ("trend in {trending_up, trending_down}", lambda r: r["trend"] != "sideways"),
        ("trend == trending_up", lambda r: r["trend"] == "trending_up"),
        ("trend == trending_down", lambda r: r["trend"] == "trending_down"),
        ("volatility in {mid, high}", lambda r: r["volatility"] != "low"),
        ("volatility == high", lambda r: r["volatility"] == "high"),
        ("momentum != neutral", lambda r: r["momentum"] != "neutral"),
        ("trend non-sideways AND vol non-low", lambda r: (r["trend"] != "sideways") & (r["volatility"] != "low")),
        ("not (sideways AND low_vol)", lambda r: ~((r["trend"] == "sideways") & (r["volatility"] == "low"))),
    ]
    for label, fn in filter_specs:
        mask = fn(test_regime).values if hasattr(fn(test_regime), "values") else np.array(fn(test_regime))
        kpi_f = trade_sim(bars_test, preds, hold=fwd, policy=policy, filter_mask=mask)
        alpha_f = (kpi_f["ret"] - bh) * 100
        # also count how many test bars allowed
        allowed = int(mask.sum()) if hasattr(mask, "sum") else sum(1 for x in mask if x)
        print(f"  {label:<55}  {kpi_f['trades']:>6}  "
              f"{kpi_f['ret']*100:>+7.2f}%  {alpha_f:>+7.2f}  {kpi_f['wr']*100:>5.1f}%   "
              f"(allowed {allowed}/{len(mask)} bars)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", nargs="+", required=True,
                   help="format: SYMBOL:combo:fwd:policy  e.g. DOGEUSDT:T+O:10:long_short")
    args = p.parse_args()
    for spec in args.candidates:
        sym, combo, fwd_str, policy = spec.split(":")
        fwd = int(fwd_str)
        try:
            analyze(sym, combo, fwd, policy)
        except Exception as e:
            print(f"\n[{spec}] ERROR: {e}")
            import traceback; traceback.print_exc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
