"""Grid search v8 (4th batch 14 symbols) — 14 NEW Binance symbols, all source combos (S/T/O/E/P/V/M/C).

Target: discover decisive signals on the new 14-symbol universe.
Same gate (sign≥60% AND p<0.01 AND alpha>0).
Includes both KR-style (S/T/O/E/P) and Native (V/M/C) source paradigms.

Runs ~30min on 14 symbols × 16 combos × 2 fwd × 2 policy × 1 thr = 896 conditions.
"""
from __future__ import annotations

import itertools
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
    BinanceCrossETHSource,
    BinancePremiumSource,
    BinanceEventDetectorSource,
    BinanceMTFAlignmentSource,
    BinanceCascadeReversalSource,
)
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

warnings.filterwarnings("ignore")

# 14 NEW symbols
SYMBOLS = ["CRVUSDT", "SNXUSDT", "COMPUSDT", "1INCHUSDT", "DYDXUSDT", "MANAUSDT",
           "SANDUSDT", "AXSUSDT", "HBARUSDT", "PENDLEUSDT", "ENJUSDT", "CHZUSDT",
           "1000LUNCUSDT", "ZECUSDT"]

# Best combos from prior grid searches + new native combos
SOURCE_COMBOS = [
    # Single sources
    ("S",), ("T",), ("O",), ("V",), ("M",), ("C",),
    # KR pairs
    ("S", "T"), ("T", "O"), ("S", "P"),
    # Native combos
    ("V", "M"), ("V", "C"), ("V", "M", "C"),
    # Best confirmed combos from prior 14 (apply to new)
    ("S", "T", "O"),
    ("T", "O", "P"),         # DOGE T+O+P winner
    ("V", "M", "C", "T", "O"),
    ("S", "T", "O", "V"),
]
FORWARD_BARS = [5, 10]
POLICIES = ["long_only", "long_short"]
THRESHOLDS = [0.005]
SOL_ALPHA_BASELINE = 27.0


_ETH_CACHE = None
def get_eth_eval():
    global _ETH_CACHE
    if _ETH_CACHE is None:
        df_1m, df_eval, _, _ = load_data("ETHUSDT")
        _ETH_CACHE = df_eval
    return _ETH_CACHE


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
    df_1m = df.dropna()
    df_eval = resample_ohlcv(df_1m, "1d")
    sig_dir = ROOT / "runs" / "pattern_scanner"
    signals = None
    for p in sorted(sig_dir.glob(f"{sym}__*d__signals.joblib")):
        signals = joblib.load(p); break
    metrics_path = ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib"
    metrics = joblib.load(metrics_path) if metrics_path.exists() else None
    prem_path = ROOT / "runs" / "premium_index" / f"{sym}_premium.joblib"
    premium = joblib.load(prem_path) if prem_path.exists() else None
    return df_1m, df_eval, signals, metrics, premium


def attach_combo(feat_pat, df_1m, df_eval, metrics, premium, combo, eval_freq_min=1440):
    out = feat_pat
    proxy = pd.DataFrame({"close": np.nan}, index=feat_pat.index)
    ctx_full = SourceContext(symbol="", eval_freq_minutes=eval_freq_min,
                              ohlcv_1m=df_1m, ohlcv_eval=df_eval)
    for code in combo:
        if code == "S":
            src = BinanceSmartMoneySource(metrics_5m=metrics)
            out = out.join(src.build_features(SourceContext(
                symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)), how="left")
        elif code == "T":
            src = BinanceTakerFlowSource(metrics_5m=metrics)
            out = out.join(src.build_features(SourceContext(
                symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)), how="left")
        elif code == "O":
            src = BinanceOIDynamicsSource(metrics_5m=metrics)
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "E":
            src = BinanceCrossETHSource(eth_ohlcv_eval=get_eth_eval())
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "P":
            if premium is None or premium.empty: continue
            src = BinancePremiumSource(premium_df=premium)
            out = out.join(src.build_features(SourceContext(
                symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)), how="left")
        elif code == "V":
            src = BinanceEventDetectorSource(metrics_5m=metrics)
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "M":
            src = BinanceMTFAlignmentSource()
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "C":
            src = BinanceCascadeReversalSource(metrics_5m=metrics)
            out = out.join(src.build_features(ctx_full), how="left")
    return out


