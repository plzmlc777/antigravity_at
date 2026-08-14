"""R-1 PoC — Paradigm 228: cross-sym OI share composition shift bilateral 24h directional.

DNA: per-sym OI-value fraction of universe total → 30d rolling z-score →
     |z|>=T bilateral trigger × bar direction × directional 24h hold.

Universe: 7 syms (substrate-limited): HBAR, LINK, AVAX, SOL, DOGE, ETH, NEAR.
Substrate: microstructure 5m OI cache aggregated to daily; 1h klines → daily bars.

Outputs (mandatory per architect protocol):
- 4-quadrant SNT: A_focus / A_mirror / B_focus / B_mirror per sym
- Three-gate: signal_t_excess>=2.0, ci_lower>0, perm_p<=0.10 (Lesson #16 concentration overlay)
- Per-sym bootstrap CI + per-quarter t breakdown
- Era stratification 2024H1/2024H2/2025H1/2025H2/2026H1 (Lesson #46 P1 audit)
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
log = logging.getLogger("paradigm_228_r1")

REPO = Path(__file__).resolve().parents[3]
OI_CACHE = REPO / "backend/runs/microstructure/cache"
KLINE_CACHE = REPO / "backend/runs/research_track/intraday_hour_of_day_anchor_alt_directional_2h/klines_cache"

TARGET_SYMS = [
    "HBARUSDT", "LINKUSDT", "AVAXUSDT", "SOLUSDT",
    "DOGEUSDT", "ETHUSDT", "NEARUSDT",
]

FEE_BPS = 8.0  # round-trip
FEE_FRAC = FEE_BPS / 10000.0

# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

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
    # Resample 1h → 1d: open=first, high=max, low=min, close=last, volume=sum
    daily = pd.DataFrame({
        "open": combined["open"].resample("1D").first(),
        "high": combined["high"].resample("1D").max(),
        "low": combined["low"].resample("1D").min(),
        "close": combined["close"].resample("1D").last(),
        "volume": combined["volume"].resample("1D").sum(),
    }).dropna()
    return daily


# ----------------------------------------------------------------------------
# Signal construction
# ----------------------------------------------------------------------------

def build_oi_share_z(syms: List[str], window: int = 30) -> pd.DataFrame:
    """Return DataFrame of rolling z-score of OI share per sym."""
    log.info("Loading OI daily for %d syms...", len(syms))
    series = {}
    for s in syms:
        ts = load_oi_value_daily(s)
        if not ts.empty:
            series[s] = ts
            log.info("  %s: %d days", s, len(ts))
    oi_df = pd.DataFrame(series).dropna(how="all")
    # Fractions
    denom = oi_df.sum(axis=1)
    oi_frac = oi_df.div(denom, axis=0)
    # 30d rolling z
    rmean = oi_frac.rolling(window).mean()
    rstd = oi_frac.rolling(window).std()
    return (oi_frac - rmean) / (rstd + 1e-12)


# ----------------------------------------------------------------------------
# Backtest — 4-quadrant SNT
# ----------------------------------------------------------------------------

def compute_forward_return(daily: pd.DataFrame, hold_days: int) -> pd.Series:
    """Forward gross return over hold_days: close[t+h]/close[t]-1."""
    return daily["close"].shift(-hold_days) / daily["close"] - 1


def simulate_symbol(
    sym: str,
    oi_z: pd.Series,
    daily: pd.DataFrame,
    z_thresh: float,
    hold_days: int,
) -> Dict[str, dict]:
    """4-quadrant simulate for one symbol. Returns dict quadrant → metrics.

    A_focus: oi_z >= +T × bar UP × LONG  (concentration continuation)
    A_mirror: oi_z >= +T × bar UP × SHORT (mirror)
    B_focus: oi_z <= -T × bar DOWN × SHORT (share exit continuation)
    B_mirror: oi_z <= -T × bar DOWN × LONG (mirror)
    """
    # Align
    df = daily.join(oi_z.rename("oi_z"), how="inner").dropna()
    if len(df) < 200:
        return {"error": "insufficient_align", "n_rows": len(df)}

    df["bar_dir"] = np.sign(df["close"] - df["open"])
    fwd_ret = compute_forward_return(df, hold_days)  # gross fraction
    df["fwd"] = fwd_ret

    # Candidate pool (all valid rows) for perm test
    pool_gross = df["fwd"].dropna().values  # gross returns of all daily windows

    quadrants = {
        "A_focus":  ((df["oi_z"] >= z_thresh) & (df["bar_dir"] > 0), +1),
        "A_mirror": ((df["oi_z"] >= z_thresh) & (df["bar_dir"] > 0), -1),
        "B_focus":  ((df["oi_z"] <= -z_thresh) & (df["bar_dir"] < 0), -1),
        "B_mirror": ((df["oi_z"] <= -z_thresh) & (df["bar_dir"] < 0), +1),
    }

    out = {}
    for qname, (mask, side) in quadrants.items():
        sub = df[mask & df["fwd"].notna()]
        if len(sub) < 10:
            out[qname] = {"n": int(len(sub)), "three_gate_pass": False, "reason": "n<10"}
            continue
        # Net per-trade: side * gross - fee_frac (converted to bps for reporting)
        net = side * sub["fwd"].values - FEE_FRAC
        net_bps = net * 10000

        boot = bootstrap_ci(net, n_boot=2000, block_size=1)

        # Pool for perm: side * pool_gross (direction-adjusted candidate)
        pool_side = side * pool_gross
        perm = fee_aware_perm_test(
            observed_net_returns=net,
            candidate_pool_returns=pool_side,
            fee_per_trade=FEE_FRAC,
            n_perms=500,
            rng_seed=42,
        )

        # Era stratification
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

        # Quarter stratification (calendar quarters)
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
        # perm_p one-sided above for longs, below for shorts
        pp = perm.get("perm_p_one_sided_above") if side > 0 else perm.get("perm_p_one_sided_below")

        # Three-gate: signal_t_excess>=2.0, ci_lower_bp>0, perm_p<=0.10
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


# ----------------------------------------------------------------------------
# Concentration diagnostics — cross-sym
# ----------------------------------------------------------------------------

def concentration_summary(all_results: Dict[str, Dict[str, dict]], quadrant: str) -> dict:
    per_sym = {}
    for sym, quads in all_results.items():
        q = quads.get(quadrant, {})
        if q.get("error"):
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

    # Cross-quarter positivity
    all_q_ts = {}
    for sym, quads in all_results.items():
        q = quads.get(quadrant, {})
        for qtr, stat in q.get("quarter_stats", {}).items():
            if stat.get("t") is not None:
                all_q_ts.setdefault(qtr, []).append(stat["t"])
    quarter_pos_ratio = {}
    for qtr, ts in all_q_ts.items():
        pos = sum(1 for t in ts if t > 0)
        quarter_pos_ratio[qtr] = {"n_syms": len(ts), "pos_ratio": pos / len(ts) if ts else 0}
    # Global quarter-pos-t-ratio (average over quarters of pos share)
    if quarter_pos_ratio:
        global_qpr = np.mean([v["pos_ratio"] for v in quarter_pos_ratio.values()])
    else:
        global_qpr = None

    return {
        "quadrant": quadrant,
        "n_syms_measurable": n_syms,
        "n_ci_pos": n_ci_pos,
        "sym_ci_pos_ratio": n_ci_pos / n_syms if n_syms else 0,
        "n_three_gate_pass": n_three_gate_pass,
        "quarter_pos_t_ratio_avg": float(global_qpr) if global_qpr is not None else None,
        "quarter_breakdown": quarter_pos_ratio,
        "per_sym": per_sym,
        # Concentration verdict per Lesson #16:
        # PASS if quarter_pos_t_ratio_avg >= 0.5 AND sym_ci_pos_ratio >= 0.30 AND n_ci_pos >= 3
        "concentration_gate_pass": bool(
            global_qpr is not None and global_qpr >= 0.5
            and n_syms > 0 and (n_ci_pos / n_syms) >= 0.30
            and n_ci_pos >= 3
        ),
    }


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--z-thresh", type=float, default=1.5)
    ap.add_argument("--hold-days", type=int, default=1)
    ap.add_argument("--tag", default="r1_baseline")
    ap.add_argument("--symbols", nargs="+", default=TARGET_SYMS)
    ap.add_argument("--out-dir", default="backend/runs/research_track/paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h")
    args = ap.parse_args()

    out_dir = REPO / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("=== Paradigm 228 R-1 %s (z=%.2f, hold=%dd) ===",
             args.tag, args.z_thresh, args.hold_days)

    # Build signal
    oi_z_df = build_oi_share_z(args.symbols, window=30)
    log.info("oi_z_df shape %s, range %s to %s",
             oi_z_df.shape, oi_z_df.index.min().date(), oi_z_df.index.max().date())

    # Per-sym simulate
    all_results = {}
    for sym in args.symbols:
        if sym not in oi_z_df.columns:
            log.warning("skip %s (no OI series)", sym)
            continue
        daily = load_kline_daily(sym)
        if daily.empty:
            log.warning("skip %s (no klines)", sym)
            continue
        log.info("simulate %s: %d daily bars", sym, len(daily))
        res = simulate_symbol(sym, oi_z_df[sym], daily, args.z_thresh, args.hold_days)
        all_results[sym] = res

    # Concentration + summaries
    summary = {
        "paradigm": "paradigm_228_alt_cross_sym_oi_share_composition_shift_30d_z_bilateral_directional_24h",
        "phase": "R-1",
        "tag": args.tag,
        "z_thresh": args.z_thresh,
        "hold_days": args.hold_days,
        "fee_bps": FEE_BPS,
        "universe": args.symbols,
        "n_syms_used": len([s for s in all_results if not all_results[s].get("error")]),
        "per_sym_quadrants": all_results,
        "concentration": {
            q: concentration_summary(all_results, q)
            for q in ["A_focus", "A_mirror", "B_focus", "B_mirror"]
        },
    }

    # Save
    out_file = out_dir / f"{args.tag}__metrics.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info("Wrote %s", out_file)

    # Print concise verdict
    print("\n=== R-1 SUMMARY ===")
    print(f"tag={args.tag}, z={args.z_thresh}, hold={args.hold_days}d, n_syms={summary['n_syms_used']}")
    for q, c in summary["concentration"].items():
        print(f"\n[{q}] n_syms={c['n_syms_measurable']}, ci_pos={c['n_ci_pos']}/{c['n_syms_measurable']} "
              f"({c['sym_ci_pos_ratio']*100:.0f}%), 3gate_pass={c['n_three_gate_pass']}, "
              f"quarter_pos_t={c['quarter_pos_t_ratio_avg']}, "
              f"CONCENTRATION_GATE={'PASS' if c['concentration_gate_pass'] else 'FAIL'}")
        for sym, per in c["per_sym"].items():
            gate = "PASS" if per["three_gate_pass"] else "fail"
            _mb = per['mean_bp']; _ot = per['obs_t']; _cl = per['ci_lower_bp']
            _mb_s = f"{_mb:.1f}" if _mb is not None else 'N/A'
            _ot_s = f"{_ot:.2f}" if _ot is not None else 'N/A'
            _cl_s = f"{_cl:.1f}" if _cl is not None else 'N/A'
            print(f"    {sym}: n={per['n']}, mean={_mb_s}bp, "
                  f"obs_t={_ot_s}, ci_lo={_cl_s}bp [{gate}]")


if __name__ == "__main__":
    main()
