"""Grid search v5 — Binance NATIVE source combinations.

Pure Binance dynamics: 5min event detection (V), Multi-Timeframe alignment (M),
Cascade reversal (C). NO KR Flow analogue (no daily cum/zscore-only sources).

Combos:
  V              - events alone
  M              - multi-TF alone
  C              - cascade alone
  V+M            - events + MTF
  V+C            - events + cascade
  M+C            - MTF + cascade
  V+M+C          - all native
  V+M+C+S        - native + KR-style smartmoney (compare)
  V+M+C+T+O      - native + DOGE winner (compare)

Search:
  14 symbols × 9 combos × 2 fwd × 2 policy × 1 thr = 504 conditions
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

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT",
           "WIFUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT", "NEARUSDT", "FILUSDT",
           "BCHUSDT", "LTCUSDT"]

# V=events, M=mtf, C=cascade, S=smartmoney(KR-style), T=taker, O=oidynamics
SOURCE_COMBOS = [
    ("V",),
    ("M",),
    ("C",),
    ("V", "M"),
    ("V", "C"),
    ("M", "C"),
    ("V", "M", "C"),                  # pure native
    ("V", "M", "C", "S"),             # native + SOL anchor
    ("V", "M", "C", "T", "O"),        # native + DOGE anchor
]
FORWARD_BARS = [5, 10]
POLICIES = ["long_only", "long_short"]
THRESHOLDS = [0.005]
SOL_ALPHA_BASELINE = 27.0


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
    metrics = joblib.load(ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib")
    return df_1m, df_eval, signals, metrics


def attach_combo(feat_pat, df_1m, df_eval, metrics, combo, eval_freq_min=1440):
    out = feat_pat
    proxy = pd.DataFrame({"close": np.nan}, index=feat_pat.index)
    ctx_full = SourceContext(symbol="", eval_freq_minutes=eval_freq_min,
                              ohlcv_1m=df_1m, ohlcv_eval=df_eval)
    for code in combo:
        if code == "V":
            src = BinanceEventDetectorSource(metrics_5m=metrics)
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "M":
            src = BinanceMTFAlignmentSource()
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "C":
            src = BinanceCascadeReversalSource(metrics_5m=metrics)
            out = out.join(src.build_features(ctx_full), how="left")
        elif code == "S":
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
    return out


def trade_sim(bars, preds, *, threshold, sl=0.06, tp=0.15, hold=5,
              fee=0.0004, policy="long_only", vol_filter=None):
    cash = 1_000_000; qty = 0; ent_p = 0; ent_i = -1
    side = "flat"; trades = []
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
                    cash -= qty * o * (1 + fee)
                    side = "long"; ent_p = o; ent_i = i
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


def evaluate(sym, df_1m, df_eval, signals, metrics, combo, fwd, policy, threshold):
    cls = RegimeClassifier()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=fwd,
    )
    feat = attach_combo(feat_pat, df_1m, df_eval, metrics, combo)
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
    print(f"Grid v5 — Binance NATIVE sources (V/M/C). {n_total} conditions.")

    results = []
    for sym in SYMBOLS:
        try:
            df_1m, df_eval, signals, metrics = load_data(sym)
            if signals is None:
                print(f"[{sym}] SKIP no signals"); continue
        except Exception as e:
            print(f"[{sym}] SKIP load: {e}"); continue
        n_done = 0
        for combo, fwd, policy, thr in itertools.product(SOURCE_COMBOS, FORWARD_BARS, POLICIES, THRESHOLDS):
            try:
                r = evaluate(sym, df_1m, df_eval, signals, metrics, combo, fwd, policy, thr)
            except Exception:
                continue
            if r is None: continue
            results.append({"symbol": sym, "combo": "+".join(combo),
                            "fwd": fwd, "policy": policy, "threshold": thr, **r})
            n_done += 1
        print(f"[{sym}] {n_done} done", flush=True)

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

    print("\n>>> Best per symbol (by sign desc, alpha_vf desc):")
    for sym in SYMBOLS:
        sub = df[df["symbol"] == sym]
        if sub.empty: continue
        best = sub.sort_values(["sign", "alpha_vf_pts"], ascending=[False, False]).iloc[0]
        gate_ok = best["sign"] >= 0.60 and best["binom_p"] < 0.01
        print(f"  {sym:>10}: combo={best['combo']:18s} fwd={best['fwd']} pol={best['policy']:11s} "
              f"sign={best['sign']*100:.1f}% p={best['binom_p']:.4f} "
              f"alpha_vf={best['alpha_vf_pts']:+7.2f}pts  ({'PASS' if gate_ok else 'fail'})")

    out_path = ROOT / "runs" / "binance_grid_search_v5.csv"
    df_sorted.to_csv(out_path, index=False)
    print(f"\nSaved {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
