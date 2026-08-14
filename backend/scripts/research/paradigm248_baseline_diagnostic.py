"""Diagnostic: does the on-chain AdrActCnt regime filter add ANYTHING
over a naive 'BTC yesterday sign → alt continuation 24h' baseline?

Test:
1. Baseline: for EVERY trigger date (all 843 aligned days), LONG alt if BTC_prior > 0, SHORT if < 0. Hold 24h.
2. Focus: only on the SUBSET where regime meets HIGH/LOW filter.
3. Compare mean_net_bp, t_stat, and n between baseline vs focus subset.

If focus edge >= baseline edge → filter adds value.
If focus edge ≈ baseline edge → Lesson #21 axis stacking / Lesson #32 baseline-coherent drift.
"""
from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p248_baseline")

PARADIGM = "btc_onchain_active_address_regime_alt_bilateral_24h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

POC_ALTS = ["SOLUSDT", "DOGEUSDT", "ETHUSDT"]
FEE_RT = 0.0008

CM_URL = (
    "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    "?assets=btc&metrics=AdrActCnt&frequency=1d"
    "&start_time=2023-06-01T00:00:00Z&end_time=2026-08-08T00:00:00Z&page_size=10000"
)


def fetch_aac():
    with urllib.request.urlopen(CM_URL, timeout=60) as r:
        d = json.loads(r.read())
    df = pd.DataFrame(d["data"])
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None).dt.normalize()
    df["AdrActCnt"] = pd.to_numeric(df["AdrActCnt"], errors="coerce")
    return df.set_index("time")["AdrActCnt"].sort_index()


def load_hourly(sym):
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    idx = df.index
    if idx.tz is not None:
        df.index = idx.tz_convert(None)
    return df["close"].resample("1h").last().dropna()


def load_daily(sym):
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.DataFrame()
    idx = df.index
    if idx.tz is not None:
        df.index = idx.tz_convert(None)
    d = pd.DataFrame({"close": df["close"].resample("1D").last()}).dropna()
    d.index = d.index.normalize()
    return d


def eval_ret(returns):
    if len(returns) < 5:
        return {"n": len(returns), "insufficient": True}
    r = np.array(returns)
    mean = r.mean()
    std = r.std(ddof=1)
    t = mean / std * np.sqrt(len(r)) if std > 0 else 0
    return {
        "n": int(len(r)),
        "mean_bp": round(float(mean) * 10000, 2),
        "std_bp": round(float(std) * 10000, 2),
        "t_stat": round(float(t), 3),
        "winrate": round(float((r > 0).mean()), 3),
    }


def build_pooled_trades(regime_mask_series, btc_sign_series, alt_hourly_dict, hold_h, direction_fn):
    """direction_fn(btc_sign) -> +1 or -1."""
    entries = regime_mask_series.index[regime_mask_series.fillna(False)]
    all_trades = []
    for sym, alt_h in alt_hourly_dict.items():
        for d in entries:
            btc_sign = btc_sign_series.get(d)
            if pd.isna(btc_sign) or btc_sign == 0:
                continue
            direction = direction_fn(btc_sign)
            e_ts = d
            x_ts = d + pd.Timedelta(hours=hold_h)
            e_idx = alt_h.index.get_indexer([e_ts], method="nearest", tolerance=pd.Timedelta("30min"))
            x_idx = alt_h.index.get_indexer([x_ts], method="nearest", tolerance=pd.Timedelta("30min"))
            if e_idx[0] == -1 or x_idx[0] == -1:
                continue
            ep = alt_h.iloc[e_idx[0]]
            xp = alt_h.iloc[x_idx[0]]
            if pd.isna(ep) or pd.isna(xp) or ep <= 0:
                continue
            raw = (xp / ep - 1) * direction
            all_trades.append(raw - FEE_RT)
    return all_trades


