"""SOL Pat+SmartMoney robustness check — 5 independent diagnostics.

The 14-symbol OOS found SOL Pat+SmartMon at sign=62.1% binom_p=0.000002 alpha+118pts.
Multiple-comparison correction (×90 conditions) gives p=0.00018, still <0.001 — but
single 50/50 split with single LGBM seed could still be data-mining noise.

Five robustness diagnostics — passing at least 3 of 5 → "real SOL signal";
passing 1-2 → "likely false positive".

Diagnostics:
  1. Walk-forward (5 expanding windows, 100d test each)
  2. Forward-bars sweep (5, 10, 20)
  3. LGBM random_state sweep (5 seeds)
  4. IS/OOS split sweep (50/50, 60/40, 70/30)
  5. Permutation test (target shuffle 100×, sign baseline)
"""
from __future__ import annotations

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
from app.composer_framework.sources import BinanceSmartMoneySource  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402, F401
from app.pattern_ml.features import build_feature_matrix  # noqa: E402
from app.pattern_ml.lgbm_composer import LGBMComposer, LGBMComposerConfig  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402
from app.regime import RegimeClassifier  # noqa: E402

warnings.filterwarnings("ignore")

SYMBOL = "SOLUSDT"
SIGN_THRESHOLD = 0.55  # relaxed from 0.60 for sub-window robustness checks
PASS_VOTES_NEEDED = 3   # out of 5 diagnostics


def _load_data():
    db = SessionLocal()
    sql = text("SELECT timestamp, open, high, low, close, volume FROM ohlcv "
               "WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp")
    rows = db.execute(sql, {"s": SYMBOL}).fetchall()
    db.close()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    df_eval = resample_ohlcv(df, "1d")
    signals = joblib.load(ROOT / "runs" / "pattern_scanner" / f"{SYMBOL}__365d__signals.joblib")
    metrics = joblib.load(ROOT / "runs" / "microstructure" / f"{SYMBOL}_full_metrics.joblib")
    return df_eval, signals, metrics


def _build_features(df_eval, signals, metrics, forward_bars=5):
    cls = RegimeClassifier.for_daily()
    regime_eval = cls.classify(df_eval)
    feat_pat = build_feature_matrix(
        ohlcv_eval=df_eval, signals_df=signals, regime_eval=regime_eval,
        eval_freq_minutes=1440, forward_bars=forward_bars,
    )
    src = BinanceSmartMoneySource(metrics_5m=metrics)
    ohlcv_eval_proxy = pd.DataFrame({"close": np.nan}, index=feat_pat.index)
    ctx = SourceContext(symbol=SYMBOL, eval_freq_minutes=1440, ohlcv_eval=ohlcv_eval_proxy)
    sm_feats = src.build_features(ctx)
    return feat_pat.join(sm_feats, how="left")


def _evaluate(train_df, test_df, seed=42):
    cfg = LGBMComposerConfig(random_state=seed)
    comp = LGBMComposer(cfg)
    comp.fit(train_df, target_col="target_fwd_ret")
    preds = comp.predict(test_df)
    actuals = test_df["target_fwd_ret"].values
    mask = ~(np.isnan(preds) | np.isnan(actuals))
    p, a = preds[mask], actuals[mask]
    if len(p) < 10:
        return None
    hits = int((np.sign(p) == np.sign(a)).sum())
    sign = hits / len(p)
    binom_p = stats.binomtest(hits, len(p), 0.5).pvalue
    return {"n": len(p), "sign": sign, "binom_p": binom_p}


