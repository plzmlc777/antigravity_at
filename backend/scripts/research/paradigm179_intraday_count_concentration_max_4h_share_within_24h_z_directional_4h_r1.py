"""Paradigm 179 R-1 PoC: intraday trade-count concentration coefficient (max 4h share within 24h) directional.

Hypothesis
----------
For each rolling 24h window (6 × 4h bars), compute max_share = max(count) / sum(count).
- Uniform distribution -> 1/6 ≈ 0.167
- max_share >= 0.4 -> one bar absorbs 40%+ of trades = strong temporal clustering event

Trigger: per-symbol rolling-90d z-score of max_share with |z| >= 2.
Trigger anchor: end timestamp of the max-share bar (the dominant bar's close).

4-Quadrant Symmetric Negative Test:
  A focus       : max_share spike + max bar price UP × LONG continuation
  A mirror      : max_share spike + max bar price UP × SHORT reversal
  B same-sign   : max_share spike + max bar price DOWN × SHORT continuation
  B mirror      : max_share spike + max bar price DOWN × LONG reversal (capitulation MR)

Three-gate PASS per quadrant:
  signal_t_excess >= 2.0  AND  bootstrap ci_lower > 0  AND  perm_p_one_sided_above <= 0.10

Concentration gate (Lesson #16):
  quarter_pos_t_ratio >= 0.5  AND  symbol_ci_pos_ratio >= 0.30  AND  n_symbols_ci_pos >= 3

Hold sweep: 4h primary, 8h and 12h secondary.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("p179_r1")

PARADIGM = "paradigm179_intraday_count_concentration_max_4h_share_within_24h_z_directional_4h"
CACHE_DIR = ROOT / "runs/ohlcv_cache_12col"
OUT_DIR = ROOT / "runs/research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LINK", "LTC", "AVAX", "BCH", "FIL", "NEAR", "WIF"]

WINDOW_BARS = 6  # 24h / 4h = 6 bars
Z_WINDOW_BARS = 540  # 90 days * 6 bars/day
Z_THRESHOLD = 2.0
HOLDS_BARS = {"4h": 1, "8h": 2, "12h": 3}
PRIMARY_HOLD = "4h"
FEE_PER_TRADE = 0.0008

QUADRANTS = ["A_focus", "A_mirror", "B_same_sign", "B_mirror"]


def load_symbol(sym: str) -> pd.DataFrame | None:
    fp = CACHE_DIR / f"{sym}USDT_4h.joblib"
    if not fp.exists():
        log.warning("missing cache: %s", fp)
        return None
    df = joblib.load(fp)
    if "count" not in df.columns or "close" not in df.columns:
        log.warning("missing columns in %s", sym)
        return None
    df = df.sort_index()
    return df[["open", "high", "low", "close", "count"]].copy()


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute max_share over rolling 24h window and rolling-90d z-score.

    The anchor row is the bar that IS the max bar; we attribute the signal there.
    """
    cnt = df["count"].astype(float)
    n = len(cnt)
    cnt_vals = cnt.values
    rolling_sum = pd.Series(cnt_vals, index=cnt.index).rolling(WINDOW_BARS, min_periods=WINDOW_BARS).sum()
    # For each position i, look at window [i-5..i] and find which bar is the max.
    max_share = pd.Series(np.nan, index=cnt.index, dtype=float)
    max_offset = pd.Series(np.nan, index=cnt.index, dtype=float)
    for i in range(WINDOW_BARS - 1, n):
        window = cnt_vals[i - WINDOW_BARS + 1 : i + 1]
        s = window.sum()
        if s <= 0:
            continue
        mx = window.max()
        off = int(np.argmax(window))  # 0..5, 0=oldest, 5=newest
        max_share.iloc[i] = mx / s
        max_offset.iloc[i] = off

    # z-score over 90d rolling
    mean = max_share.rolling(Z_WINDOW_BARS, min_periods=Z_WINDOW_BARS).mean()
    std = max_share.rolling(Z_WINDOW_BARS, min_periods=Z_WINDOW_BARS).std()
    z = (max_share - mean) / std

    out = pd.DataFrame(
        {
            "close": df["close"].astype(float),
            "max_share": max_share,
            "max_offset_in_24h": max_offset,
            "z": z,
        }
    )
    return out


def get_max_bar_direction(df_sigs: pd.DataFrame, df_raw: pd.DataFrame) -> pd.Series:
    """Determine UP/DOWN direction of the *max bar* within the 24h window.

    The max bar is at index (i - 5 + offset), where offset in 0..5.
    Direction = sign(close - open) of that max bar.
    """
    direction = pd.Series(np.nan, index=df_sigs.index, dtype=float)
    opens = df_raw["open"].values
    closes = df_raw["close"].values
    offsets = df_sigs["max_offset_in_24h"].values

    for i in range(len(df_sigs)):
        off = offsets[i]
        if np.isnan(off):
            continue
        max_bar_idx = i - (WINDOW_BARS - 1) + int(off)
        if max_bar_idx < 0:
            continue
        o = opens[max_bar_idx]
        c = closes[max_bar_idx]
        if o <= 0:
            continue
        direction.iloc[i] = 1.0 if c > o else (-1.0 if c < o else 0.0)
    return direction


