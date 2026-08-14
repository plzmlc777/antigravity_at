"""Paradigm 160 R-1: alt_cross_exchange_volume_share_rotation_directional_4h

Hypothesis
----------
Bybit ↔ Binance Futures 24h cumulative volume share rotation × per-symbol
directional 4h hold.

Trigger
-------
- per-sym 4h bar: share = bybit_qv / (bybit_qv + binance_qv)
  using quote_volume (USDT-denominated) on both venues
- Rolling 7d (42 × 4h bars) z-score of share
- |z| ≥ 2.0 trigger

Mechanism
---------
- Bybit share spike (z ≥ +2.0): bybit-side aggressive flow → continuation 4h
  A focus: LONG @ next-bar open / A mirror: SHORT
- Bybit share dump (z ≤ -2.0): binance-side aggressive flow → continuation 4h opposite
  B focus: SHORT @ next-bar open / B mirror: LONG

4-quadrant Symmetric Negative Test (Lesson #19 mandatory for joint-trigger)

Pass criteria — Three-gate + Concentration
- signal_t_excess >= 2.0
- bootstrap CI lower (95%) > 0
- fee-aware perm_p one-sided <= 0.10
- Concentration Gate: q_pos_t_ratio >= 0.5 AND syms_ci_pos_ratio >= 0.30 AND n_syms_ci_pos >= 3

Fee: 16 bp round-trip (8 bp/side)
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
    fee_aware_perm_test,
    bootstrap_ci,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p160_r1")

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]
BINANCE_CACHE = ROOT / "runs" / "ohlcv_cache_12col"
BYBIT_CACHE = ROOT / "runs" / "ohlcv_cache" / "bybit_klines_4h"

# Trigger parameters
ROLL_WINDOW_BARS = 7 * 6  # 7d × (24/4) = 42 4h bars
Z_THRESHOLD = 2.0
HOLD_BARS = 1  # 4h hold (1 × 4h bar)
FEE_RT = 0.0016  # 16 bp round-trip

OUTPUT_DIR = ROOT / "runs" / "research_track" / "alt_cross_exchange_volume_share_rotation_directional_4h" / "r1"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _load_binance(sym: str) -> pd.DataFrame:
    fp = BINANCE_CACHE / f"{sym}_4h.joblib"
    df = joblib.load(fp)
    df = df.reset_index().rename(columns={"open_time": "ts", "quote_volume": "qv"})
    df["ts"] = pd.to_datetime(df["ts"]).dt.tz_localize(None) if df["ts"].dt.tz is not None else pd.to_datetime(df["ts"])
    return df[["ts", "open", "close", "qv"]].rename(columns={"open": "bn_open", "close": "bn_close", "qv": "bn_qv"})


def _load_bybit(sym: str) -> pd.DataFrame:
    fp = BYBIT_CACHE / f"{sym}_4h.joblib"
    df = joblib.load(fp)
    df = df.rename(columns={"open_time": "ts", "open": "by_open", "close": "by_close",
                            "quote_volume": "by_qv"})
    return df[["ts", "by_open", "by_close", "by_qv"]]


def _build_share_series(sym: str) -> pd.DataFrame:
    bn = _load_binance(sym)
    by = _load_bybit(sym)
    df = pd.merge(bn, by, on="ts", how="inner")
    df = df.sort_values("ts").reset_index(drop=True)
    df["total_qv"] = df["bn_qv"] + df["by_qv"]
    df["share"] = df["by_qv"] / df["total_qv"].replace(0, np.nan)
    df["share_mean"] = df["share"].rolling(ROLL_WINDOW_BARS, min_periods=ROLL_WINDOW_BARS).mean()
    df["share_std"] = df["share"].rolling(ROLL_WINDOW_BARS, min_periods=ROLL_WINDOW_BARS).std(ddof=1)
    df["share_z"] = (df["share"] - df["share_mean"]) / df["share_std"]
    # 4h forward return: enter at next bar open, exit at next bar close (1 bar hold)
    # since we use binance perp for trading: bn_open[t+1] -> bn_close[t+1]
    df["next_open"] = df["bn_open"].shift(-1)
    df["next_close"] = df["bn_close"].shift(-1)
    df["fwd_ret_gross"] = (df["next_close"] - df["next_open"]) / df["next_open"]
    return df


def _quadrant_metrics(
    df_all: pd.DataFrame,
    trig_mask: pd.Series,
    direction: int,
    label: str,
    candidate_pool_returns: np.ndarray,
) -> Dict:
    """Compute single-quadrant metrics."""
    if direction not in (-1, 1):
        raise ValueError("direction must be +1 (LONG) or -1 (SHORT)")

    tdf = df_all[trig_mask & df_all["fwd_ret_gross"].notna()].copy()
    if len(tdf) < 30:
        return {
            "quadrant": label,
            "direction": "LONG" if direction == 1 else "SHORT",
            "n": int(len(tdf)),
            "error": "n<30 sample insufficient",
        }

    # Apply direction × gross return − fee
    gross = direction * tdf["fwd_ret_gross"].to_numpy()
    net = gross - FEE_RT
    tdf["gross"] = gross
    tdf["net"] = net

    # Concentration: per-quarter t + per-symbol bootstrap
    tdf["quarter"] = tdf["ts"].dt.to_period("Q").astype(str)
    quarters = sorted(tdf["quarter"].unique())
    q_t = {}
    for q in quarters:
        sub = tdf[tdf["quarter"] == q]["net"].to_numpy()
        if len(sub) >= 10 and sub.std(ddof=1) > 0:
            q_t[q] = float(sub.mean() / sub.std(ddof=1) * np.sqrt(len(sub)))
        else:
            q_t[q] = None
    q_t_measurable = {k: v for k, v in q_t.items() if v is not None}
    q_pos_t_ratio = (sum(1 for v in q_t_measurable.values() if v > 0) /
                     len(q_t_measurable)) if q_t_measurable else 0.0

    # Per-symbol bootstrap CI
    sym_ci = {}
    for sym in tdf["symbol"].unique():
        sub = tdf[tdf["symbol"] == sym]["net"].to_numpy()
        if len(sub) >= 10:
            ci = bootstrap_ci(sub, n_boot=1000, block_size=1)
            sym_ci[sym] = {
                "n": int(len(sub)),
                "mean_bp": float(sub.mean() * 1e4),
                "ci_lower_bp": float(ci["ci_lower"] * 1e4),
                "ci_pos": bool(ci["ci_lower"] > 0),
            }
        else:
            sym_ci[sym] = {"n": int(len(sub)), "skip": "n<10"}
    syms_measurable = [s for s, v in sym_ci.items() if "skip" not in v]
    syms_ci_pos = [s for s in syms_measurable if sym_ci[s]["ci_pos"]]
    syms_ci_pos_ratio = (len(syms_ci_pos) / len(syms_measurable)) if syms_measurable else 0.0

    # Three-gate
    obs_t = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net))) if net.std(ddof=1) > 0 else 0.0
    fee_perm = fee_aware_perm_test(
        observed_net_returns=net,
        candidate_pool_returns=candidate_pool_returns,
        fee_per_trade=FEE_RT,
        n_perms=2000,
    )
    ci = bootstrap_ci(net, n_boot=2000, block_size=1)
    if direction == 1:
        perm_p_use = fee_perm.get("perm_p_one_sided_above", float("nan"))
    else:
        # For SHORT: net = -gross - fee; positive expected → still test above null
        perm_p_use = fee_perm.get("perm_p_one_sided_above", float("nan"))

    sig_t_excess = fee_perm.get("signal_t_excess", float("nan"))
    ci_lower = ci.get("ci_lower", float("nan"))

    three_gate = (
        isinstance(sig_t_excess, float) and not np.isnan(sig_t_excess) and sig_t_excess >= 2.0
        and isinstance(ci_lower, float) and not np.isnan(ci_lower) and ci_lower > 0
        and isinstance(perm_p_use, float) and not np.isnan(perm_p_use) and perm_p_use <= 0.10
    )

    concentration_pass = (
        q_pos_t_ratio >= 0.5
        and syms_ci_pos_ratio >= 0.30
        and len(syms_ci_pos) >= 3
    )

    return {
        "quadrant": label,
        "direction": "LONG" if direction == 1 else "SHORT",
        "n": int(len(net)),
        "gross_mean_bp": float(gross.mean() * 1e4),
        "net_mean_bp": float(net.mean() * 1e4),
        "obs_t": obs_t,
        "signal_t_excess": float(sig_t_excess) if not np.isnan(sig_t_excess) else None,
        "perm_p_one_sided_above": float(perm_p_use) if not np.isnan(perm_p_use) else None,
        "null_mean_t": fee_perm.get("null_mean_t"),
        "ci_lower_bp": float(ci_lower * 1e4) if not np.isnan(ci_lower) else None,
        "ci_upper_bp": float(ci.get("ci_upper") * 1e4),
        "prob_positive": float(ci.get("prob_positive")),
        "three_gate_pass": bool(three_gate),
        "concentration": {
            "q_pos_t_ratio": float(q_pos_t_ratio),
            "n_quarters_measurable": int(len(q_t_measurable)),
            "n_quarters_pos_t": int(sum(1 for v in q_t_measurable.values() if v > 0)),
            "per_quarter_t": {k: round(v, 2) if v is not None else None for k, v in q_t.items()},
            "syms_ci_pos_ratio": float(syms_ci_pos_ratio),
            "n_syms_ci_pos": int(len(syms_ci_pos)),
            "n_syms_measurable": int(len(syms_measurable)),
            "per_symbol": {s: v for s, v in sym_ci.items()},
            "pass": bool(concentration_pass),
        },
        "fee_floor_check": {
            "fee_rt_bp": float(FEE_RT * 1e4),
            "gross_above_fee_floor": bool(gross.mean() * 1e4 >= FEE_RT * 1e4),
        },
    }


def main():
    t_start = time.time()
    log.info("Paradigm 160 R-1 — alt_cross_exchange_volume_share_rotation_directional_4h")
    log.info("Universe: %s", UNIVERSE)
    log.info("Trigger: |share_z| >= %.1f over %d 4h bars (=%dd window)",
             Z_THRESHOLD, ROLL_WINDOW_BARS, ROLL_WINDOW_BARS // 6)

    # Build per-symbol share series
    per_sym_df = []
    for sym in UNIVERSE:
        df = _build_share_series(sym)
        df["symbol"] = sym
        per_sym_df.append(df)
    df_all = pd.concat(per_sym_df, ignore_index=True)
    df_all = df_all.dropna(subset=["share_z", "fwd_ret_gross"]).reset_index(drop=True)
    log.info("Combined n=%d rows across %d syms", len(df_all), df_all["symbol"].nunique())

    # Lesson #34: signal distribution prescreen
    z = df_all["share_z"].to_numpy()
    log.info("share_z dist: median=%.3f p90=%.3f p95=%.3f p99=%.3f max=%.3f",
             float(np.median(z)), float(np.quantile(np.abs(z), 0.90)),
             float(np.quantile(np.abs(z), 0.95)), float(np.quantile(np.abs(z), 0.99)),
             float(np.max(np.abs(z))))
    log.info("frac |z|>=2.0: %.4f  frac |z|>=2.5: %.4f  frac |z|>=3.0: %.4f",
             float((np.abs(z) >= 2.0).mean()), float((np.abs(z) >= 2.5).mean()),
             float((np.abs(z) >= 3.0).mean()))

    # Candidate pool: ALL forward returns × LONG direction (gross, no fee here — pool is gross template)
    # For SHORT mirror quadrants, the pool is the negated set, but we use abs framing —
    # candidate_pool_returns should be NET after fee under the same direction.
    # Simplest: pool = next-bar gross returns × direction sign − fee
    pool_gross = df_all["fwd_ret_gross"].to_numpy()
    pool_long_net = pool_gross - FEE_RT
    pool_short_net = -pool_gross - FEE_RT

    # Triggers
    mask_pos = df_all["share_z"] >= Z_THRESHOLD   # bybit share spike
    mask_neg = df_all["share_z"] <= -Z_THRESHOLD  # bybit share dump

    log.info("Trigger counts: pos_z=%d  neg_z=%d", int(mask_pos.sum()), int(mask_neg.sum()))

    quadrants = []

    # A focus: bybit share spike (z>=+2) × LONG (continuation primary)
    quadrants.append(_quadrant_metrics(df_all, mask_pos, +1, "A_focus_pos_z_LONG", pool_long_net))
    # A mirror: bybit share spike × SHORT (reversal)
    quadrants.append(_quadrant_metrics(df_all, mask_pos, -1, "A_mirror_pos_z_SHORT", pool_short_net))
    # B focus: bybit share dump (z<=-2) × SHORT (binance-side aggressive continuation)
    quadrants.append(_quadrant_metrics(df_all, mask_neg, -1, "B_focus_neg_z_SHORT", pool_short_net))
    # B mirror: bybit share dump × LONG (reversal)
    quadrants.append(_quadrant_metrics(df_all, mask_neg, +1, "B_mirror_neg_z_LONG", pool_long_net))

    # Aggregate verdict
    n_three_gate_pass = sum(1 for q in quadrants if q.get("three_gate_pass"))
    n_three_gate_pass_with_concentration = sum(
        1 for q in quadrants
        if q.get("three_gate_pass") and q.get("concentration", {}).get("pass")
    )

    # Perfect mirror antipattern (Lesson #39)
    A_focus_bp = quadrants[0].get("gross_mean_bp", None)
    A_mirror_bp = quadrants[1].get("gross_mean_bp", None)
    perfect_mirror_A = (
        A_focus_bp is not None and A_mirror_bp is not None
        and abs(A_focus_bp + A_mirror_bp) < 1.0  # within 1 bp = perfect mirror
    )
    B_focus_bp = quadrants[2].get("gross_mean_bp", None)
    B_mirror_bp = quadrants[3].get("gross_mean_bp", None)
    perfect_mirror_B = (
        B_focus_bp is not None and B_mirror_bp is not None
        and abs(B_focus_bp + B_mirror_bp) < 1.0
    )

    verdict_label = (
        "PASS_R1_FULL_BOTH_FOCUS" if (
            quadrants[0].get("three_gate_pass") and quadrants[0].get("concentration", {}).get("pass")
            and quadrants[2].get("three_gate_pass") and quadrants[2].get("concentration", {}).get("pass")
        )
        else "PASS_R1_A_FOCUS_ONLY" if (
            quadrants[0].get("three_gate_pass") and quadrants[0].get("concentration", {}).get("pass")
        )
        else "PASS_R1_B_FOCUS_ONLY" if (
            quadrants[2].get("three_gate_pass") and quadrants[2].get("concentration", {}).get("pass")
        )
        else "MIRROR_PASS_ONLY" if (
            n_three_gate_pass_with_concentration > 0
        )
        else "BROAD_FALSIFIED_FEE_FLOOR" if all(
            q.get("gross_mean_bp", 0) is not None
            and abs(q.get("gross_mean_bp", 0)) < FEE_RT * 1e4 for q in quadrants
        )
        else "BROAD_FALSIFIED_NO_THREE_GATE"
    )

    # Lesson #56 OUTCOME-LEVEL family proxy check
    all_quadrants_fee_floor_sub = all(
        q.get("gross_mean_bp") is not None
        and abs(q["gross_mean_bp"]) < FEE_RT * 1e4
        for q in quadrants
    )

    out = {
        "paradigm": "alt_cross_exchange_volume_share_rotation_directional_4h",
        "paradigm_number": 160,
        "phase": "R-1",
        "host": "WSL local",
        "wall_clock_s": round(time.time() - t_start, 1),
        "universe": UNIVERSE,
        "n_syms": len(UNIVERSE),
        "window": {
            "start": str(df_all["ts"].min()),
            "end": str(df_all["ts"].max()),
            "n_total_rows": int(len(df_all)),
            "n_pos_triggers": int(mask_pos.sum()),
            "n_neg_triggers": int(mask_neg.sum()),
        },
        "config": {
            "frame": "4h",
            "roll_window_bars": int(ROLL_WINDOW_BARS),
            "roll_window_days": int(ROLL_WINDOW_BARS // 6),
            "z_threshold": float(Z_THRESHOLD),
            "hold_bars": int(HOLD_BARS),
            "fee_rt_bp": float(FEE_RT * 1e4),
        },
        "signal_dist": {
            "median_share_z": float(np.median(z)),
            "p90_abs_z": float(np.quantile(np.abs(z), 0.90)),
            "p95_abs_z": float(np.quantile(np.abs(z), 0.95)),
            "p99_abs_z": float(np.quantile(np.abs(z), 0.99)),
            "max_abs_z": float(np.max(np.abs(z))),
            "frac_abs_z_ge_2": float((np.abs(z) >= 2.0).mean()),
            "frac_abs_z_ge_2_5": float((np.abs(z) >= 2.5).mean()),
            "frac_abs_z_ge_3": float((np.abs(z) >= 3.0).mean()),
        },
        "quadrants": quadrants,
        "summary": {
            "n_quadrants_three_gate_pass": int(n_three_gate_pass),
            "n_quadrants_three_gate_pass_with_concentration": int(n_three_gate_pass_with_concentration),
            "perfect_mirror_A_focus_vs_A_mirror": bool(perfect_mirror_A),
            "perfect_mirror_B_focus_vs_B_mirror": bool(perfect_mirror_B),
            "all_quadrants_fee_floor_sub_threshold": bool(all_quadrants_fee_floor_sub),
            "lesson_56_outcome_family_proxy": bool(all_quadrants_fee_floor_sub),  # If TRUE, paradigm 160 = 7th cross-ex fee-floor convergence
            "verdict": verdict_label,
        },
    }

    metrics_path = OUTPUT_DIR / "r1__metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("Saved metrics: %s", metrics_path)
    log.info("Verdict: %s  wall=%.1fs", verdict_label, time.time() - t_start)

    # Print summary
    print("\n=== Paradigm 160 R-1 Summary ===")
    print(f"Verdict: {verdict_label}")
    print(f"Window: {df_all['ts'].min()} .. {df_all['ts'].max()} ({len(df_all)} rows)")
    print(f"Triggers: pos_z={int(mask_pos.sum())} neg_z={int(mask_neg.sum())}")
    print()
    print(f"{'Quadrant':<28} {'n':>6} {'gross_bp':>10} {'net_bp':>10} {'sigex':>7} "
          f"{'perm_p':>8} {'ci_lo_bp':>10} {'q_pos':>8} {'syms_ci+':>9} {'3gate':>6} {'conc':>6}")
    for q in quadrants:
        if "error" in q:
            print(f"{q['quadrant']:<28} {q['n']:>6} ERR {q['error']}")
            continue
        conc = q["concentration"]
        sigex = q.get('signal_t_excess')
        perm_p = q.get('perm_p_one_sided_above')
        ci_lo = q.get('ci_lower_bp')
        print(f"{q['quadrant']:<28} {q['n']:>6} {q['gross_mean_bp']:>10.2f} {q['net_mean_bp']:>10.2f} "
              f"{(sigex if sigex is not None else 0):>7.2f} "
              f"{(perm_p if perm_p is not None else 0):>8.4f} "
              f"{(ci_lo if ci_lo is not None else 0):>10.2f} "
              f"{conc['q_pos_t_ratio']:>8.2f} "
              f"{conc['n_syms_ci_pos']}/{conc['n_syms_measurable']:<7} "
              f"{'PASS' if q['three_gate_pass'] else 'FAIL':>6} "
              f"{'PASS' if conc['pass'] else 'FAIL':>6}")
    print()
    print(f"perfect_mirror A_focus vs A_mirror: {perfect_mirror_A}")
    print(f"perfect_mirror B_focus vs B_mirror: {perfect_mirror_B}")
    print(f"all_quadrants_fee_floor_sub: {all_quadrants_fee_floor_sub}")
    print(f"Lesson #56 OUTCOME-LEVEL family proxy (fee-floor sub-threshold): {all_quadrants_fee_floor_sub}")


if __name__ == "__main__":
    main()