# ─────────────────────────── Diagnostic 1: walk-forward ───
def diagnostic_walk_forward(feat):
    """5 expanding windows, ~100d test each."""
    print("\n" + "=" * 70)
    print("[1/5] WALK-FORWARD VALIDATION (5 expanding windows)")
    print("=" * 70)
    n = len(feat)
    test_size = max(80, n // 8)
    windows = []
    for i in range(5):
        train_end = n // 3 + i * test_size
        test_end = train_end + test_size
        if test_end > n:
            break
        train_df = feat.iloc[:train_end].dropna(subset=["target_fwd_ret"])
        test_df = feat.iloc[train_end:test_end]
        if len(train_df) < 50 or len(test_df) < 30:
            continue
        windows.append((train_df, test_df, train_end, test_end))

    results = []
    for i, (tr, te, tr_end, te_end) in enumerate(windows):
        r = _evaluate(tr, te)
        if r is None:
            print(f"  window {i+1}: SKIP")
            continue
        results.append(r)
        print(f"  window {i+1} (train→{tr_end}, test {tr_end}-{te_end}): "
              f"n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")

    passed = sum(1 for r in results if r["sign"] >= SIGN_THRESHOLD)
    avg_sign = np.mean([r["sign"] for r in results])
    verdict = passed >= max(3, len(results) - 1)
    print(f"  Result: {passed}/{len(results)} windows ≥{SIGN_THRESHOLD*100:.0f}% sign, "
          f"avg sign={avg_sign*100:.1f}% — {'PASS' if verdict else 'FAIL'}")
    return verdict


# ─────────────────────────── Diagnostic 2: forward-bars ───
def diagnostic_forward_bars(df_eval, signals, metrics):
    print("\n" + "=" * 70)
    print("[2/5] FORWARD-BARS SWEEP (fwd=5, 10, 20)")
    print("=" * 70)
    results = []
    for fwd in (5, 10, 20):
        feat = _build_features(df_eval, signals, metrics, forward_bars=fwd)
        n = len(feat)
        split = n // 2
        tr = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
        te = feat.iloc[split:]
        r = _evaluate(tr, te)
        if r is None:
            continue
        results.append((fwd, r))
        print(f"  fwd={fwd:>2}: n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")

    passed = sum(1 for _, r in results if r["sign"] >= SIGN_THRESHOLD)
    verdict = passed >= 2  # 2/3 sweeps
    print(f"  Result: {passed}/{len(results)} fwd-bars ≥{SIGN_THRESHOLD*100:.0f}% sign — "
          f"{'PASS' if verdict else 'FAIL'}")
    return verdict


# ─────────────────────────── Diagnostic 3: LGBM seeds ───
def diagnostic_seeds(feat):
    print("\n" + "=" * 70)
    print("[3/5] LGBM RANDOM-STATE SWEEP (5 seeds)")
    print("=" * 70)
    n = len(feat)
    split = n // 2
    tr = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    te = feat.iloc[split:]
    results = []
    for seed in (0, 1, 2, 7, 42):
        r = _evaluate(tr, te, seed=seed)
        if r is None:
            continue
        results.append((seed, r))
        print(f"  seed={seed:>2}: n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")

    avg_sign = np.mean([r["sign"] for _, r in results])
    passed = sum(1 for _, r in results if r["sign"] >= SIGN_THRESHOLD)
    verdict = passed >= 4  # 4/5 seeds — strong consistency required
    print(f"  Result: {passed}/{len(results)} seeds ≥{SIGN_THRESHOLD*100:.0f}% sign, "
          f"avg sign={avg_sign*100:.1f}% — {'PASS' if verdict else 'FAIL'}")
    return verdict


# ─────────────────────────── Diagnostic 4: split ratios ───
def diagnostic_split_ratios(feat):
    print("\n" + "=" * 70)
    print("[4/5] IS/OOS SPLIT SWEEP (50/50, 60/40, 70/30)")
    print("=" * 70)
    n = len(feat)
    results = []
    for label, ratio in (("50/50", 0.5), ("60/40", 0.6), ("70/30", 0.7)):
        split = int(n * ratio)
        tr = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
        te = feat.iloc[split:]
        r = _evaluate(tr, te)
        if r is None:
            continue
        results.append((label, r))
        print(f"  {label}: n={r['n']} sign={r['sign']*100:.1f}% p={r['binom_p']:.4f}")

    passed = sum(1 for _, r in results if r["sign"] >= SIGN_THRESHOLD)
    verdict = passed >= 2  # 2/3 splits
    print(f"  Result: {passed}/{len(results)} splits ≥{SIGN_THRESHOLD*100:.0f}% sign — "
          f"{'PASS' if verdict else 'FAIL'}")
    return verdict


# ─────────────────────────── Diagnostic 5: permutation ───
def diagnostic_permutation(feat, n_perm=100):
    print("\n" + "=" * 70)
    print(f"[5/5] PERMUTATION TEST (target shuffle, n={n_perm})")
    print("=" * 70)
    n = len(feat)
    split = n // 2
    tr_full = feat.iloc[:split].dropna(subset=["target_fwd_ret"])
    te_full = feat.iloc[split:]

    # actual sign
    actual = _evaluate(tr_full, te_full)
    print(f"  actual: sign={actual['sign']*100:.1f}% p={actual['binom_p']:.4f}")

    rng = np.random.default_rng(42)
    perm_signs = []
    for k in range(n_perm):
        tr_shuf = tr_full.copy()
        tr_shuf["target_fwd_ret"] = rng.permutation(tr_shuf["target_fwd_ret"].values)
        r = _evaluate(tr_shuf, te_full)
        if r is None:
            continue
        perm_signs.append(r["sign"])
        if (k + 1) % 25 == 0:
            print(f"  ...permutation {k+1}/{n_perm} done", flush=True)

    perm_arr = np.array(perm_signs)
    pct95 = np.percentile(perm_arr, 95)
    pct99 = np.percentile(perm_arr, 99)
    p_value = float((perm_arr >= actual["sign"]).mean())
    verdict = p_value < 0.05
    print(f"  perm null distribution: mean={perm_arr.mean()*100:.1f}% "
          f"95th={pct95*100:.1f}% 99th={pct99*100:.1f}%")
    print(f"  actual sign {actual['sign']*100:.1f}% — empirical p={p_value:.3f} — "
          f"{'PASS' if verdict else 'FAIL'}")
    return verdict


def main() -> int:
    print(f"Robustness check for {SYMBOL} Pat+SmartMoney variant")
    print(f"  pass threshold per diagnostic: sign≥{SIGN_THRESHOLD*100:.0f}%")
    print(f"  overall verdict: pass {PASS_VOTES_NEEDED}/5 to confirm signal")

    df_eval, signals, metrics = _load_data()
    print(f"\nData: {len(df_eval)} daily eval bars, {df_eval.index[0].date()} → {df_eval.index[-1].date()}")
    print(f"      pattern signals: {len(signals):,} rows")
    print(f"      smart money 5min metrics: {len(metrics):,} rows")

    # Build base feature matrix once with default fwd=5
    feat_base = _build_features(df_eval, signals, metrics, forward_bars=5)
    print(f"      feature matrix: {feat_base.shape}")

    votes = []
    votes.append(("walk_forward", diagnostic_walk_forward(feat_base)))
    votes.append(("forward_bars", diagnostic_forward_bars(df_eval, signals, metrics)))
    votes.append(("seeds", diagnostic_seeds(feat_base)))
    votes.append(("split_ratios", diagnostic_split_ratios(feat_base)))
    votes.append(("permutation", diagnostic_permutation(feat_base, n_perm=100)))

    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    for name, ok in votes:
        print(f"  {name:15s} : {'PASS' if ok else 'FAIL'}")
    n_pass = sum(1 for _, ok in votes if ok)
    print(f"\n  Total: {n_pass}/5 diagnostics passed")
    if n_pass >= PASS_VOTES_NEEDED:
        print(f"  → CONFIRMED: SOL Pat+SmartMoney is a real signal")
    else:
        print(f"  → LIKELY FALSE POSITIVE: insufficient robustness — do NOT seed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