def compute_forward_returns(close: pd.Series, hold_bars: int) -> pd.Series:
    """Forward (entry-at-close[i] -> exit-at-close[i+hold]) gross return."""
    fwd = close.shift(-hold_bars) / close - 1.0
    return fwd


def quadrant_trades_per_sym(sigs: pd.DataFrame, direction_max_bar: pd.Series, fwd_ret: pd.Series, quadrant: str) -> pd.DataFrame:
    """Filter the per-symbol signals/returns to the given quadrant.

    Each trade carries:
      - entry_time (index)
      - gross : gross return over hold window
      - direction : +1 long / -1 short (the trade direction)
      - net : direction * gross - fee
    """
    z = sigs["z"]
    df = pd.DataFrame(
        {"z": z, "dir_max": direction_max_bar, "gross": fwd_ret}
    ).dropna()
    # |z| >= 2 trigger
    df = df.loc[df["z"].abs() >= Z_THRESHOLD]
    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))

    if quadrant == "A_focus":
        df = df.loc[df["dir_max"] > 0]
        direction = 1.0  # LONG continuation
    elif quadrant == "A_mirror":
        df = df.loc[df["dir_max"] > 0]
        direction = -1.0  # SHORT reversal
    elif quadrant == "B_same_sign":
        df = df.loc[df["dir_max"] < 0]
        direction = -1.0  # SHORT continuation
    elif quadrant == "B_mirror":
        df = df.loc[df["dir_max"] < 0]
        direction = 1.0  # LONG reversal (capitulation MR)
    else:
        raise ValueError(f"unknown quadrant {quadrant}")

    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))

    df = df.assign(direction=direction)
    df["net"] = df["direction"] * df["gross"] - FEE_PER_TRADE
    return df


