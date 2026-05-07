"""Grid search for SOL-equivalent combinations.

Target: signal at least as strong as SOL Pat+SmartMon
  - sign ≥ 60%, binom_p < 0.01, alpha > 0  (seed gate)
  - alpha_long_short ≥ +27pts (SOL long_only baseline)

Search space:
  - 14 symbols
  - 8 source combinations (single + pair + triple)
  - 2 forward bars (5, 10)
  - 2 policies (long_only, long_short)
  → 14 × 8 × 2 × 2 = 896 conditions

Outputs sorted ranking + count of conditions surpassing SOL alpha.
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
)
from app.db.session import SessionLocal  # noqa: E402
from app.microstructure.features import aggregate_to_eval_bars  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

warnings.filterwarnings("ignore")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "DOGEUSDT", "AVAXUSDT",
           "WIFUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT", "NEARUSDT", "FILUSDT",
           "BCHUSDT", "LTCUSDT"]

# Source combinations to test (M=micro/Combined, S=SmartMon, T=TakerFlow, O=OIDyn)
SOURCE_COMBOS = [
    ("S",),         # SmartMoney only (baseline winner)
    ("T",),         # TakerFlow only
    ("O",),         # OIDynamics only
    ("M", "S"),     # legacy micro + smart
    ("S", "T"),     # smart + taker
    ("S", "O"),     # smart + oi
    ("T", "O"),     # taker + oi
    ("S", "T", "O"),# all three new
    ("M", "S", "T", "O"),  # everything
]

FORWARD_BARS = [5, 10]
POLICIES = ["long_only", "long_short"]
SOL_ALPHA_BASELINE = 27.0  # SOL Pat+SmartMon long_only alpha


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
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df_eval = resample_ohlcv(df, "1d")

    # signals (any version)
    sig_dir = ROOT / "runs" / "pattern_scanner"
    sig_path = None
    for p in sorted(sig_dir.glob(f"{sym}__*d__signals.joblib")):
        sig_path = p
        break
    signals = joblib.load(sig_path) if sig_path else None
    metrics = joblib.load(ROOT / "runs" / "microstructure" / f"{sym}_full_metrics.joblib")
    return df_eval, signals, metrics


def attach_sources(feat_pat, df_eval, metrics, combo, eval_freq_min=1440):
    out = feat_pat
    for code in combo:
        if code == "M":
            micro = aggregate_to_eval_bars(metrics, feat_pat.index, eval_freq_min)
            if "micro_" not in "".join(micro.columns):
                micro = micro.add_prefix("micro_")
            out = out.join(micro, how="left")
        elif code == "S":
            src = BinanceSmartMoneySource(metrics_5m=metrics)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min,
                                ohlcv_eval=pd.DataFrame({"close": np.nan}, index=feat_pat.index))
            out = out.join(src.build_features(ctx), how="left")
        elif code == "T":
            src = BinanceTakerFlowSource(metrics_5m=metrics)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min,
                                ohlcv_eval=pd.DataFrame({"close": np.nan}, index=feat_pat.index))
            out = out.join(src.build_features(ctx), how="left")
        elif code == "O":
            src = BinanceOIDynamicsSource(metrics_5m=metrics)
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min,
                                ohlcv_eval=df_eval)
            out = out.join(src.build_features(ctx), how="left")
    return out


def trade_sim(bars, preds, *, threshold=0.005, sl=0.06, tp=0.15, hold=5,
              fee=0.0004, policy="long_only"):
    """Same as ml_binance_oos.trade_sim, copied for self-contained run."""
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


def evaluate(sym, df_eval, signals, metrics, combo, fwd, policy):
    cls = RegimeClassifier.for_daily()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=fwd,
    )
    feat = attach_sources(feat_pat, df_eval, metrics, combo)
    n = len(feat)
    split = n // 2
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
    kpi = trade_sim(bars, preds, hold=fwd, policy=policy)
    bh = (bars.iloc[-1]["close"] - bars.iloc[0]["open"]) / bars.iloc[0]["open"]
    alpha = (kpi["ret"] - bh) * 100

    return {"sign": sign, "binom_p": binom_p, "alpha_pts": alpha,
            "ret_pct": kpi["ret"] * 100, "bh_pct": bh * 100,
            "trades": kpi["trades"], "wr": kpi["wr"] * 100}


def main():
    print("Multi-source grid search — looking for SOL-equivalent or stronger combinations")
    print(f"  Target: sign≥60% AND p<0.01 AND alpha>+{SOL_ALPHA_BASELINE}pts")
    print(f"  Search: {len(SYMBOLS)} symbols × {len(SOURCE_COMBOS)} combos × "
          f"{len(FORWARD_BARS)} fwd × {len(POLICIES)} policies = "
          f"{len(SYMBOLS) * len(SOURCE_COMBOS) * len(FORWARD_BARS) * len(POLICIES)} conditions")
    print()

    results = []
    for sym in SYMBOLS:
        try:
            df_eval, signals, metrics = load_data(sym)
        except Exception as e:
            print(f"[{sym}] SKIP: {e}", flush=True)
            continue
        if signals is None or len(metrics) == 0:
            print(f"[{sym}] SKIP: missing signals/metrics", flush=True)
            continue

        n_done = 0
        for combo, fwd, policy in itertools.product(SOURCE_COMBOS, FORWARD_BARS, POLICIES):
            try:
                r = evaluate(sym, df_eval, signals, metrics, combo, fwd, policy)
            except Exception as e:
                continue
            if r is None:
                continue
            results.append({
                "symbol": sym,
                "combo": "+".join(combo),
                "fwd": fwd,
                "policy": policy,
                **r,
            })
            n_done += 1
        print(f"[{sym}] {n_done} conditions evaluated", flush=True)

    df = pd.DataFrame(results)
    print()
    print("=" * 100)
    print("FULL RESULTS")
    print("=" * 100)
    df_sorted = df.sort_values("alpha_pts", ascending=False).reset_index(drop=True)

    # Seed gate
    sg = df_sorted[(df_sorted["sign"] >= 0.60) & (df_sorted["binom_p"] < 0.01) & (df_sorted["alpha_pts"] > 0)]
    print(f"\n>>> Seed gate (sign≥60% AND p<0.01 AND alpha>0): {len(sg)} passing conditions")
    if len(sg) > 0:
        print(sg[["symbol", "combo", "fwd", "policy", "sign", "binom_p", "alpha_pts", "trades", "wr"]].to_string(index=False))

    # SOL-equivalent or stronger
    sol_match = df_sorted[(df_sorted["sign"] >= 0.60) & (df_sorted["binom_p"] < 0.01)
                          & (df_sorted["alpha_pts"] >= SOL_ALPHA_BASELINE)]
    print(f"\n>>> SOL-equivalent (gate AND alpha≥{SOL_ALPHA_BASELINE}pts): {len(sol_match)} conditions")
    if len(sol_match) > 0:
        print(sol_match[["symbol", "combo", "fwd", "policy", "sign", "binom_p", "alpha_pts", "trades", "wr"]].to_string(index=False))

    # Top 30 by alpha
    print(f"\n>>> Top 30 by alpha (regardless of gate):")
    show = df_sorted.head(30).copy()
    show["sign"] = (show["sign"] * 100).round(1)
    show["binom_p"] = show["binom_p"].round(4)
    show["alpha_pts"] = show["alpha_pts"].round(2)
    show["wr"] = show["wr"].round(1)
    print(show[["symbol", "combo", "fwd", "policy", "sign", "binom_p", "alpha_pts", "trades", "wr"]].to_string(index=False))

    # Per-source ratio
    print("\n>>> Pass ratio per source combination:")
    for combo_name, sub in df.groupby("combo"):
        pass_ct = ((sub["sign"] >= 0.60) & (sub["binom_p"] < 0.01) & (sub["alpha_pts"] > 0)).sum()
        print(f"  {combo_name:18s}  {pass_ct:>2}/{len(sub):>2}  ({pass_ct/len(sub)*100:.1f}%)")

    # Save full results to disk for later use
    out_path = ROOT / "runs" / "binance_grid_search.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_sorted.to_csv(out_path, index=False)
    print(f"\nSaved full results to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
