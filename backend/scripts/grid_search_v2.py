"""Grid search v2: 12 non-passing symbols with new CrossETH source + threshold sweep.

Difference from multi_source_grid_search:
  - SOL/DOGE excluded (already confirmed)
  - +1 new source: E (CrossETH)
  - threshold sweep: 0.003, 0.005, 0.008
  - SmartMon-only baseline always included for baseline comparison

Search space:
  - 12 symbols
  - 7 source combos (S, S+E, T+E, O+E, S+T+E, T+O+E, S+T+O+E)
  - 2 fwd (5, 10)
  - 2 policies
  - 3 thresholds
  → 12 × 7 × 2 × 2 × 3 = 1008 conditions
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
    BinanceMicrostructureSource,
    BinanceSmartMoneySource,
    BinanceTakerFlowSource,
    BinanceOIDynamicsSource,
    BinanceCrossETHSource,
)
from app.db.session import SessionLocal  # noqa: E402
from app.microstructure.features import aggregate_to_eval_bars  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

warnings.filterwarnings("ignore")

# 12 symbols (SOL + DOGE excluded — already confirmed)
SYMBOLS = ["BTCUSDT", "ETHUSDT", "LINKUSDT", "AVAXUSDT", "WIFUSDT", "ADAUSDT",
           "BNBUSDT", "XRPUSDT", "NEARUSDT", "FILUSDT", "BCHUSDT", "LTCUSDT"]

# Combos with E (CrossETH) as new dimension
SOURCE_COMBOS = [
    ("S",),                # baseline single
    ("S", "E"),
    ("T", "E"),
    ("O", "E"),
    ("S", "T", "E"),
    ("T", "O", "E"),
    ("S", "T", "O", "E"),
]
FORWARD_BARS = [5, 10]
POLICIES = ["long_only", "long_short"]
THRESHOLDS = [0.003, 0.005, 0.008]
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
    df_eval = resample_ohlcv(df, "1d")
    sig_dir = ROOT / "runs" / "pattern_scanner"
    signals = None
    for p in sorted(sig_dir.glob(f"{sym}__*d__signals.joblib")):
        signals = joblib.load(p); break
    metrics = joblib.load(ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib")
    return df_eval, signals, metrics


# Cache ETH ohlcv globally (used by all symbols)
_ETH_OHLCV_CACHE = None
def get_eth_ohlcv():
    global _ETH_OHLCV_CACHE
    if _ETH_OHLCV_CACHE is None:
        df_eval, _, _ = load_data("ETHUSDT")
        _ETH_OHLCV_CACHE = df_eval
    return _ETH_OHLCV_CACHE


def attach_combo(feat_pat, df_eval, metrics, combo, eval_freq_min=1440):
    out = feat_pat
    proxy = pd.DataFrame({"close": np.nan}, index=feat_pat.index)
    eth_eval = get_eth_ohlcv()
    for code in combo:
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
        elif code == "E":
            src = BinanceCrossETHSource(eth_ohlcv_eval=eth_eval)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=df_eval)
            out = out.join(src.build_features(ctx), how="left")
    return out


def trade_sim(bars, preds, *, threshold, sl=0.06, tp=0.15, hold=5,
              fee=0.0004, policy="long_only", vol_filter=None):
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
            if c <= ent_p * (1 - sl): ex_r = "sl"; ex_p = ent_p * (1 - sl)
            elif c >= ent_p * (1 + tp): ex_r = "tp"; ex_p = ent_p * (1 + tp)
            elif held >= hold: ex_r = "time"; ex_p = o
            if ex_r:
                proc = qty * ex_p * (1 - fee)
                cost = qty * ent_p * (1 + fee)
                cash += proc
                trades.append({"ret": (proc - cost) / cost})
                qty = 0; side = "flat"
        elif side == "short":
            held = i - ent_i
            ex_r = None; ex_p = o
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
                    qty = (cash * 0.95) / o
                    cash -= qty * o
                    cash -= qty * o * fee
                    side = "short"; ent_p = o; ent_i = i
    if side == "long":
        last = float(bars.iloc[-1]["close"])
        proc = qty * last * (1 - fee)
        cost = qty * ent_p * (1 + fee)
        cash += proc
        trades.append({"ret": (proc - cost) / cost})
    elif side == "short":
        last = float(bars.iloc[-1]["close"])
        pnl = qty * (ent_p - last) - qty * ent_p * fee - qty * last * fee
        cash += qty * ent_p + pnl
        trades.append({"ret": pnl / (qty * ent_p)})
    return {"trades": len(trades), "ret": (cash - 1_000_000) / 1_000_000,
            "wr": float(np.mean([t["ret"] > 0 for t in trades])) if trades else 0.0}


def evaluate(sym, df_eval, signals, metrics, combo, fwd, policy, threshold, vol_filter_mask=None):
    cls = RegimeClassifier()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=fwd,
    )
    feat = attach_combo(feat_pat, df_eval, metrics, combo)
    n = len(feat); split = n // 2
    train = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    test = feat.iloc[split:]
    if len(train) < 30 or len(test) < 30:
        return None

    cfg = LGBMComposerConfig()
    comp = LGBMComposer(cfg)
    comp.fit(train, target_col="target_fwd_ret")
    preds = comp.predict(test)
    actuals = test["target_fwd_ret"].values
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p, a = preds[mask], actuals[mask]
    if len(p) < 10:
        return None
    hits = int((np.sign(p) == np.sign(a)).sum())
    sign = hits / len(p)
    binom_p = scistats.binomtest(hits, len(p), 0.5).pvalue

    bars = df_eval.loc[test.index]
    test_regime = regime_eval.loc[test.index]
    vol_mask = (test_regime["volatility"] != "low").values  # always test the vol filter

    kpi = trade_sim(bars, preds, threshold=threshold, hold=fwd, policy=policy)
    kpi_vf = trade_sim(bars, preds, threshold=threshold, hold=fwd, policy=policy, vol_filter=vol_mask)
    bh = (bars.iloc[-1]["close"] - bars.iloc[0]["open"]) / bars.iloc[0]["open"]
    alpha = (kpi["ret"] - bh) * 100
    alpha_vf = (kpi_vf["ret"] - bh) * 100
    return {"sign": sign, "binom_p": binom_p,
            "alpha_pts": alpha, "alpha_vf_pts": alpha_vf,
            "ret_pct": kpi["ret"] * 100, "trades": kpi["trades"],
            "trades_vf": kpi_vf["trades"]}


def main():
    print("Grid search v2 — 12 non-passing symbols + CrossETH + threshold sweep + vol filter")
    n_total = (len(SYMBOLS) * len(SOURCE_COMBOS) * len(FORWARD_BARS) * len(POLICIES)
               * len(THRESHOLDS))
    print(f"  Search: {len(SYMBOLS)} sym × {len(SOURCE_COMBOS)} combos × "
          f"{len(FORWARD_BARS)} fwd × {len(POLICIES)} pol × {len(THRESHOLDS)} thr = {n_total} conditions")

    results = []
    for sym in SYMBOLS:
        try:
            df_eval, signals, metrics = load_data(sym)
            if signals is None:
                print(f"[{sym}] SKIP no signals", flush=True)
                continue
        except Exception as e:
            print(f"[{sym}] SKIP load error: {e}", flush=True)
            continue
        n_done = 0
        for combo, fwd, policy, thr in itertools.product(SOURCE_COMBOS, FORWARD_BARS, POLICIES, THRESHOLDS):
            try:
                r = evaluate(sym, df_eval, signals, metrics, combo, fwd, policy, thr)
            except Exception:
                continue
            if r is None:
                continue
            results.append({"symbol": sym, "combo": "+".join(combo),
                            "fwd": fwd, "policy": policy, "threshold": thr, **r})
            n_done += 1
        print(f"[{sym}] {n_done} conditions done", flush=True)

    df = pd.DataFrame(results)
    df_sorted = df.sort_values("alpha_vf_pts", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 100)
    print(">>> Seed gate (sign≥60% AND p<0.01 AND alpha>0):")
    sg = df_sorted[(df_sorted["sign"] >= 0.60) & (df_sorted["binom_p"] < 0.01) & (df_sorted["alpha_pts"] > 0)]
    print(f"    {len(sg)} conditions passing baseline gate")
    if len(sg) > 0:
        print(sg[["symbol", "combo", "fwd", "policy", "threshold",
                  "sign", "binom_p", "alpha_pts", "alpha_vf_pts", "trades"]].to_string(index=False))

    print("\n" + "=" * 100)
    print(">>> SOL-equivalent (gate AND alpha_vf ≥+27pts):")
    eq = df_sorted[(df_sorted["sign"] >= 0.60) & (df_sorted["binom_p"] < 0.01)
                   & (df_sorted["alpha_vf_pts"] >= SOL_ALPHA_BASELINE)]
    print(f"    {len(eq)} conditions matching")
    if len(eq) > 0:
        print(eq[["symbol", "combo", "fwd", "policy", "threshold",
                  "sign", "binom_p", "alpha_pts", "alpha_vf_pts", "trades"]].to_string(index=False))

    print("\n" + "=" * 100)
    print(">>> Top 30 by alpha_vf_pts (vol filter applied) — overall:")
    show = df_sorted.head(30).copy()
    show["sign"] = (show["sign"] * 100).round(1)
    show["binom_p"] = show["binom_p"].round(4)
    show["alpha_pts"] = show["alpha_pts"].round(2)
    show["alpha_vf_pts"] = show["alpha_vf_pts"].round(2)
    print(show[["symbol", "combo", "fwd", "policy", "threshold",
                "sign", "binom_p", "alpha_pts", "alpha_vf_pts", "trades", "trades_vf"]].to_string(index=False))

    print("\n>>> Best per symbol (by alpha_vf_pts among gate-passing OR best near-miss):")
    for sym in SYMBOLS:
        sub = df[df["symbol"] == sym]
        if sub.empty:
            continue
        best = sub.sort_values("alpha_vf_pts", ascending=False).iloc[0]
        gate_ok = best["sign"] >= 0.60 and best["binom_p"] < 0.01
        print(f"  {sym:>10}: combo={best['combo']:18s} fwd={best['fwd']} pol={best['policy']:11s} "
              f"thr={best['threshold']:.3f} sign={best['sign']*100:.1f}% "
              f"alpha_vf={best['alpha_vf_pts']:+7.2f}pts (gate={'PASS' if gate_ok else 'fail'})")

    out_path = ROOT / "runs" / "binance_grid_search_v2.csv"
    df_sorted.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