def per_quadrant_eval(per_sym_trades: dict, candidate_pool: list, label: str) -> dict:
    """Run perm test + bootstrap CI + concentration diagnostics on a quadrant."""
    all_net = []
    per_sym_summary = {}
    quarter_t_data = {}  # quarter -> list of net

    for sym, df in per_sym_trades.items():
        if df is None or df.empty:
            continue
        net_arr = df["net"].values
        gross_arr = df["gross"].values * df["direction"].values  # signed gross
        all_net.extend(net_arr.tolist())
        # per-sym bootstrap CI
        if len(net_arr) >= 5:
            ci = bootstrap_ci(net_arr, n_boot=1000, block_size=1)
            per_sym_summary[sym] = {
                "n": int(len(net_arr)),
                "mean_net_bp": float(net_arr.mean() * 10000),
                "ci_lower_bp": float(ci["ci_lower"] * 10000),
                "ci_upper_bp": float(ci["ci_upper"] * 10000),
                "ci_pos": bool(ci["ci_lower"] > 0),
            }
        else:
            per_sym_summary[sym] = {
                "n": int(len(net_arr)),
                "mean_net_bp": float(net_arr.mean() * 10000) if len(net_arr) else 0.0,
                "ci_lower_bp": float("nan"),
                "ci_upper_bp": float("nan"),
                "ci_pos": False,
            }
        # quarterly bucketing
        q_series = df.index.to_series().dt.to_period("Q")
        for q, sub in df.groupby(q_series):
            qkey = str(q)
            quarter_t_data.setdefault(qkey, []).extend(sub["net"].values.tolist())

    n_total = len(all_net)
    if n_total < 5:
        return {
            "label": label,
            "n_trades": n_total,
            "error": "n<5",
            "per_sym": per_sym_summary,
        }

    all_net_arr = np.asarray(all_net, dtype=float)
    obs_mean = float(all_net_arr.mean())
    obs_std = all_net_arr.std(ddof=1)
    obs_t = float(obs_mean / obs_std * np.sqrt(n_total)) if obs_std > 0 else 0.0

    # Bootstrap CI on aggregate
    ci_agg = bootstrap_ci(all_net_arr, n_boot=2000, block_size=1)

    # Fee-aware perm test using the candidate pool of all-bar forward returns (gross unsigned)
    # For the perm null, pool is signed by quadrant direction
    quadrant_direction = {"A_focus": 1.0, "A_mirror": -1.0, "B_same_sign": -1.0, "B_mirror": 1.0}[label]
    pool_signed = np.asarray(candidate_pool, dtype=float) * quadrant_direction
    perm = fee_aware_perm_test(
        observed_net_returns=all_net_arr,
        candidate_pool_returns=pool_signed,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )

    # Concentration diagnostics
    # Per-quarter t-stat
    quarter_t = {}
    for q, vals in quarter_t_data.items():
        a = np.asarray(vals, dtype=float)
        if len(a) >= 5 and a.std(ddof=1) > 0:
            t = float(a.mean() / a.std(ddof=1) * np.sqrt(len(a)))
            quarter_t[q] = {"n": int(len(a)), "t": t, "mean_bp": float(a.mean() * 10000), "pos_t": bool(t > 0)}
    n_quarters_measurable = len(quarter_t)
    n_quarters_pos_t = sum(1 for v in quarter_t.values() if v["pos_t"])
    quarter_pos_t_ratio = n_quarters_pos_t / n_quarters_measurable if n_quarters_measurable else 0.0

    n_syms_measurable = sum(1 for s in per_sym_summary.values() if not np.isnan(s["ci_lower_bp"]))
    n_syms_ci_pos = sum(1 for s in per_sym_summary.values() if s["ci_pos"])
    symbol_ci_pos_ratio = n_syms_ci_pos / n_syms_measurable if n_syms_measurable else 0.0

    # Three-gate verdict
    gate_signal_t = bool(perm["signal_t_excess"] >= 2.0) if not np.isnan(perm["signal_t_excess"]) else False
    gate_ci = bool(ci_agg["ci_lower"] > 0)
    gate_perm = bool(perm["perm_p_one_sided_above"] <= 0.10) if not np.isnan(perm["perm_p_one_sided_above"]) else False
    three_gate_pass = gate_signal_t and gate_ci and gate_perm

    # Concentration gate
    conc_pass = bool(
        quarter_pos_t_ratio >= 0.5
        and symbol_ci_pos_ratio >= 0.30
        and n_syms_ci_pos >= 3
    )

    return {
        "label": label,
        "n_trades": int(n_total),
        "obs_mean_bp": float(obs_mean * 10000),
        "obs_t": obs_t,
        "ci_lower_bp": float(ci_agg["ci_lower"] * 10000),
        "ci_upper_bp": float(ci_agg["ci_upper"] * 10000),
        "ci_prob_positive": float(ci_agg["prob_positive"]),
        "null_mean_t": perm["null_mean_t"],
        "signal_t_excess": perm["signal_t_excess"],
        "perm_p_two_sided": perm["perm_p_two_sided"],
        "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
        "gates": {
            "signal_t_excess_ge_2": gate_signal_t,
            "ci_lower_gt_0": gate_ci,
            "perm_p_le_0_10": gate_perm,
            "three_gate_pass": three_gate_pass,
        },
        "concentration": {
            "quarter_t": quarter_t,
            "n_quarters_measurable": n_quarters_measurable,
            "n_quarters_pos_t": n_quarters_pos_t,
            "quarter_pos_t_ratio": quarter_pos_t_ratio,
            "n_syms_measurable": n_syms_measurable,
            "n_syms_ci_pos": n_syms_ci_pos,
            "symbol_ci_pos_ratio": symbol_ci_pos_ratio,
            "concentration_gate_pass": conc_pass,
        },
        "per_sym": per_sym_summary,
    }