def trade_sim(bars, preds, *, threshold, sl=0.06, tp=0.15, hold=5, fee=0.0004,
              policy="long_only", vol_filter=None):
    cash = 1_000_000; qty = 0; ent_p = 0; ent_i = -1; side = "flat"; trades = []
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
                cash += proc; trades.append({"ret": (proc - cost) / cost})
                qty = 0; side = "flat"
        elif side == "short":
            held = i - ent_i; ex_r = None; ex_p = o
            if c >= ent_p * (1 + sl): ex_r = "sl"; ex_p = ent_p * (1 + sl)
            elif c <= ent_p * (1 - tp): ex_r = "tp"; ex_p = ent_p * (1 - tp)
            elif held >= hold: ex_r = "time"; ex_p = o
            if ex_r:
                pnl = qty * (ent_p - ex_p) - qty * ent_p * fee - qty * ex_p * fee
                cash += qty * ent_p + pnl
                trades.append({"ret": pnl / (qty * ent_p)})
                qty = 0; side = "flat"
        if side == "flat" and not np.isnan(pred):
            allowed = True if vol_filter is None else bool(vol_filter[i])
            if allowed:
                if pred > threshold:
                    qty = (cash * 0.95) / (o * (1 + fee))
                    cash -= qty * o * (1 + fee); side = "long"; ent_p = o; ent_i = i
                elif policy == "long_short" and pred < -threshold:
                    qty = (cash * 0.95) / o; cash -= qty * o
                    cash -= qty * o * fee; side = "short"; ent_p = o; ent_i = i
    if side == "long":
        last = float(bars.iloc[-1]["close"])
        proc = qty * last * (1 - fee); cost = qty * ent_p * (1 + fee)
        cash += proc; trades.append({"ret": (proc - cost) / cost})
    elif side == "short":
        last = float(bars.iloc[-1]["close"])
        pnl = qty * (ent_p - last) - qty * ent_p * fee - qty * last * fee
        cash += qty * ent_p + pnl; trades.append({"ret": pnl / (qty * ent_p)})
    return {"trades": len(trades), "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float(np.mean([t["ret"] > 0 for t in trades])) if trades else 0.0}


def evaluate(sym, df_1m, df_eval, signals, metrics, premium, combo, fwd, policy, threshold):
    cls = RegimeClassifier()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=fwd,
    )
    feat = attach_combo(feat_pat, df_1m, df_eval, metrics, premium, combo)
    n = len(feat); split = n // 2
    train = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    test = feat.iloc[split:]
    if len(train) < 30 or len(test) < 30: return None
    cfg = LGBMComposerConfig()
    comp = LGBMComposer(cfg)
    comp.fit(train, target_col="target_fwd_ret")
    preds = comp.predict(test)
    actuals = test["target_fwd_ret"].values
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p, a = preds[mask], actuals[mask]
    if len(p) < 10: return None
    hits = int((np.sign(p) == np.sign(a)).sum())
    sign = hits / len(p); binom_p = scistats.binomtest(hits, len(p), 0.5).pvalue

    bars = df_eval.loc[test.index]
    test_regime = regime_eval.loc[test.index]
    vol_mask = (test_regime["volatility"] != "low").values
    kpi = trade_sim(bars, preds, threshold=threshold, hold=fwd, policy=policy)
    kpi_vf = trade_sim(bars, preds, threshold=threshold, hold=fwd, policy=policy, vol_filter=vol_mask)
    bh = (bars.iloc[-1]["close"] - bars.iloc[0]["open"]) / bars.iloc[0]["open"]
    return {"sign": sign, "binom_p": binom_p,
            "alpha_pts": (kpi["ret"] - bh) * 100,
            "alpha_vf_pts": (kpi_vf["ret"] - bh) * 100,
            "trades": kpi["trades"], "trades_vf": kpi_vf["trades"]}


