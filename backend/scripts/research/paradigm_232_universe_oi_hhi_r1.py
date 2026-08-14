"""R-1 PoC — Paradigm 232: Universe-scalar OI HHI concentration regime bilateral 24h directional.

DNA: universe-level daily HHI = Σ((OI_value_i / Σ OI_value_j)^2) computed across ~55 Binance USDT-M perps
     → 90d rolling percentile rank → HIGH (pct_rank>=0.70) vs LOW (pct_rank<=0.30) bilateral regime trigger
     → forward return on 14-alt equal-weight cohort measured at t+H (1d, 3d, 5d).

Novel: both trigger axes non-OHLCV (HHI level + regime membership). Escapes Lesson #77
       corollary + Lesson #39 sub-class A that graveyarded paradigm 231 (launchpool bar-direction).

Universe:
- HHI computed over 55 syms with full OI cache coverage 2024-11-07 to 2026-05-01
- Forward return measured on 14-alt cohort: BTC/ETH/SOL/XRP/DOGE/ADA/AVAX/BNB/LINK/LTC/BCH/FIL/NEAR/WIF

4-quadrant SNT:
- A_focus  = HHI HIGH (pct_rank>=0.70) × SHORT (crowding-risk reversal hypothesis)
- A_mirror = HHI HIGH (pct_rank>=0.70) × LONG   (mirror)
- B_focus  = HHI LOW  (pct_rank<=0.30) × LONG   (dispersed-market continuation)
- B_mirror = HHI LOW  (pct_rank<=0.30) × SHORT  (mirror)

Sweep: pct_rank ∈ {0.65, 0.70, 0.75, 0.80} × hold ∈ {1d, 3d, 5d}
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paradigm_232_r1")

REPO = Path(__file__).resolve().parents[3]
OI_CACHE = REPO / "backend/runs/microstructure/cache"
OHLCV_CACHE = REPO / "backend/runs/ohlcv_cache"

# 14-alt forward return cohort
COHORT_SYMS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "BNBUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "FILUSDT", "NEARUSDT", "WIFUSDT",
]

FEE_BPS = 8.0  # round-trip
FEE_FRAC = FEE_BPS / 10000.0

# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

def list_hhi_universe() -> List[str]:
    """55 syms with full OI cache coverage."""
    syms = sorted(set(f.name.split("__")[0] for f in OI_CACHE.glob("*.joblib")))
    good = []
    target_first = "2024-11-07"
    target_last = "2026-05-01"
    for s in syms:
        files = sorted(OI_CACHE.glob(f"{s}__*.joblib"))
        if not files:
            continue
        first_d = files[0].name.split("__")[1].replace(".joblib", "")
        last_d = files[-1].name.split("__")[1].replace(".joblib", "")
        if first_d <= target_first and last_d >= target_last and len(files) >= 530:
            good.append(s)
    return good


def load_oi_value_daily(sym: str) -> pd.Series:
    files = sorted(OI_CACHE.glob(f"{sym}__*.joblib"))
    dfs = []
    for f in files:
        try:
            df = joblib.load(f)
            if "open_interest_value_usdt" in df.columns:
                dfs.append(df[["open_interest_value_usdt"]])
        except Exception as e:
            log.debug("load fail %s: %s", f.name, e)
    if not dfs:
        return pd.Series(dtype=float)
    combined = pd.concat(dfs).sort_index()
    combined.index = pd.to_datetime(combined.index, utc=True)
    # daily last snapshot (00:00 UTC of next day)
    daily = combined["open_interest_value_usdt"].resample("1D").last().dropna()
    return daily


def load_cohort_ohlcv_daily(sym: str) -> pd.DataFrame:
    """Load 1m joblib, resample to daily UTC bars."""
    p = OHLCV_CACHE / f"{sym}_1m.joblib"
    if not p.exists():
        return pd.DataFrame()
    df = joblib.load(p)
    if df.empty:
        return pd.DataFrame()
    # Index is naive UTC per inspection
    df = df.copy()
    if df.index.tz is None:
        df.index = pd.to_datetime(df.index).tz_localize("UTC")
    else:
        df.index = pd.to_datetime(df.index).tz_convert("UTC")
    daily = pd.DataFrame({
        "open":   df["open"].resample("1D").first(),
        "high":   df["high"].resample("1D").max(),
        "low":    df["low"].resample("1D").min(),
        "close":  df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()
    return daily


# ----------------------------------------------------------------------------
# HHI signal construction
# ----------------------------------------------------------------------------

def build_universe_hhi(syms: List[str], pct_window: int = 90) -> pd.DataFrame:
    """Return DataFrame with columns: hhi_raw, hhi_pct_rank (90d rolling)."""
    log.info("Loading OI daily for %d syms for HHI computation...", len(syms))
    series = {}
    for s in syms:
        ts = load_oi_value_daily(s)
        if not ts.empty:
            series[s] = ts
    oi_df = pd.DataFrame(series)
    # Only rows where at least 40 syms have OI (ensure meaningful HHI)
    n_active = oi_df.notna().sum(axis=1)
    valid_rows = n_active >= 40
    oi_df = oi_df.loc[valid_rows]
    log.info("OI matrix shape %s (after filter n_active>=40), range %s to %s",
             oi_df.shape, oi_df.index.min().date(), oi_df.index.max().date())

    # Per-day HHI: fillna(0) on missing syms then compute
    oi_filled = oi_df.fillna(0)
    denom = oi_filled.sum(axis=1)
    shares = oi_filled.div(denom, axis=0)
    hhi = (shares ** 2).sum(axis=1)

    # 90d rolling percentile rank of HHI
    def _pct_rank(x):
        # last value's rank among the window
        s = pd.Series(x)
        return (s.rank(method="min").iloc[-1] - 1) / max(len(s) - 1, 1)

    pct_rank = hhi.rolling(pct_window).apply(_pct_rank, raw=False)
    return pd.DataFrame({"hhi_raw": hhi, "hhi_pct_rank": pct_rank}).dropna()


# ----------------------------------------------------------------------------
# Cohort forward-return backtest
# ----------------------------------------------------------------------------

def compute_cohort_forward_returns(hold_days: int) -> pd.DataFrame:
    """Return DataFrame indexed by day, columns=cohort syms, values=fwd_return."""
    frames = {}
    for sym in COHORT_SYMS:
        d = load_cohort_ohlcv_daily(sym)
        if d.empty:
            log.warning("no OHLCV for %s", sym)
            continue
        d["fwd"] = d["close"].shift(-hold_days) / d["close"] - 1
        frames[sym] = d["fwd"].dropna()
    return pd.DataFrame(frames)


def evaluate_quadrant(
    fwd_ret: pd.DataFrame,
    signal_mask: pd.Series,   # bool Series indexed by date
    side: int,                # +1 long / -1 short
    tag: str,
) -> dict:
    """
    Given a boolean regime mask + trade side, compute:
    - n (trades = regime_days x cohort_syms)
    - mean/std_bp of net returns per (day, sym)
    - block bootstrap CI (block by day since regime-days autocorrelated)
    - fee-aware perm test using cohort's full fwd_ret pool
    - three-gate verdict
    - per-quarter t-stat breakdown
    - per-sym CI positivity
    """
    signal_days = signal_mask[signal_mask].index
    if len(signal_days) < 5:
        return {"tag": tag, "n": 0, "error": "insufficient_regime_days", "n_days": len(signal_days)}

    aligned = fwd_ret.loc[fwd_ret.index.isin(signal_days)]
    if aligned.empty:
        return {"tag": tag, "n": 0, "error": "no_aligned_returns"}

    # Stack to (day, sym) tuples
    stacked = aligned.stack().dropna()
    if len(stacked) < 30:
        return {"tag": tag, "n": int(len(stacked)), "error": "n<30"}

    # Net per-trade returns
    gross = stacked.values.astype(float)
    net = side * gross - FEE_FRAC
    net_bps = net * 10000

    # Block bootstrap by day (aggregate rows per day into blocks)
    # Since observations are per-(day,sym) and same-day rows share regime, use block=cohort_size ~14
    boot = bootstrap_ci(net, n_boot=2000, block_size=len(COHORT_SYMS))

    # Perm test: candidate pool = all cohort fwd returns (not just regime days)
    pool_gross = fwd_ret.stack().dropna().values.astype(float)
    pool_side = side * pool_gross
    perm = fee_aware_perm_test(
        observed_net_returns=net,
        candidate_pool_returns=pool_side,
        fee_per_trade=FEE_FRAC,
        n_perms=500,
        rng_seed=42,
    )

    sigex = perm.get("signal_t_excess")
    ci_lo_bp = float(boot["ci_lower"] * 10000)
    ci_hi_bp = float(boot["ci_upper"] * 10000)
    pp = perm.get("perm_p_one_sided_above") if side > 0 else perm.get("perm_p_one_sided_below")

    three_gate = bool(
        sigex is not None and not np.isnan(sigex) and sigex >= 2.0
        and ci_lo_bp > 0
        and pp is not None and not np.isnan(pp) and pp <= 0.10
    )

    # Per-quarter t-stat (rows indexed by day)
    day_index = pd.MultiIndex.from_tuples(stacked.index)
    df_out = pd.DataFrame({"net_bp": net_bps}, index=day_index)
    df_out.index.names = ["day", "sym"]
    df_out = df_out.reset_index()
    df_out["day"] = pd.to_datetime(df_out["day"])
    df_out["quarter"] = df_out["day"].dt.to_period("Q").astype(str)
    q_stats = {}
    for q, g in df_out.groupby("quarter"):
        arr = g["net_bp"].values
        if len(arr) < 5:
            q_stats[q] = {"n": int(len(arr)), "t": None}
            continue
        std = arr.std(ddof=1)
        t = arr.mean() / (std / np.sqrt(len(arr))) if std > 0 else None
        q_stats[q] = {
            "n": int(len(arr)),
            "mean_bp": float(arr.mean()),
            "t": float(t) if t is not None else None,
        }

    # Per-sym CI
    per_sym = {}
    for sym in COHORT_SYMS:
        sub = df_out[df_out["sym"] == sym]
        if len(sub) < 10:
            per_sym[sym] = {"n": int(len(sub)), "mean_bp": None, "ci_lower_bp": None, "ci_pos": False}
            continue
        arr = sub["net_bp"].values / 10000  # back to fraction for bootstrap_ci input
        b = bootstrap_ci(arr, n_boot=1000, block_size=1)
        cl = float(b["ci_lower"] * 10000)
        per_sym[sym] = {
            "n": int(len(sub)),
            "mean_bp": float(arr.mean() * 10000),
            "ci_lower_bp": cl,
            "ci_upper_bp": float(b["ci_upper"] * 10000),
            "ci_pos": bool(cl > 0),
        }

    n_syms_measured = sum(1 for v in per_sym.values() if v["ci_lower_bp"] is not None)
    n_syms_ci_pos = sum(1 for v in per_sym.values() if v["ci_pos"])
    n_q_measured = sum(1 for v in q_stats.values() if v["t"] is not None)
    n_q_pos = sum(1 for v in q_stats.values() if v["t"] is not None and v["t"] > 0)
    q_pos_ratio = n_q_pos / n_q_measured if n_q_measured else None

    # Concentration gate (Lesson #16)
    concentration_pass = bool(
        q_pos_ratio is not None and q_pos_ratio >= 0.5
        and n_syms_measured > 0 and (n_syms_ci_pos / n_syms_measured) >= 0.30
        and n_syms_ci_pos >= 3
    )

    return {
        "tag": tag,
        "n": int(len(net)),
        "n_regime_days": int(len(signal_days)),
        "mean_bp": float(net_bps.mean()),
        "std_bp": float(net_bps.std(ddof=1)),
        "obs_t": float(perm.get("obs_t", 0)),
        "signal_t_excess": float(sigex) if sigex is not None and not np.isnan(sigex) else None,
        "null_mean_t": float(perm.get("null_mean_t", 0)),
        "ci_lower_bp": ci_lo_bp,
        "ci_upper_bp": ci_hi_bp,
        "perm_p_one_sided": float(pp) if pp is not None else None,
        "three_gate_pass": three_gate,
        "quarter_stats": q_stats,
        "quarter_pos_t_ratio": float(q_pos_ratio) if q_pos_ratio is not None else None,
        "per_sym": per_sym,
        "n_syms_ci_pos": n_syms_ci_pos,
        "n_syms_measured": n_syms_measured,
        "sym_ci_pos_ratio": float(n_syms_ci_pos / n_syms_measured) if n_syms_measured else None,
        "concentration_gate_pass": concentration_pass,
        "n_pool": int(len(pool_gross)),
    }


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct-thresh", type=float, default=0.70, help="HIGH threshold (LOW=1-pct)")
    ap.add_argument("--hold-days", type=int, default=1)
    ap.add_argument("--tag", default="r1_baseline")
    ap.add_argument("--out-dir", default="backend/runs/research_track/paradigm_232_alt_binance_universe_oi_herfindahl_concentration_regime_daily_bilateral")
    args = ap.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== Paradigm 232 R-1 %s (pct_thresh=%.2f, hold=%dd) ===",
             args.tag, args.pct_thresh, args.hold_days)

    # 1. Build universe HHI
    hhi_universe = list_hhi_universe()
    log.info("HHI universe: %d syms", len(hhi_universe))
    hhi_df = build_universe_hhi(hhi_universe, pct_window=90)
    log.info("HHI series: %d days, hhi_raw range [%.4f, %.4f], mean=%.4f",
             len(hhi_df), hhi_df["hhi_raw"].min(), hhi_df["hhi_raw"].max(),
             hhi_df["hhi_raw"].mean())

    # 2. Build regime masks
    pct_hi = args.pct_thresh
    pct_lo = 1.0 - args.pct_thresh
    high_mask = hhi_df["hhi_pct_rank"] >= pct_hi
    low_mask = hhi_df["hhi_pct_rank"] <= pct_lo
    log.info("HIGH regime: %d days (%.1f%%), LOW regime: %d days (%.1f%%)",
             high_mask.sum(), 100.0 * high_mask.mean(),
             low_mask.sum(), 100.0 * low_mask.mean())

    # 3. Cohort forward returns
    fwd_ret = compute_cohort_forward_returns(args.hold_days)
    log.info("cohort fwd_ret: %d days x %d syms",
             len(fwd_ret), fwd_ret.shape[1])

    # Align to HHI dates (both naive/UTC daily). Ensure UTC.
    fwd_ret.index = pd.to_datetime(fwd_ret.index)
    if fwd_ret.index.tz is None:
        fwd_ret.index = fwd_ret.index.tz_localize("UTC")
    else:
        fwd_ret.index = fwd_ret.index.tz_convert("UTC")
    hhi_df.index = pd.to_datetime(hhi_df.index)
    if hhi_df.index.tz is None:
        hhi_df.index = hhi_df.index.tz_localize("UTC")
    else:
        hhi_df.index = hhi_df.index.tz_convert("UTC")
    # Normalize to date only for join
    fwd_ret.index = fwd_ret.index.normalize()
    hhi_df.index = hhi_df.index.normalize()

    # regime masks -> reindex to fwd_ret dates
    high_mask = hhi_df["hhi_pct_rank"] >= pct_hi
    low_mask = hhi_df["hhi_pct_rank"] <= pct_lo

    # 4. Evaluate 4 quadrants
    log.info("--- Evaluating 4 quadrants ---")
    A_focus  = evaluate_quadrant(fwd_ret, high_mask, side=-1, tag="A_focus_HIGH_SHORT")
    A_mirror = evaluate_quadrant(fwd_ret, high_mask, side=+1, tag="A_mirror_HIGH_LONG")
    B_focus  = evaluate_quadrant(fwd_ret, low_mask,  side=+1, tag="B_focus_LOW_LONG")
    B_mirror = evaluate_quadrant(fwd_ret, low_mask,  side=-1, tag="B_mirror_LOW_SHORT")

    summary = {
        "paradigm": "paradigm_232_alt_binance_universe_oi_herfindahl_concentration_regime_daily_bilateral",
        "phase": "R-1",
        "tag": args.tag,
        "pct_thresh_hi": pct_hi,
        "pct_thresh_lo": pct_lo,
        "hold_days": args.hold_days,
        "fee_bps": FEE_BPS,
        "hhi_universe_n": len(hhi_universe),
        "hhi_universe": hhi_universe,
        "cohort": COHORT_SYMS,
        "hhi_range": [float(hhi_df["hhi_raw"].min()), float(hhi_df["hhi_raw"].max())],
        "hhi_mean": float(hhi_df["hhi_raw"].mean()),
        "n_days_hhi": int(len(hhi_df)),
        "n_high_days": int(high_mask.sum()),
        "n_low_days": int(low_mask.sum()),
        "quadrants": {
            "A_focus_HIGH_SHORT": A_focus,
            "A_mirror_HIGH_LONG": A_mirror,
            "B_focus_LOW_LONG": B_focus,
            "B_mirror_LOW_SHORT": B_mirror,
        },
    }

    # Verdict: PASS if any focus quadrant passes both three-gate AND concentration
    verdicts = {}
    for qname, q in summary["quadrants"].items():
        verdicts[qname] = {
            "three_gate_pass": q.get("three_gate_pass", False),
            "concentration_gate_pass": q.get("concentration_gate_pass", False),
            "full_pass": q.get("three_gate_pass", False) and q.get("concentration_gate_pass", False),
        }
    summary["verdicts"] = verdicts

    # Lesson #39 mirror check: A_focus vs A_mirror sum ~ -2*fee => sub-class A
    def _sum_check(q1, q2):
        m1 = q1.get("mean_bp"); m2 = q2.get("mean_bp")
        if m1 is None or m2 is None:
            return None
        return {"m1_bp": m1, "m2_bp": m2, "sum_bp": m1 + m2,
                "expected_sub_class_A_bp": -2 * FEE_BPS}
    summary["lesson39_A_mirror_check"] = _sum_check(A_focus, A_mirror)
    summary["lesson39_B_mirror_check"] = _sum_check(B_focus, B_mirror)

    # Save
    out_file = out_dir / f"{args.tag}__metrics.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info("Wrote %s", out_file)

    # Print concise verdict
    print("\n=== R-1 SUMMARY ===")
    print(f"tag={args.tag}, pct_thresh HI={pct_hi} LO={pct_lo}, hold={args.hold_days}d")
    print(f"HHI universe n={len(hhi_universe)}, HHI range [{summary['hhi_range'][0]:.4f},{summary['hhi_range'][1]:.4f}] mean={summary['hhi_mean']:.4f}")
    print(f"HIGH days={summary['n_high_days']}, LOW days={summary['n_low_days']}")
    print(f"\nLesson #39 A mirror check: {summary['lesson39_A_mirror_check']}")
    print(f"Lesson #39 B mirror check: {summary['lesson39_B_mirror_check']}")
    for qname, q in summary["quadrants"].items():
        if q.get("error"):
            print(f"\n[{qname}] ERROR: {q['error']}")
            continue
        print(f"\n[{qname}] n={q['n']} (regime_days={q['n_regime_days']})")
        print(f"    mean={q['mean_bp']:.2f}bp, obs_t={q['obs_t']:.2f}, sigex={q['signal_t_excess']}, "
              f"ci=[{q['ci_lower_bp']:.2f},{q['ci_upper_bp']:.2f}]bp, perm_p={q['perm_p_one_sided']}")
        print(f"    3gate={q['three_gate_pass']}, conc_gate={q['concentration_gate_pass']} "
              f"(syms_ci_pos={q['n_syms_ci_pos']}/{q['n_syms_measured']}, q_pos_t_ratio={q['quarter_pos_t_ratio']})")


if __name__ == "__main__":
    main()
