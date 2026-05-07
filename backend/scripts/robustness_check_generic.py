"""Generic robustness check for any (symbol, source_combo, forward_bars) candidate.

Same 5-diagnostic protocol as robustness_check_sol.py:
  1. Walk-forward (5 expanding windows)
  2. Forward-bars sweep (5, 10, 20)
  3. LGBM seed sweep (5 seeds)
  4. IS/OOS split sweep (50/50, 60/40, 70/30)
  5. Permutation test (n=100)

Pass criterion: 3+/5 diagnostics → confirmed signal.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats
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
    BinanceBookDepthSource,
    BinanceEventDetectorSource,
    BinanceMTFAlignmentSource,
    BinanceCascadeReversalSource,
)
from app.db.session import SessionLocal  # noqa: E402
from app.microstructure.features import aggregate_to_eval_bars  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

warnings.filterwarnings("ignore")

SIGN_THRESHOLD = 0.55
PASS_VOTES_NEEDED = 3
_CURRENT_SYM = None
_CURRENT_DF1M = None


_ETH_CACHE = None
_PREMIUM_CACHE = {}
_BD_CACHE = {}


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
    return df_eval, signals, metrics, df_1m


def _get_eth_eval():
    global _ETH_CACHE
    if _ETH_CACHE is None:
        df_eval, _, _ = load_data("ETHUSDT")
        _ETH_CACHE = df_eval
    return _ETH_CACHE


def _get_premium(sym):
    if sym in _PREMIUM_CACHE: return _PREMIUM_CACHE[sym]
    p = ROOT / "runs" / "premium_index" / f"{sym}_premium.joblib"
    _PREMIUM_CACHE[sym] = joblib.load(p) if p.exists() else None
    return _PREMIUM_CACHE[sym]


def _get_bd(sym):
    if sym in _BD_CACHE: return _BD_CACHE[sym]
    p = ROOT / "runs" / "book_depth" / f"{sym}_bookdepth.joblib"
    _BD_CACHE[sym] = joblib.load(p) if p.exists() else None
    return _BD_CACHE[sym]


def attach_combo(feat_pat, df_eval, metrics, combo, eval_freq_min=1440, sym=None, df_1m=None):
    """Attach features for a combo string like 'S', 'S+T', 'T+O+P', 'V+C', 'V+M+C'."""
    out = feat_pat
    codes = combo.split("+")
    proxy = pd.DataFrame({"close": np.nan}, index=feat_pat.index)
    ctx_full = SourceContext(symbol=sym or "", eval_freq_minutes=eval_freq_min,
                              ohlcv_1m=df_1m, ohlcv_eval=df_eval)
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
        elif code == "E":
            src = BinanceCrossETHSource(eth_ohlcv_eval=_get_eth_eval())
            ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=df_eval)
            out = out.join(src.build_features(ctx), how="left")
        elif code == "P":
            premium = _get_premium(sym)
            if premium is not None and not premium.empty:
                src = BinancePremiumSource(premium_df=premium)
                ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)
                out = out.join(src.build_features(ctx), how="left")
        elif code == "B":
            bd = _get_bd(sym)
            if bd is not None and not bd.empty:
                src = BinanceBookDepthSource(bd_daily=bd)
                ctx = SourceContext(symbol="", eval_freq_minutes=eval_freq_min, ohlcv_eval=proxy)
                out = out.join(src.build_features(ctx), how="left")
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


def build_features(df_eval, signals, metrics, combo, fwd):
    cls = RegimeClassifier.for_daily()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=fwd,
    )
    return attach_combo(feat_pat, df_eval, metrics, combo, sym=_CURRENT_SYM, df_1m=_CURRENT_DF1M)


def evaluate(train, test, seed=42):
    cfg = LGBMComposerConfig(random_state=seed)
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
    binom_p = stats.binomtest(hits, len(p), 0.5).pvalue
    return {"n": len(p), "sign": sign, "binom_p": binom_p}


def diag_walk_forward(feat):
    n = len(feat)
    test_size = max(80, n // 8)
    results = []
    for i in range(5):
        tr_end = n // 3 + i * test_size
        te_end = tr_end + test_size
        if te_end > n: break
        tr = feat.iloc[:tr_end].dropna(subset=["target_fwd_ret"])
        te = feat.iloc[tr_end:te_end]
        if len(tr) < 50 or len(te) < 30: continue
        r = evaluate(tr, te)
        if r is None: continue
        results.append(r)
        print(f"  window {i+1}: n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")
    passed = sum(1 for r in results if r["sign"] >= SIGN_THRESHOLD)
    avg = np.mean([r["sign"] for r in results]) if results else 0
    verdict = passed >= max(3, len(results) - 1)
    print(f"  → {passed}/{len(results)} ≥{SIGN_THRESHOLD*100:.0f}%, avg={avg*100:.1f}% — "
          f"{'PASS' if verdict else 'FAIL'}")
    return verdict


def diag_forward_bars(df_eval, signals, metrics, combo):
    results = []
    for fwd in (5, 10, 20):
        feat = build_features(df_eval, signals, metrics, combo, fwd)
        n = len(feat); split = n // 2
        tr = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
        te = feat.iloc[split:]
        r = evaluate(tr, te)
        if r is None: continue
        results.append((fwd, r))
        print(f"  fwd={fwd:>2}: n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")
    passed = sum(1 for _, r in results if r["sign"] >= SIGN_THRESHOLD)
    verdict = passed >= 2
    print(f"  → {passed}/{len(results)} ≥{SIGN_THRESHOLD*100:.0f}% — {'PASS' if verdict else 'FAIL'}")
    return verdict


def diag_seeds(feat):
    n = len(feat); split = n // 2
    tr = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    te = feat.iloc[split:]
    results = []
    for seed in (0, 1, 2, 7, 42):
        r = evaluate(tr, te, seed=seed)
        if r is None: continue
        results.append((seed, r))
        print(f"  seed={seed:>2}: sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")
    avg = np.mean([r["sign"] for _, r in results])
    passed = sum(1 for _, r in results if r["sign"] >= SIGN_THRESHOLD)
    verdict = passed >= 4
    print(f"  → {passed}/{len(results)} ≥{SIGN_THRESHOLD*100:.0f}%, avg={avg*100:.1f}% — "
          f"{'PASS' if verdict else 'FAIL'}")
    return verdict


def diag_split_ratios(feat):
    n = len(feat); results = []
    for label, ratio in (("50/50", 0.5), ("60/40", 0.6), ("70/30", 0.7)):
        split = int(n * ratio)
        tr = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
        te = feat.iloc[split:]
        r = evaluate(tr, te)
        if r is None: continue
        results.append((label, r))
        print(f"  {label}: n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")
    passed = sum(1 for _, r in results if r["sign"] >= SIGN_THRESHOLD)
    verdict = passed >= 2
    print(f"  → {passed}/{len(results)} ≥{SIGN_THRESHOLD*100:.0f}% — {'PASS' if verdict else 'FAIL'}")
    return verdict


def diag_permutation(feat, n_perm=100):
    n = len(feat); split = n // 2
    tr_full = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    te_full = feat.iloc[split:]
    actual = evaluate(tr_full, te_full)
    print(f"  actual: sign={actual['sign']*100:.1f}% p={actual['binom_p']:.4f}")
    rng = np.random.default_rng(42)
    perm_signs = []
    for k in range(n_perm):
        tr_shuf = tr_full.copy()
        tr_shuf["target_fwd_ret"] = rng.permutation(tr_shuf["target_fwd_ret"].values)
        r = evaluate(tr_shuf, te_full)
        if r is not None:
            perm_signs.append(r["sign"])
    perm_arr = np.array(perm_signs)
    pct95 = np.percentile(perm_arr, 95)
    pct99 = np.percentile(perm_arr, 99)
    p_value = float((perm_arr >= actual["sign"]).mean())
    verdict = p_value < 0.05
    print(f"  null mean={perm_arr.mean()*100:.1f}% 95th={pct95*100:.1f}% 99th={pct99*100:.1f}% "
          f"empirical p={p_value:.3f} — {'PASS' if verdict else 'FAIL'}")
    return verdict


def run_check(symbol, combo, fwd):
    global _CURRENT_SYM, _CURRENT_DF1M
    _CURRENT_SYM = symbol
    print(f"\n{'#' * 80}")
    print(f"# ROBUSTNESS CHECK: {symbol} combo={combo} fwd={fwd}")
    print(f"{'#' * 80}")
    df_eval, signals, metrics, df_1m = load_data(symbol)
    _CURRENT_DF1M = df_1m
    feat = build_features(df_eval, signals, metrics, combo, fwd)
    print(f"Data: {len(df_eval)} eval bars, {df_eval.index[0].date()} → {df_eval.index[-1].date()}")
    print(f"Feature matrix: {feat.shape}")

    print("\n[1/5] WALK-FORWARD")
    v1 = diag_walk_forward(feat)
    print("\n[2/5] FORWARD-BARS")
    v2 = diag_forward_bars(df_eval, signals, metrics, combo)
    print("\n[3/5] LGBM SEEDS")
    v3 = diag_seeds(feat)
    print("\n[4/5] IS/OOS SPLITS")
    v4 = diag_split_ratios(feat)
    print("\n[5/5] PERMUTATION (n=100)")
    v5 = diag_permutation(feat, n_perm=100)

    votes = {"walk_forward": v1, "forward_bars": v2, "seeds": v3, "splits": v4, "permutation": v5}
    n_pass = sum(votes.values())
    print(f"\n>>> Result: {n_pass}/5 — "
          f"{'CONFIRMED' if n_pass >= PASS_VOTES_NEEDED else 'LIKELY FALSE POSITIVE'}")
    return symbol, combo, fwd, n_pass, votes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", nargs="+", required=True,
                   help="format: SYMBOL:combo:fwd  e.g. DOGEUSDT:T+O:10 SOLUSDT:S+T:10")
    args = p.parse_args()

    print(f"Robustness check on {len(args.candidates)} candidate(s)")
    print(f"Pass threshold: sign≥{SIGN_THRESHOLD*100:.0f}% per diagnostic, "
          f"{PASS_VOTES_NEEDED}/5 diagnostics for confirmation")

    summary = []
    for spec in args.candidates:
        sym, combo, fwd_str = spec.split(":")
        fwd = int(fwd_str)
        try:
            res = run_check(sym, combo, fwd)
            summary.append(res)
        except Exception as e:
            print(f"\n[{sym}/{combo}/fwd={fwd}] ERROR: {e}")

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    for sym, combo, fwd, n_pass, votes in summary:
        v_str = " ".join(f"{k[:4]}={'P' if v else 'F'}" for k, v in votes.items())
        verdict = "CONFIRMED" if n_pass >= PASS_VOTES_NEEDED else "FALSE POSITIVE"
        print(f"  {sym} {combo} fwd={fwd}: {n_pass}/5  ({v_str})  → {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