def main():
    n_total = len(SYMBOLS) * len(SOURCE_COMBOS) * len(FORWARD_BARS) * len(POLICIES) * len(THRESHOLDS)
    print(f"Grid v8 — 14 NEW Binance symbols. {n_total} conditions.")

    results = []
    for sym in SYMBOLS:
        try:
            df_1m, df_eval, signals, metrics, premium = load_data(sym)
            if signals is None or metrics is None:
                print(f"[{sym}] SKIP — missing signals/metrics"); continue
        except Exception as e:
            print(f"[{sym}] SKIP load: {e}"); continue
        n_done = 0
        for combo, fwd, policy, thr in itertools.product(SOURCE_COMBOS, FORWARD_BARS, POLICIES, THRESHOLDS):
            try:
                r = evaluate(sym, df_1m, df_eval, signals, metrics, premium, combo, fwd, policy, thr)
            except Exception:
                continue
            if r is None: continue
            results.append({"symbol": sym, "combo": "+".join(combo),
                            "fwd": fwd, "policy": policy, "threshold": thr, **r})
            n_done += 1
        print(f"[{sym}] {n_done} done", flush=True)

    if not results:
        print("No results"); return 1
    df = pd.DataFrame(results)
    df_sorted = df.sort_values("alpha_vf_pts", ascending=False).reset_index(drop=True)

    print("\n>>> Seed gate (sign≥60% AND p<0.01 AND alpha>0):")
    sg = df_sorted[(df_sorted["sign"] >= 0.60) & (df_sorted["binom_p"] < 0.01) & (df_sorted["alpha_pts"] > 0)]
    print(f"    {len(sg)} conditions")
    if len(sg) > 0:
        print(sg[["symbol", "combo", "fwd", "policy", "sign", "binom_p", "alpha_pts", "alpha_vf_pts", "trades"]].to_string(index=False))

    print("\n>>> Top 30 by alpha_vf_pts:")
    show = df_sorted.head(30).copy()
    show["sign"] = (show["sign"] * 100).round(1)
    show["binom_p"] = show["binom_p"].round(4)
    show["alpha_pts"] = show["alpha_pts"].round(2)
    show["alpha_vf_pts"] = show["alpha_vf_pts"].round(2)
    print(show[["symbol", "combo", "fwd", "policy", "sign", "binom_p", "alpha_pts", "alpha_vf_pts", "trades"]].to_string(index=False))

    print("\n>>> Best per symbol (sign≥0.55, by sign desc):")
    df_strong = df[df["sign"] >= 0.55].sort_values(["sign", "alpha_vf_pts"], ascending=[False, False])
    for sym in SYMBOLS:
        sub = df_strong[df_strong["symbol"] == sym]
        if sub.empty:
            sub_all = df[df["symbol"] == sym]
            if sub_all.empty: continue
            best = sub_all.sort_values("alpha_vf_pts", ascending=False).iloc[0]
        else:
            best = sub.iloc[0]
        gate_ok = best["sign"] >= 0.60 and best["binom_p"] < 0.01
        print(f"  {sym:>15}: combo={best['combo']:18s} fwd={best['fwd']} pol={best['policy']:11s} "
              f"sign={best['sign']*100:.1f}% p={best['binom_p']:.4f} "
              f"alpha_vf={best['alpha_vf_pts']:+7.2f}pts  ({'PASS' if gate_ok else 'fail'})")

    out_path = ROOT / "runs" / "binance_grid_search_v8.csv"
    df_sorted.to_csv(out_path, index=False)
    print(f"\nSaved {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