def main():
    aac = fetch_aac().dropna()
    pct30 = aac.rolling(30, min_periods=20).apply(
        lambda w: (w < w.iloc[-1]).sum() / (len(w) - 1) if len(w) > 1 else np.nan, raw=False
    )
    pct30_lag1 = pct30.shift(1).dropna()

    btc_daily = load_daily("BTCUSDT")
    btc_ret_prior = btc_daily["close"].pct_change()
    btc_sign_prior = np.sign(btc_ret_prior)

    alt_hourly = {sym: load_hourly(sym) for sym in POC_ALTS}
    alt_hourly = {k: v for k, v in alt_hourly.items() if not v.empty}

    common = pct30_lag1.index.intersection(btc_sign_prior.dropna().index)
    regime = pct30_lag1.reindex(common)
    btc_sign = btc_sign_prior.reindex(common)

    log.info("common dates: %d", len(common))

    hold_h = 24

    # === BASELINE: no regime filter, just BTC-sign continuation for all days ===
    baseline_mask = pd.Series(True, index=common)
    def dir_continuation(bsign):
        return int(bsign)  # +1 if BTC up prior day → LONG alt; -1 if down → SHORT alt
    baseline_trades = build_pooled_trades(baseline_mask, btc_sign, alt_hourly, hold_h, dir_continuation)
    baseline_eval = eval_ret(baseline_trades)
    baseline_ci = bootstrap_ci(baseline_trades, n_boot=1500, block_size=5) if len(baseline_trades) >= 5 else None
    log.info("BASELINE (BTC-sign continuation, no regime filter): %s", baseline_eval)
    if baseline_ci:
        log.info("  CI: mean=%.1fbp lower=%.1fbp upper=%.1fbp",
                 baseline_ci["mean"]*10000, baseline_ci["ci_lower"]*10000, baseline_ci["ci_upper"]*10000)

    # === HIGH regime filter ===
    high_mask = regime > 0.70
    high_trades = build_pooled_trades(high_mask, btc_sign, alt_hourly, hold_h, dir_continuation)
    high_eval = eval_ret(high_trades)
    high_ci = bootstrap_ci(high_trades, n_boot=1500, block_size=5) if len(high_trades) >= 5 else None
    log.info("HIGH regime (pct30>0.70): %s", high_eval)
    if high_ci:
        log.info("  CI: mean=%.1fbp lower=%.1fbp upper=%.1fbp",
                 high_ci["mean"]*10000, high_ci["ci_lower"]*10000, high_ci["ci_upper"]*10000)

    # === LOW regime filter ===
    low_mask = regime < 0.30
    low_trades = build_pooled_trades(low_mask, btc_sign, alt_hourly, hold_h, dir_continuation)
    low_eval = eval_ret(low_trades)
    low_ci = bootstrap_ci(low_trades, n_boot=1500, block_size=5) if len(low_trades) >= 5 else None
    log.info("LOW regime (pct30<0.30): %s", low_eval)
    if low_ci:
        log.info("  CI: mean=%.1fbp lower=%.1fbp upper=%.1fbp",
                 low_ci["mean"]*10000, low_ci["ci_lower"]*10000, low_ci["ci_upper"]*10000)

    # === MID regime (complement, 0.30-0.70) ===
    mid_mask = (regime >= 0.30) & (regime <= 0.70)
    mid_trades = build_pooled_trades(mid_mask, btc_sign, alt_hourly, hold_h, dir_continuation)
    mid_eval = eval_ret(mid_trades)
    mid_ci = bootstrap_ci(mid_trades, n_boot=1500, block_size=5) if len(mid_trades) >= 5 else None
    log.info("MID regime (0.30-0.70): %s", mid_eval)
    if mid_ci:
        log.info("  CI: mean=%.1fbp lower=%.1fbp upper=%.1fbp",
                 mid_ci["mean"]*10000, mid_ci["ci_lower"]*10000, mid_ci["ci_upper"]*10000)

    # Two-sample test: HIGH vs BASELINE. Is HIGH significantly better?
    def welch_t(a, b):
        a = np.array(a); b = np.array(b)
        ma, mb = a.mean(), b.mean()
        va = a.var(ddof=1); vb = b.var(ddof=1)
        na, nb = len(a), len(b)
        se = np.sqrt(va/na + vb/nb)
        return (ma - mb) / se if se > 0 else 0.0

    t_high_vs_base = welch_t(high_trades, baseline_trades)
    t_low_vs_base = welch_t(low_trades, baseline_trades)
    t_high_vs_mid = welch_t(high_trades, mid_trades)
    t_low_vs_mid = welch_t(low_trades, mid_trades)
    log.info("INCREMENTAL VALUE OF REGIME FILTER (Welch t-stat vs baseline):")
    log.info("  HIGH vs baseline: %.2f", t_high_vs_base)
    log.info("  LOW  vs baseline: %.2f", t_low_vs_base)
    log.info("  HIGH vs MID:      %.2f", t_high_vs_mid)
    log.info("  LOW  vs MID:      %.2f", t_low_vs_mid)

    out = {
        "paradigm": PARADIGM,
        "test": "baseline_incremental_value_of_regime_filter",
        "hold_h": hold_h,
        "baseline_no_filter": {**baseline_eval,
                               **({"ci_lower_bp": round(baseline_ci["ci_lower"]*10000, 2),
                                   "ci_upper_bp": round(baseline_ci["ci_upper"]*10000, 2)} if baseline_ci else {})},
        "high_regime": {**high_eval,
                        **({"ci_lower_bp": round(high_ci["ci_lower"]*10000, 2),
                            "ci_upper_bp": round(high_ci["ci_upper"]*10000, 2)} if high_ci else {})},
        "low_regime": {**low_eval,
                       **({"ci_lower_bp": round(low_ci["ci_lower"]*10000, 2),
                           "ci_upper_bp": round(low_ci["ci_upper"]*10000, 2)} if low_ci else {})},
        "mid_regime": {**mid_eval,
                       **({"ci_lower_bp": round(mid_ci["ci_lower"]*10000, 2),
                           "ci_upper_bp": round(mid_ci["ci_upper"]*10000, 2)} if mid_ci else {})},
        "welch_t_high_vs_baseline": round(float(t_high_vs_base), 3),
        "welch_t_low_vs_baseline": round(float(t_low_vs_base), 3),
        "welch_t_high_vs_mid": round(float(t_high_vs_mid), 3),
        "welch_t_low_vs_mid": round(float(t_low_vs_mid), 3),
        "interpretation": {
            "if_baseline_positive": "BTC-sign daily momentum is the driver; on-chain filter is decoration",
            "if_high_much_greater_than_baseline": "on-chain HIGH regime adds edge (mechanism confirmed)",
            "if_welch_t_less_than_2": "on-chain filter is NOT statistically incremental (Lesson #32 baseline-coherent drift or Lesson #21 axis stacking)"
        },
    }

    (OUT_DIR / "r1_baseline_diagnostic.json").write_text(json.dumps(out, indent=2))
    log.info("wrote r1_baseline_diagnostic.json")


if __name__ == "__main__":
    main()