def main():
    log.info("paradigm 179 R-1 starting — 14 syms × 4h × 2.25yr × 4-quadrant SNT × 3 holds")

    # Load + build signals
    sym_signals = {}
    sym_raw = {}
    sym_directions = {}
    for sym in SYMS:
        df = load_symbol(sym)
        if df is None:
            continue
        sigs = compute_signals(df)
        direction_max = get_max_bar_direction(sigs, df)
        sym_signals[sym] = sigs
        sym_raw[sym] = df
        sym_directions[sym] = direction_max
        log.info(
            "  %s: rows=%d, valid_z=%d, max_share p50=%.4f p99=%.4f",
            sym,
            len(sigs),
            int(sigs["z"].notna().sum()),
            float(sigs["max_share"].median(skipna=True)),
            float(sigs["max_share"].quantile(0.99)),
        )

    # Build pool of all candidate gross forward returns (for each hold) for perm test
    results_all_holds = {}
    for hold_label, hold_bars in HOLDS_BARS.items():
        log.info("=== HOLD %s (%d bars) ===", hold_label, hold_bars)

        # candidate pool: all valid gross fwd returns across symbols (where signal was computable)
        pool = []
        per_sym_fwd = {}
        for sym, df in sym_raw.items():
            fwd = compute_forward_returns(df["close"].astype(float), hold_bars)
            per_sym_fwd[sym] = fwd
            sigs = sym_signals[sym]
            valid_idx = sigs["z"].dropna().index
            valid_fwd = fwd.reindex(valid_idx).dropna()
            pool.extend(valid_fwd.values.tolist())
        log.info("  candidate pool size: %d", len(pool))

        hold_result = {"hold": hold_label, "hold_bars": hold_bars, "pool_size": len(pool), "quadrants": {}}

        for quad in QUADRANTS:
            per_sym_trades = {}
            for sym in sym_signals:
                df_q = quadrant_trades_per_sym(
                    sym_signals[sym], sym_directions[sym], per_sym_fwd[sym], quad
                )
                per_sym_trades[sym] = df_q
            r = per_quadrant_eval(per_sym_trades, pool, quad)
            hold_result["quadrants"][quad] = r
            log.info(
                "  %s n=%d obs_t=%.2f sigex=%.2f ci_lo_bp=%.1f perm_p_above=%.3f three_gate=%s conc_gate=%s",
                quad,
                r.get("n_trades", 0),
                r.get("obs_t", 0.0),
                r.get("signal_t_excess", float("nan")) if r.get("signal_t_excess") is not None else float("nan"),
                r.get("ci_lower_bp", float("nan")),
                r.get("perm_p_one_sided_above", float("nan")) if r.get("perm_p_one_sided_above") is not None else float("nan"),
                r.get("gates", {}).get("three_gate_pass", False),
                r.get("concentration", {}).get("concentration_gate_pass", False),
            )
        results_all_holds[hold_label] = hold_result

    # Overall verdict — primary hold = 4h, scan all holds for any PASS cell
    primary = results_all_holds[PRIMARY_HOLD]
    overall_three_gate_pass_cells = []
    overall_full_pass_cells = []
    for hold_label, hres in results_all_holds.items():
        for quad, qres in hres["quadrants"].items():
            if qres.get("gates", {}).get("three_gate_pass"):
                overall_three_gate_pass_cells.append({"hold": hold_label, "quadrant": quad})
                if qres.get("concentration", {}).get("concentration_gate_pass"):
                    overall_full_pass_cells.append({"hold": hold_label, "quadrant": quad})

    # Primary verdict logic
    n_primary_pass = sum(1 for q in QUADRANTS if primary["quadrants"][q].get("gates", {}).get("three_gate_pass"))
    if n_primary_pass == 0 and not overall_three_gate_pass_cells:
        verdict = "BROAD_FALSIFIED"
        verdict_reason = "All 4 quadrants × 3 holds three-gate FAIL"
    elif n_primary_pass == 0 and overall_three_gate_pass_cells:
        verdict = "BROAD_FALSIFIED_PRIMARY_OFF_PRIMARY_CELL_PASS"
        verdict_reason = f"Primary hold 4h all-fail; off-primary PASS cells: {overall_three_gate_pass_cells}"
    elif overall_full_pass_cells:
        # at least one cell has both gates pass
        verdict = "PASS_R1_FULL_CANDIDATE"
        verdict_reason = f"PASS cells (three+conc): {overall_full_pass_cells}"
    else:
        verdict = "CONCENTRATED_R1_PASS"
        verdict_reason = "three-gate PASS but Concentration FAIL"

    # B mirror Lesson #42 check
    b_mirror_primary = primary["quadrants"]["B_mirror"]
    b_same_primary = primary["quadrants"]["B_same_sign"]
    lesson42_check = {
        "B_mirror_three_gate_pass": b_mirror_primary.get("gates", {}).get("three_gate_pass", False),
        "B_same_sign_three_gate_pass": b_same_primary.get("gates", {}).get("three_gate_pass", False),
        "lesson42_4th_dogfood_pattern": (
            b_mirror_primary.get("gates", {}).get("three_gate_pass", False)
            and not b_same_primary.get("gates", {}).get("three_gate_pass", False)
        ),
    }

    output = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "universe": [f"{s}USDT" for s in SYMS],
        "n_syms": len(sym_signals),
        "trigger": {
            "statistic": "max_share=max(count)/sum(count) over rolling 6×4h bars",
            "z_window_bars": Z_WINDOW_BARS,
            "z_threshold_abs": Z_THRESHOLD,
        },
        "fee_per_trade": FEE_PER_TRADE,
        "holds_tested": list(HOLDS_BARS.keys()),
        "primary_hold": PRIMARY_HOLD,
        "results": results_all_holds,
        "summary": {
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "primary_hold_quadrants_three_gate_pass": n_primary_pass,
            "all_hold_three_gate_pass_cells": overall_three_gate_pass_cells,
            "all_hold_full_pass_cells_three_plus_conc": overall_full_pass_cells,
            "lesson42_check": lesson42_check,
        },
    }

    out_fp = OUT_DIR / "r1__metrics.json"
    with open(out_fp, "w") as fh:
        json.dump(output, fh, indent=2, default=str)
    log.info("wrote %s", out_fp)
    log.info("VERDICT: %s — %s", verdict, verdict_reason)


if __name__ == "__main__":
    main()
