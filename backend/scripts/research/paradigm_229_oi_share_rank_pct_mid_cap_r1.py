"""R-1 PoC — Paradigm 229: cross-sym OI share rolling PERCENTILE RANK, mid-cap universe, bilateral directional 24h.

DNA (distinct from paradigm 228):
    - Substrate: microstructure 5m open_interest_value_usdt aggregated daily
    - Universe: MID-CAP only (HBAR, LINK, AVAX, DOGE, NEAR) — no ETH/SOL/BTC mega-caps
      (paradigm 228 lesson: mega-cap normalization noise dominates share-fraction denominator)
    - Signal: per-sym OI-share = sym_OI_value / sum(mid_cap_OI_value)
              7d change in that share
              90d rolling percentile rank (BOUNDED [0,1], no threshold feasibility problem — Lesson #40)
    - Trigger: pct_rank > 0.95 (concentration surge)   OR  pct_rank < 0.05 (concentration exit)
    - Bar direction: sign(close - open) of the daily bar containing the trigger
    - Hold: 24h (1 day) primary, sweep also 12h/36h/48h in later phases

4-quadrant Symmetric Negative Test (Lesson #19 mandatory for joint-trigger):
    A_focus:  pct_rank > 0.95 & bar_up  → LONG  (concentration continuation)
    A_mirror: pct_rank > 0.95 & bar_up  → SHORT
    B_focus:  pct_rank < 0.05 & bar_dn  → SHORT (exit continuation)
    B_mirror: pct_rank < 0.05 & bar_dn  → LONG

Three-gate (Lesson #16 elite gate):
    signal_t_excess >= 2.0  AND  ci_lower_bp > 0  AND  perm_p_one_sided <= 0.10

Concentration gate:
    quarter_pos_t_ratio_avg >= 0.5 AND sym_ci_pos_ratio >= 0.30 AND n_ci_pos >= 2 (adjusted for 5-sym universe)

Era stratify: 2024H1/2024H2/2025H1/2025H2/2026H1 (Pattern P1 alpha decay).
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
log = logging.getLogger("paradigm_229_r1")

REPO = Path(__file__).resolve().parents[3]
OI_CACHE = REPO / "backend/runs/microstructure/cache"
KLINE_CACHE = REPO / "backend/runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/klines_cache"

# Mid-cap universe (both OI substrate AND kline cache present).
# Excluded ETH/SOL/BTC (mega-caps >15% share) per hypothesis design.
# LDO/AXS/COMP/ETC excluded because no 1h kline cache in klines_cache directory.
TARGET_SYMS = [
    "HBARUSDT", "LINKUSDT", "AVAXUSDT", "DOGEUSDT", "NEARUSDT",
]

FEE_BPS = 8.0  # round-trip
FEE_FRAC = FEE_BPS / 10000.0

# Signal window params
CHANGE_LOOKBACK_DAYS = 7   # 7-day change in OI share fraction
RANK_WINDOW_DAYS = 90      # 90-day rolling percentile rank


# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

def load_oi_value_daily(sym: str) -> pd.Series:
    """Load per-sym daily-mean OI value (usdt) from 5m microstructure cache."""
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
    # daily last-value snapshot (end-of-day OI value)
    daily = combined["open_interest_value_usdt"].resample("1D").last().dropna()
    return daily


def load_kline_daily(sym: str) -> pd.DataFrame:
    files = sorted(KLINE_CACHE.glob(f"{sym}_1h_*.joblib"))
    if not files:
        return pd.DataFrame()
    dfs = []
    for f in files:
        try:
            df = joblib.load(f)
            dfs.append(df)
        except Exception as e:
            log.debug("kline load fail %s: %s", f.name, e)
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs).sort_index()
    combined.index = pd.to_datetime(combined.index, utc=True)
    combined = combined[~combined.index.duplicated(keep="last")]
    daily = pd.DataFrame({
        "open": combined["open"].resample("1D").first(),
        "high": combined["high"].resample("1D").max(),
        "low": combined["low"].resample("1D").min(),
        "close": combined["close"].resample("1D").last(),
        "volume": combined["volume"].resample("1D").sum(),
    }).dropna()
    return daily


# ----------------------------------------------------------------------------
# Signal construction — PERCENTILE RANK on 7d share-change
# ----------------------------------------------------------------------------

def build_oi_share_rank_pct(
    syms: List[str],
    change_lookback: int = CHANGE_LOOKBACK_DAYS,
    rank_window: int = RANK_WINDOW_DAYS,
) -> pd.DataFrame:
    """Return per-sym DataFrame of 90d rolling percentile rank of 7d share change.

    Output values are in [0, 1]; rank=0.95 means today's 7d share change is
    higher than 95% of the past 90 days (concentration inflow surge).
    """
    log.info("Loading OI daily for %d syms...", len(syms))
    series = {}
    for s in syms:
        ts = load_oi_value_daily(s)
        if not ts.empty:
            series[s] = ts
            log.info("  %s: %d days (%s .. %s)", s, len(ts), ts.index[0].date(), ts.index[-1].date())
    oi_df = pd.DataFrame(series).dropna(how="all")
    # Universe-total-based share fraction
    denom = oi_df.sum(axis=1)
    oi_frac = oi_df.div(denom, axis=0)
    # 7d change of fraction
    change_7d = oi_frac.diff(change_lookback)
    # 90d rolling percentile rank
    rank_pct = change_7d.rolling(rank_window).rank(pct=True)
    return rank_pct


# ----------------------------------------------------------------------------
# Backtest — 4-quadrant SNT
# ----------------------------------------------------------------------------

def compute_forward_return(daily: pd.DataFrame, hold_days: int) -> pd.Series:
    return daily["close"].shift(-hold_days) / daily["close"] - 1


def simulate_symbol(
    sym: str,
    rank_pct: pd.Series,
    daily: pd.DataFrame,
    high_thresh: float,
    low_thresh: float,
    hold_days: int,
) -> Dict[str, dict]:
    df = daily.join(rank_pct.rename("rank_pct"), how="inner").dropna()
    if len(df) < 200:
        return {"error": "insufficient_align", "n_rows": len(df)}

    df["bar_dir"] = np.sign(df["close"] - df["open"])
    fwd_ret = compute_forward_return(df, hold_days)
    df["fwd"] = fwd_ret

    pool_gross = df["fwd"].dropna().values

    quadrants = {
        "A_focus":  ((df["rank_pct"] >= high_thresh) & (df["bar_dir"] > 0), +1),
        "A_mirror": ((df["rank_pct"] >= high_thresh) & (df["bar_dir"] > 0), -1),
        "B_focus":  ((df["rank_pct"] <= low_thresh) & (df["bar_dir"] < 0), -1),
        "B_mirror": ((df["rank_pct"] <= low_thresh) & (df["bar_dir"] < 0), +1),
    }

    out: Dict[str, dict] = {}
    for qname, (mask, side) in quadrants.items():
        sub = df[mask & df["fwd"].notna()]
        if len(sub) < 10:
            out[qname] = {"n": int(len(sub)), "three_gate_pass": False, "reason": "n<10"}
            continue
        net = side * sub["fwd"].values - FEE_FRAC
        net_bps = net * 10000

        boot = bootstrap_ci(net, n_boot=2000, block_size=1)

        pool_side = side * pool_gross
        perm = fee_aware_perm_test(
            observed_net_returns=net,
            candidate_pool_returns=pool_side,
            fee_per_trade=FEE_FRAC,
            n_perms=500,
            rng_seed=42,
        )

        # Era stratify (Pattern P1 alpha-decay probe)
        eras = {
            "2024H1": ("2024-01-01", "2024-06-30"),
            "2024H2": ("2024-07-01", "2024-12-31"),
            "2025H1": ("2025-01-01", "2025-06-30"),
            "2025H2": ("2025-07-01", "2025-12-31"),
            "2026H1": ("2026-01-01", "2026-06-30"),
        }
        era_stats = {}
        for era, (start, end) in eras.items():
            s_utc = pd.Timestamp(start, tz="UTC")
            e_utc = pd.Timestamp(end, tz="UTC")
            sub_era = sub.loc[(sub.index >= s_utc) & (sub.index <= e_utc)]
            if len(sub_era) < 5:
                era_stats[era] = {"n": int(len(sub_era)), "mean_bp": None, "t": None}
                continue
            net_era = (side * sub_era["fwd"].values - FEE_FRAC) * 10000
            t_era = net_era.mean() / (net_era.std(ddof=1) / np.sqrt(len(net_era))) if net_era.std(ddof=1) > 0 else None
            era_stats[era] = {
                "n": int(len(sub_era)),
                "mean_bp": float(net_era.mean()),
                "t": float(t_era) if t_era is not None else None,
            }

        # Quarter stratify (concentration diagnostic)
        sub_q = sub.copy()
        sub_q["net_bp"] = net_bps
        sub_q["quarter"] = sub_q.index.to_period("Q").astype(str)
        q_stats = {}
        for q, g in sub_q.groupby("quarter"):
            arr = g["net_bp"].values
            if len(arr) < 5:
                q_stats[q] = {"n": int(len(arr)), "t": None}
                continue
            t = arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr))) if arr.std(ddof=1) > 0 else None
            q_stats[q] = {"n": int(len(arr)), "mean_bp": float(arr.mean()),
                          "t": float(t) if t is not None else None}

        sigex = perm.get("signal_t_excess")
        ci_lo_bp = boot["ci_lower"] * 10000
        pp = perm.get("perm_p_one_sided_above") if side > 0 else perm.get("perm_p_one_sided_below")

        three_gate = (
            sigex is not None and not np.isnan(sigex) and sigex >= 2.0
            and ci_lo_bp > 0
            and pp is not None and not np.isnan(pp) and pp <= 0.10
        )

        out[qname] = {
            "n": int(len(sub)),
            "mean_bp": float(net_bps.mean()),
            "std_bp": float(net_bps.std(ddof=1)),
            "obs_t": float(perm.get("obs_t", 0)),
            "signal_t_excess": float(sigex) if sigex is not None and not np.isnan(sigex) else None,
            "null_mean_t": float(perm.get("null_mean_t", 0)),
            "ci_lower_bp": float(ci_lo_bp),
            "ci_upper_bp": float(boot["ci_upper"] * 10000),
            "perm_p_one_sided": float(pp) if pp is not None else None,
            "three_gate_pass": bool(three_gate),
            "era_stats": era_stats,
            "quarter_stats": q_stats,
            "n_pool": int(len(pool_gross)),
        }
    return out


def concentration_summary(all_results: Dict[str, Dict[str, dict]], quadrant: str) -> dict:
    per_sym = {}
    for sym, quads in all_results.items():
        q = quads.get(quadrant, {})
        if q.get("error") or "n" not in q or q.get("n", 0) < 10:
            continue
        per_sym[sym] = {
            "n": q.get("n", 0),
            "mean_bp": q.get("mean_bp"),
            "obs_t": q.get("obs_t"),
            "ci_lower_bp": q.get("ci_lower_bp"),
            "ci_pos": q.get("ci_lower_bp", -1) > 0,
            "three_gate_pass": q.get("three_gate_pass", False),
        }
    n_syms = len(per_sym)
    n_ci_pos = sum(1 for v in per_sym.values() if v["ci_pos"])
    n_three_gate_pass = sum(1 for v in per_sym.values() if v["three_gate_pass"])

    all_q_ts: Dict[str, List[float]] = {}
    for sym, quads in all_results.items():
        q = quads.get(quadrant, {})
        for qtr, stat in q.get("quarter_stats", {}).items():
            if stat.get("t") is not None:
                all_q_ts.setdefault(qtr, []).append(stat["t"])
    quarter_pos_ratio = {}
    for qtr, ts in all_q_ts.items():
        pos = sum(1 for t in ts if t > 0)
        quarter_pos_ratio[qtr] = {"n_syms": len(ts), "pos_ratio": pos / len(ts) if ts else 0}
    if quarter_pos_ratio:
        global_qpr = float(np.mean([v["pos_ratio"] for v in quarter_pos_ratio.values()]))
    else:
        global_qpr = None

    # Adjusted concentration gate: 5-sym universe → 30% ci_pos = 2 syms
    return {
        "quadrant": quadrant,
        "n_syms_measurable": n_syms,
        "n_ci_pos": n_ci_pos,
        "sym_ci_pos_ratio": n_ci_pos / n_syms if n_syms else 0,
        "n_three_gate_pass": n_three_gate_pass,
        "quarter_pos_t_ratio_avg": global_qpr,
        "quarter_breakdown": quarter_pos_ratio,
        "per_sym": per_sym,
        "concentration_gate_pass": bool(
            global_qpr is not None and global_qpr >= 0.5
            and n_syms > 0 and (n_ci_pos / n_syms) >= 0.30
            and n_ci_pos >= 2
        ),
    }


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--high-thresh", type=float, default=0.95)
    ap.add_argument("--low-thresh", type=float, default=0.05)
    ap.add_argument("--hold-days", type=int, default=1)
    ap.add_argument("--tag", default="r1_baseline_p95_h1")
    ap.add_argument("--symbols", nargs="+", default=TARGET_SYMS)
    ap.add_argument("--out-dir", default="backend/runs/research_track/paradigm_229_alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h")
    args = ap.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== Paradigm 229 R-1 %s (p_hi=%.2f p_lo=%.2f hold=%dd) ===",
             args.tag, args.high_thresh, args.low_thresh, args.hold_days)
    log.info("Universe: %s", args.symbols)

    rank_pct_df = build_oi_share_rank_pct(args.symbols)
    log.info("Rank-pct panel: %d days x %d syms", len(rank_pct_df), len(rank_pct_df.columns))

    # Empirical trigger density audit (Lesson #34)
    density_stats = {}
    for s in rank_pct_df.columns:
        sv = rank_pct_df[s].dropna()
        n_hi = int((sv >= args.high_thresh).sum())
        n_lo = int((sv <= args.low_thresh).sum())
        density_stats[s] = {
            "n_days": int(len(sv)),
            "n_hi_hits": n_hi,
            "n_lo_hits": n_lo,
            "hi_pct": float(n_hi / len(sv)) if len(sv) else 0.0,
            "lo_pct": float(n_lo / len(sv)) if len(sv) else 0.0,
        }
        log.info("  %s density: n_days=%d hi=%d(%.2f%%) lo=%d(%.2f%%)",
                 s, len(sv), n_hi, 100*n_hi/max(len(sv),1), n_lo, 100*n_lo/max(len(sv),1))

    all_results: Dict[str, Dict[str, dict]] = {}
    for sym in args.symbols:
        log.info("Simulating %s ...", sym)
        if sym not in rank_pct_df.columns:
            all_results[sym] = {"error": "no_oi_data"}
            continue
        daily = load_kline_daily(sym)
        if daily.empty:
            log.warning("  %s: no klines, skip", sym)
            all_results[sym] = {"error": "no_klines"}
            continue
        log.info("  %s klines: %d days (%s..%s)", sym, len(daily), daily.index[0].date(), daily.index[-1].date())
        res = simulate_symbol(
            sym=sym,
            rank_pct=rank_pct_df[sym],
            daily=daily,
            high_thresh=args.high_thresh,
            low_thresh=args.low_thresh,
            hold_days=args.hold_days,
        )
        all_results[sym] = res
        for qn, m in res.items():
            if isinstance(m, dict) and "n" in m:
                log.info("    %s: n=%d mean=%.1fbp sig_t_ex=%s ci_lo=%.1fbp perm_p=%s 3gate=%s",
                         qn, m["n"], m.get("mean_bp", 0),
                         f"{m.get('signal_t_excess'):.2f}" if m.get('signal_t_excess') is not None else "NA",
                         m.get("ci_lower_bp", 0),
                         f"{m.get('perm_p_one_sided'):.3f}" if m.get('perm_p_one_sided') is not None else "NA",
                         m.get("three_gate_pass"))

    # Concentration diagnostics per quadrant
    conc = {}
    for q in ["A_focus", "A_mirror", "B_focus", "B_mirror"]:
        conc[q] = concentration_summary(all_results, q)
        log.info("Concentration %s: n_syms=%d n_ci_pos=%d(%.2f%%) qpr=%s conc_pass=%s",
                 q, conc[q]["n_syms_measurable"], conc[q]["n_ci_pos"],
                 100*conc[q]["sym_ci_pos_ratio"],
                 f"{conc[q]['quarter_pos_t_ratio_avg']:.2f}" if conc[q]["quarter_pos_t_ratio_avg"] is not None else "NA",
                 conc[q]["concentration_gate_pass"])

    metrics = {
        "paradigm_number": 229,
        "paradigm_slug": "alt_cross_sym_oi_share_rank_pct_7d_change_mid_cap_bilateral_directional_24h",
        "phase": "R-1",
        "tag": args.tag,
        "config": {
            "high_thresh": args.high_thresh,
            "low_thresh": args.low_thresh,
            "hold_days": args.hold_days,
            "change_lookback_days": CHANGE_LOOKBACK_DAYS,
            "rank_window_days": RANK_WINDOW_DAYS,
            "fee_bps": FEE_BPS,
            "symbols": args.symbols,
        },
        "trigger_density": density_stats,
        "per_symbol": all_results,
        "concentration": conc,
    }

    out_file = out_dir / f"{args.tag}__metrics.json"
    out_file.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Wrote %s", out_file)

    # Overall PASS verdict
    focus_conc_pass = conc["A_focus"]["concentration_gate_pass"] or conc["B_focus"]["concentration_gate_pass"]
    focus_n_three_gate = conc["A_focus"]["n_three_gate_pass"] + conc["B_focus"]["n_three_gate_pass"]
    log.info("=== SUMMARY: focus_conc_pass=%s focus_n_three_gate=%d ===",
             focus_conc_pass, focus_n_three_gate)


if __name__ == "__main__":
    main()
