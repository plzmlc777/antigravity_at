"""Paradigm 148 R-1: alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h.

Hypothesis
----------
Cross-exchange PRICE lead-lag: Bybit (Asian-retail-dominated venue) PRICE
velocity z[t] leads Binance (global institutional + retail) PRICE velocity
z[t+Δ] at Δ ∈ {15min, 30min, 60min, 120min}. Trigger:

    |Bybit_PRICE_velocity_z[t]| > 2.0

Direction: sign(Bybit_PRICE_velocity_z[t]) → 4h forward LONG/SHORT continuation
on Binance same-symbol perp.

Differentiation vs prior graveyards (Lesson #44 amendment 32nd xref dogfood)
---------------------------------------------------------------------------
- paradigm 71 distinct via cross-exchange (single→cross) AND axis (OI→PRICE)
- paradigm 75 distinct via cross-exchange (cross-symbol within Binance →
  cross-exchange same-symbol Bybit/Binance) — broad PRICE lead-lag class
  proximity STRONG WARNING but substrate composition genuinely different
- paradigm 103 distinct via axis (funding→PRICE)
- paradigm 104 distinct via axis (OI level same-bar→PRICE velocity time-shifted)
- paradigm 147 v2 distinct via axis (OI velocity→PRICE velocity);
  NOT 6th-instance Lesson #56 trap (PRICE velocity z trigger NOT in
  confirmed-falsified family)
- paradigm 81 distinct via mechanism (synchronous correlation regime → time-
  shifted velocity lead-lag)
- Lesson #58 cross-substrate exemption: Bybit klines + Binance klines = 2
  substrates (different exchange API, different liquidity pool, different
  participant base) → Lesson #21 axis-stacking sub-finding EXEMPT
- HMM/unsupervised prohibition (Lesson #45 CONFIRMED): pure parametric z

4-quadrant SNT × Δ sweep (Lesson #19 mandatory, 16 cells one batch)
-------------------------------------------------------------------
For each Δ ∈ {15, 30, 60, 120} min:
  - A focus: Bybit_z > +2.0 × 4h LONG on Binance (positive continuation)
  - A mirror: Bybit_z > +2.0 × 4h SHORT (mean-reversion)
  - B focus: Bybit_z < -2.0 × 4h SHORT (negative continuation)
  - B mirror: Bybit_z < -2.0 × 4h LONG

Three-gate PASS criterion (per cell):
  signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_one_sided_above <= 0.10
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm148_r1")

# ---------------------------- Config ----------------------------
PARADIGM_NAME = "alt_bybit_to_binance_lead_lag_PRICE_delay_directional_4h"
PARADIGM_ID = 148

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]

# Substrate caches (paradigm148_backfill_klines.py output)
CACHE_BYBIT = ROOT / "runs" / "ohlcv_cache_15m" / "bybit_klines"
CACHE_BINANCE = ROOT / "runs" / "ohlcv_cache_15m" / "binance_klines"

OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Frame: 15min bars
FRAME_MIN = 15
# Velocity: 1h velocity = 4 bars
VELOCITY_BARS = 4
# Rolling std window: 30d = 30*96 = 2880 bars
ZSCORE_BARS = 30 * (24 * 60 // FRAME_MIN)  # 2880

# Trigger threshold
Z_THRESHOLD = 2.0

# Lead-lag shifts (in 15min bars)
DELTA_MIN_LIST = [15, 30, 60, 120]
DELTA_BARS_LIST = [d // FRAME_MIN for d in DELTA_MIN_LIST]  # [1,2,4,8]

# Forward hold: 4h = 16 bars (15min)
HOLD_BARS = 4 * 60 // FRAME_MIN  # 16

# Fee
FEE_PER_TRADE = 0.0008  # 8 bp round-trip

# Concentration gate (Lesson #16 STRICT ≥30%)
CONC_QUARTER_POS_T_RATIO_MIN = 0.5
CONC_SYM_CI_POS_RATIO_MIN = 0.30
CONC_N_SYM_CI_POS_MIN = 3


# ------------------------- Helpers -------------------------
def load_klines(cache_dir: Path, sym: str) -> pd.DataFrame:
    path = cache_dir / f"{sym}_15m.joblib"
    if not path.exists():
        raise FileNotFoundError(f"missing cache: {path}")
    df = joblib.load(path)
    df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
    return df


def align_klines(bybit_df: pd.DataFrame, binance_df: pd.DataFrame) -> pd.DataFrame:
    """Outer-join on ts at 15min frame; forward-fill close within ±1 bar tolerance."""
    bb = bybit_df[["ts", "close"]].rename(columns={"close": "bb_close"})
    bn = binance_df[["ts", "close"]].rename(columns={"close": "bn_close"})
    # Floor both to 15min boundary
    bb["ts"] = bb["ts"].dt.floor(f"{FRAME_MIN}min")
    bn["ts"] = bn["ts"].dt.floor(f"{FRAME_MIN}min")
    bb = bb.drop_duplicates(subset=["ts"], keep="last")
    bn = bn.drop_duplicates(subset=["ts"], keep="last")
    df = pd.merge(bb, bn, on="ts", how="inner").sort_values("ts").reset_index(drop=True)
    return df


def compute_velocity_z(close: pd.Series, vel_bars: int, z_bars: int) -> pd.Series:
    """1h velocity (close[t] - close[t-vel_bars]) / 30d rolling std of velocity."""
    velocity = close - close.shift(vel_bars)
    vel_std = velocity.rolling(window=z_bars, min_periods=z_bars // 2).std(ddof=1)
    z = velocity / vel_std
    return z


def compute_forward_return(close: pd.Series, hold_bars: int) -> pd.Series:
    """Forward log return over hold_bars."""
    return (close.shift(-hold_bars) / close - 1.0)


def run_cell(
    aligned: pd.DataFrame,
    sym: str,
    delta_bars: int,
    z_threshold: float,
    direction_sign: int,  # +1 for LONG, -1 for SHORT
    z_filter_sign: int,   # +1 for z>+T, -1 for z<-T
) -> Dict:
    """Run one cell of the 4-quadrant SNT × Δ sweep for a single symbol.

    Trigger: Bybit_z[t] > +T (z_filter_sign=+1) or < -T (z_filter_sign=-1)
    Forward return computed on Binance at t+delta_bars with hold_bars
    Direction sign: +1 LONG, -1 SHORT
    """
    bb_z = compute_velocity_z(aligned["bb_close"], VELOCITY_BARS, ZSCORE_BARS)
    bn_fwd_ret_at_shift = compute_forward_return(aligned["bn_close"], HOLD_BARS).shift(-delta_bars)

    if z_filter_sign > 0:
        trigger_mask = bb_z > z_threshold
    else:
        trigger_mask = bb_z < -z_threshold

    # Drop NaN
    valid = trigger_mask & bn_fwd_ret_at_shift.notna()
    triggered_gross = bn_fwd_ret_at_shift[valid] * direction_sign
    triggered_net = triggered_gross - FEE_PER_TRADE

    # Candidate pool: ALL forward returns (no trigger filter), same hold/shift
    pool_gross = bn_fwd_ret_at_shift[bn_fwd_ret_at_shift.notna()] * direction_sign
    pool_net_for_perm = pool_gross  # _perm_utils applies fee internally

    # Timestamps for quarter stratification
    trigger_ts = aligned.loc[valid.index[valid], "ts"]

    return {
        "sym": sym,
        "n_triggers": int(valid.sum()),
        "n_pool": int(bn_fwd_ret_at_shift.notna().sum()),
        "obs_net_returns": triggered_net.values.tolist(),
        "obs_trigger_ts": [str(t) for t in trigger_ts.values],
        "pool_gross_returns": pool_gross.values.tolist(),
    }


def aggregate_cell_results(per_sym_results: List[Dict], cell_label: str) -> Dict:
    """Pool across symbols, run 3-gate stats + concentration."""
    all_obs = []
    all_pool = []
    all_trigger_ts = []
    per_sym_summary = []

    for r in per_sym_results:
        all_obs.extend(r["obs_net_returns"])
        all_pool.extend(r["pool_gross_returns"])
        all_trigger_ts.extend(r["obs_trigger_ts"])

        # Per-symbol bootstrap CI (Concentration check)
        if len(r["obs_net_returns"]) >= 10:
            sym_ci = bootstrap_ci(r["obs_net_returns"], n_boot=1000, block_size=1)
            per_sym_summary.append({
                "sym": r["sym"],
                "n": r["n_triggers"],
                "mean_bp": sym_ci["mean"] * 1e4,
                "ci_lower_bp": sym_ci["ci_lower"] * 1e4,
                "ci_pos": bool(sym_ci["ci_lower"] > 0),
            })
        else:
            per_sym_summary.append({
                "sym": r["sym"],
                "n": r["n_triggers"],
                "mean_bp": float("nan"),
                "ci_lower_bp": float("nan"),
                "ci_pos": False,
            })

    n_obs = len(all_obs)
    n_pool = len(all_pool)

    if n_obs < 30:
        return {
            "cell": cell_label,
            "verdict": "SAMPLE_INSUFFICIENT",
            "n_obs": n_obs,
            "n_pool": n_pool,
            "per_sym_summary": per_sym_summary,
        }

    # 3-gate stats
    perm = fee_aware_perm_test(all_obs, all_pool, fee_per_trade=FEE_PER_TRADE,
                                n_perms=1000)
    boot = bootstrap_ci(all_obs, n_boot=2000, block_size=1)

    # Quarter stratification
    df_obs = pd.DataFrame({"ret": all_obs, "ts": pd.to_datetime(all_trigger_ts)})
    df_obs["quarter"] = df_obs["ts"].dt.to_period("Q").astype(str)
    quarter_stats = {}
    for q, grp in df_obs.groupby("quarter"):
        if len(grp) >= 5:
            arr = grp["ret"].values
            if arr.std(ddof=1) > 0:
                qt = arr.mean() / arr.std(ddof=1) * np.sqrt(len(arr))
            else:
                qt = 0.0
            quarter_stats[q] = {"n": len(grp), "mean_bp": float(arr.mean() * 1e4), "t": float(qt)}

    n_q_measurable = len(quarter_stats)
    n_q_pos_t = sum(1 for s in quarter_stats.values() if s["t"] > 0)
    quarter_pos_t_ratio = n_q_pos_t / n_q_measurable if n_q_measurable else 0.0

    n_sym_measurable = sum(1 for s in per_sym_summary if not np.isnan(s.get("ci_lower_bp", float("nan"))))
    n_sym_ci_pos = sum(1 for s in per_sym_summary if s.get("ci_pos", False))
    symbol_ci_pos_ratio = n_sym_ci_pos / n_sym_measurable if n_sym_measurable else 0.0

    # 3-gate
    gate_sigex = perm.get("signal_t_excess", float("nan")) >= 2.0
    gate_ci = boot.get("ci_lower", float("nan")) > 0
    gate_perm = perm.get("perm_p_one_sided_above", float("nan")) <= 0.10
    gates_pass = bool(gate_sigex and gate_ci and gate_perm)

    # Concentration
    conc_pass = (
        quarter_pos_t_ratio >= CONC_QUARTER_POS_T_RATIO_MIN
        and symbol_ci_pos_ratio >= CONC_SYM_CI_POS_RATIO_MIN
        and n_sym_ci_pos >= CONC_N_SYM_CI_POS_MIN
    )

    if gates_pass and conc_pass:
        verdict = "PASS_R1_FULL"
    elif gates_pass and not conc_pass:
        verdict = "CONCENTRATED_R1_PASS"
    else:
        verdict = "FAIL"

    return {
        "cell": cell_label,
        "verdict": verdict,
        "n_obs": n_obs,
        "n_pool": n_pool,
        "obs_mean_bp": float(perm.get("obs_mean", 0.0)) * 1e4,
        "obs_t": float(perm.get("obs_t", 0.0)),
        "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
        "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
        "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
        "ci_lower_bp": float(boot.get("ci_lower", float("nan"))) * 1e4,
        "ci_upper_bp": float(boot.get("ci_upper", float("nan"))) * 1e4,
        "prob_positive": float(boot.get("prob_positive", float("nan"))),
        "gates": {"sigex_ge_2": bool(gate_sigex), "ci_pos": bool(gate_ci), "perm_p_le_010": bool(gate_perm)},
        "concentration": {
            "n_quarters_measurable": int(n_q_measurable),
            "n_quarters_pos_t": int(n_q_pos_t),
            "quarter_pos_t_ratio": float(quarter_pos_t_ratio),
            "n_syms_measurable": int(n_sym_measurable),
            "n_syms_ci_pos": int(n_sym_ci_pos),
            "symbol_ci_pos_ratio": float(symbol_ci_pos_ratio),
            "pass": bool(conc_pass),
        },
        "quarter_breakdown": quarter_stats,
        "per_sym_summary": per_sym_summary,
    }


# ----------------------------- Main -----------------------------
def main() -> int:
    log.info("=== paradigm 148 R-1 dispatch ===")
    log.info("Universe: %s", UNIVERSE)
    log.info("Frame: %dmin | Velocity: %dbar (%dmin) | Z window: %dbar (30d)",
             FRAME_MIN, VELOCITY_BARS, VELOCITY_BARS * FRAME_MIN, ZSCORE_BARS)
    log.info("Δ shifts (min): %s | Hold: %dbar (%dmin)", DELTA_MIN_LIST, HOLD_BARS, HOLD_BARS * FRAME_MIN)
    log.info("Z threshold: ±%.1f | Fee: %.4f", Z_THRESHOLD, FEE_PER_TRADE)

    t0 = time.time()
    aligned_by_sym: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        try:
            bb = load_klines(CACHE_BYBIT, sym)
            bn = load_klines(CACHE_BINANCE, sym)
            aligned = align_klines(bb, bn)
            aligned_by_sym[sym] = aligned
            log.info("[%s] aligned n=%d range=%s..%s", sym, len(aligned),
                     aligned["ts"].min(), aligned["ts"].max())
        except FileNotFoundError as e:
            log.error("[%s] cache missing: %s", sym, e)
            return 1

    # 4-quadrant × 4 Δ = 16 cells
    quadrants = [
        ("A_focus_zpos_LONG", +1, +1),    # z>+T, LONG
        ("A_mirror_zpos_SHORT", -1, +1),  # z>+T, SHORT
        ("B_focus_zneg_SHORT", -1, -1),   # z<-T, SHORT
        ("B_mirror_zneg_LONG", +1, -1),   # z<-T, LONG
    ]

    results = {}
    for delta_min, delta_bars in zip(DELTA_MIN_LIST, DELTA_BARS_LIST):
        for q_name, dir_sign, z_filt_sign in quadrants:
            cell_label = f"D{delta_min}min_{q_name}"
            log.info("Cell: %s (delta_bars=%d, dir=%+d, z_filter=%+d)",
                     cell_label, delta_bars, dir_sign, z_filt_sign)
            per_sym = []
            for sym, aligned in aligned_by_sym.items():
                r = run_cell(aligned, sym, delta_bars, Z_THRESHOLD, dir_sign, z_filt_sign)
                per_sym.append(r)
            agg = aggregate_cell_results(per_sym, cell_label)
            results[cell_label] = agg
            log.info("  → verdict=%s n_obs=%d obs_mean_bp=%.2f sigex=%.2f ci_lower_bp=%.2f perm_p=%.3f conc=%s",
                     agg["verdict"], agg.get("n_obs", 0),
                     agg.get("obs_mean_bp", float("nan")),
                     agg.get("signal_t_excess", float("nan")),
                     agg.get("ci_lower_bp", float("nan")),
                     agg.get("perm_p_one_sided_above", float("nan")),
                     agg.get("concentration", {}).get("pass", False))

    # Top-level summary
    summary = {
        "paradigm_id": PARADIGM_ID,
        "paradigm_name": PARADIGM_NAME,
        "universe": UNIVERSE,
        "config": {
            "frame_min": FRAME_MIN,
            "velocity_bars": VELOCITY_BARS,
            "zscore_bars": ZSCORE_BARS,
            "z_threshold": Z_THRESHOLD,
            "delta_min_list": DELTA_MIN_LIST,
            "hold_bars": HOLD_BARS,
            "fee_per_trade": FEE_PER_TRADE,
        },
        "elapsed_s": round(time.time() - t0, 1),
        "cells": results,
    }

    # Overall verdict
    pass_cells = [c for c, v in results.items() if v["verdict"] == "PASS_R1_FULL"]
    concentrated_cells = [c for c, v in results.items() if v["verdict"] == "CONCENTRATED_R1_PASS"]
    if pass_cells:
        summary["overall_verdict"] = "PASS_R1_FULL"
        summary["pass_cells"] = pass_cells
    elif concentrated_cells:
        summary["overall_verdict"] = "CONCENTRATED_R1_PASS"
        summary["concentrated_cells"] = concentrated_cells
    else:
        # Check if all 4 quadrants × all 4 Δ are negative (broad falsification)
        all_negative = all(v.get("obs_mean_bp", 0) < 0 for v in results.values() if "obs_mean_bp" in v)
        if all_negative:
            summary["overall_verdict"] = "BROAD_FALSIFIED"
        else:
            summary["overall_verdict"] = "FAIL"

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    log.info("=== R-1 complete in %.1fs → %s ===", summary["elapsed_s"], out_path)
    log.info("Overall verdict: %s", summary["overall_verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
