"""Paradigm 196 R-1 — per-sym 5d/30d open interest short/long ratio z-spike,
bilateral 4-quadrant SNT.

Substrate transplant of paradigm 195 (RV ratio) → OI (open interest).
PRIMARY GOAL: universe-level concentration limit cross-substrate verify.

Hypothesis:
    Per-sym 5min open interest aggregated to 4h (last-in-bucket). Compute
        short_mean = mean OI over last 5d (5d * 6 bars = 30 4h-bars)
        long_mean  = mean OI over last 30d (180 4h-bars)
        ratio      = short_mean / long_mean
        z_ratio    = 90d rolling z-score of ratio
    z_ratio >= +2 = "5d OI level is expanded vs 30d baseline" = OI accumulation
    (term-structure spike). z_ratio <= -2 = OI distribution. Spec requests
    z>=+2 only to mirror paradigm 195 formulation (cross-substrate parity).
    4-quadrant SNT split by concurrent 4h bar direction:
        A_focus  : z>=+2 × bar UP   × LONG  (OI accumulation at top → continuation)
        A_mirror : z>=+2 × bar UP   × SHORT (OI accumulation at top → exhaustion fade)
        B_same   : z>=+2 × bar DOWN × SHORT (OI accumulation at bottom → cascade continuation)
        B_mirror : z>=+2 × bar DOWN × LONG  (OI accumulation at bottom → capitulation MR;
                                             Lesson #42 8th dogfood)

Substrate:
    backend/runs/microstructure/{SYM}USDT_full_metrics.joblib — 5min `open_interest`
    backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib       — 4h close for bar_ret + forward_ret
    13/14 syms = 799-801d (Feb 2024 - May 2026); BTC = 541d (Nov 2024 - May 2026).
    Effective universe mean ~2.14yr. Lesson #30 data window ratio ~95% (full-window OK).

Empirical sample density (measured pre-dispatch with this exact statistic):
    Total valid panel bars: 55,553
    z>=+2 raw triggers: 2,954 (5.32% across panel)
    Per-sym pos2: 126 (FIL) ~ 333 (BNB / DOGE)
    Across 4 quadrants × 9 quarters expected ~164/cell → PASS Lesson #11

Lesson refs:
    #11 sample density (prescreen passed, empirically measured 5.32%)
    #19 4-quadrant SNT bilateral mandatory (unary z>=+2 trigger split by bar dir)
    #21 single derived statistic (OI ratio z), no axis stacking
    #30 data window ratio 95% (>30% threshold, full-window applies)
    #34 empirical distribution prescreen (done; z>=+2 = 5.32%, z<=-2 = 3.31%)
    #40 structural threshold — OI ratio CAN go z<=-2 (level compression);
        spec mandated z>=+2 only for cross-substrate parity with paradigm 195.
    #42 8th dogfood (capitulation MR universal cross-class verify, OI substrate)
    #61 slug grep audit clean (no oi_ratio/open_interest_ratio/oi_term_structure)
    #62 5/5 family-distinct strict vs paradigm 71 (Binance OI velocity, Tier 4 retire):
        - statistic class: OI velocity (rate of change z) vs OI ratio (window-mean ratio) → distinct
        - mechanism: velocity acceleration trigger vs accumulation/distribution regime → distinct
        - universe: same 14-alt cohort (acceptable per Lesson #62 statistic-distinct path)
        - entry-side: spike-trigger event (sparse) — same class but distinct statistic
        - hold: 4h + sweep (same convention)
    #67/68/70 ESCAPE (per-sym idiosyncratic / continuous rolling / new statistic class)
    #69 5-item summary
    #71 sparse-strict mode (per-trade edge ≥ 2% target)

CRITICAL CROSS-SUBSTRATE TEST (paradigm 195 finding direct):
    paradigm 195 RV ratio: A_focus_h12h three-gate PASS (sigex +3.42) but
    Concentration FAIL — 2/14 syms ci_pos (14%, ADA + LINK cluster).
    Question: does universe-level concentration limit (~14% threshold) persist
    when statistic substrate is OI instead of RV? If YES → universe limit
    universal across momentum-like axes. If NO → RV-specific.

Decision criteria (paradigm 196 best cell):
    syms_ci_pos_ratio >= 30% → HYPOTHESIS 2 (OI substrate alpha-bearing dispersion)
    syms_ci_pos_ratio <  14% → HYPOTHESIS 1 (universe limit universal, 14-sym retire)
    14% <= syms_ci_pos_ratio < 30% → MARGINAL (partial universe limit)

NB on Lesson #42 8th dogfood:
    Previous dogfood chain (paradigm 117/158/162/179/193/194/195) all confirmed
    "capitulation MR" pattern: bar-DOWN × LONG (B_mirror) outperforms bar-DOWN × SHORT
    (B_same) at extreme triggers. Paradigm 196 tests cross-substrate (OI ratio).
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("paradigm196_r1")

PARADIGM = "alt_per_sym_5d_30d_open_interest_short_long_ratio_z_spike_directional_4h_bilateral"
COUNTER = 196

PRICE_CACHE_DIR = REPO_ROOT / "runs" / "ohlcv_cache_12col"
OI_CACHE_DIR = REPO_ROOT / "runs" / "microstructure"
OUT_DIR = REPO_ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX",
        "LINK", "LTC", "BCH", "NEAR", "FIL", "WIF"]

BARS_PER_DAY = 6           # 4h bars
WIN_SHORT = 5 * BARS_PER_DAY    # 30 bars (5d)
WIN_LONG = 30 * BARS_PER_DAY    # 180 bars (30d)
WIN_Z = 90 * BARS_PER_DAY       # 540 bars (90d)
DEBOUNCE_BARS = 6          # 24h debounce
Z_THRESH = 2.0             # primary trigger threshold

HOLD_BARS = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}
PRIMARY_HOLD = "4h"

FEE_RT = 0.0008  # 8 bp round-trip

# Per-sym effective data years (for life-changing 4-dim)
# BTC = 1.48yr, rest = 2.19yr; universe mean = (13*2.19 + 1*1.48) / 14 = 2.14yr
N_YEARS_UNIVERSE = 2.14


def compute_signal_from_oi_and_close(
    oi_5min: pd.Series, close_4h: pd.Series
) -> tuple[pd.Series, pd.Series, pd.Series, pd.DatetimeIndex]:
    """Resample 5min OI to 4h (last-in-bucket), align to close_4h index, compute z_ratio.

    Returns:
        z_ratio  : 90d z-score of (5d OI mean / 30d OI mean)
        bar_ret  : 1-bar (4h) simple return aligned to same index
        valid    : mask of fully-valid rows
        index    : DatetimeIndex of the aligned series
    """
    # Resample 5min OI to 4h (last) — produces 4h-aligned series
    oi_4h = oi_5min.resample("4h", label="right", closed="right").last()
    # Align with close_4h via inner-join on index
    df = pd.concat([oi_4h.rename("oi"), close_4h.rename("close")], axis=1, join="inner").sort_index()
    df = df.dropna(subset=["oi", "close"])

    short_mean = df["oi"].rolling(WIN_SHORT, min_periods=WIN_SHORT).mean()
    long_mean = df["oi"].rolling(WIN_LONG, min_periods=WIN_LONG).mean()
    ratio = short_mean / long_mean
    mu = ratio.rolling(WIN_Z, min_periods=WIN_Z).mean()
    sd = ratio.rolling(WIN_Z, min_periods=WIN_Z).std()
    z = (ratio - mu) / sd
    z = z.replace([np.inf, -np.inf], np.nan)
    bar_ret = (df["close"] / df["close"].shift(1) - 1.0)

    valid = (~z.isna()) & (~bar_ret.isna()) & np.isfinite(z) & np.isfinite(bar_ret)
    return z, bar_ret, valid, df.index


def debounce(trig: np.ndarray, gap: int) -> np.ndarray:
    out = np.zeros_like(trig, dtype=bool)
    last = -gap - 1
    for i in range(len(trig)):
        if trig[i] and (i - last) >= gap:
            out[i] = True
            last = i
    return out


def forward_return(close: np.ndarray, idx: int, hold: int) -> float:
    nxt = idx + hold
    if nxt >= len(close):
        return np.nan
    return float(close[nxt] / close[idx] - 1.0)


def t_stat(arr: np.ndarray) -> float:
    arr = np.asarray(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return float("nan")
    sd = arr.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(arr.mean() / sd * np.sqrt(len(arr)))


def collect_per_sym() -> dict:
    """Per-sym signal/bar return/close arrays + valid masks."""
    out = {}
    for sym in SYMS:
        oi_path = OI_CACHE_DIR / f"{sym}USDT_full_metrics.joblib"
        px_path = PRICE_CACHE_DIR / f"{sym}USDT_4h.joblib"
        if not oi_path.exists():
            log.warning("missing OI %s", sym)
            continue
        if not px_path.exists():
            log.warning("missing price %s", sym)
            continue
        oi_df = joblib.load(oi_path).sort_index()
        px_df = joblib.load(px_path).sort_index()
        oi_5min = oi_df["open_interest"].astype(float)
        close_4h = px_df["close"].astype(float)
        z, bar_ret, valid, idx = compute_signal_from_oi_and_close(oi_5min, close_4h)
        # Get aligned close for forward_return
        close_aligned = close_4h.reindex(idx).values
        out[sym] = dict(
            close=close_aligned,
            z=z.values,
            bar_ret=bar_ret.values,
            valid=valid.values,
            index=idx,
        )
        log.info(
            "%s: rows=%d valid=%d pos2=%d window=%s..%s",
            sym, len(idx), int(valid.sum()),
            int(((z >= Z_THRESH) & valid).sum()),
            idx[0], idx[-1],
        )
    return out


def evaluate_quadrant(per_sym: dict, quadrant: str, hold_bars: int) -> dict:
    """Return per-trade metrics for given quadrant and hold horizon."""
    trades_gross = []
    trades_net = []
    trades_meta = []  # (sym, ts, gross)
    pool_gross = []   # all candidate hold returns (for fee-aware perm pool)

    direction_long = quadrant in ("A_focus", "B_mirror")
    bar_dir_up = quadrant in ("A_focus", "A_mirror")

    for sym, d in per_sym.items():
        close = d["close"]
        z = d["z"]
        bar_ret = d["bar_ret"]
        valid = d["valid"]
        idx_arr = d["index"]

        # Build trigger mask per quadrant
        trig_raw = (z >= Z_THRESH) & valid
        if bar_dir_up:
            trig_raw = trig_raw & (bar_ret > 0)
        else:
            trig_raw = trig_raw & (bar_ret < 0)
        # debounce 24h
        trig = debounce(trig_raw, DEBOUNCE_BARS)
        trig_idxs = np.where(trig)[0]

        for i in trig_idxs:
            r = forward_return(close, i, hold_bars)
            if np.isnan(r):
                continue
            if not direction_long:
                r = -r
            gross = r
            net = gross - FEE_RT
            trades_gross.append(gross)
            trades_net.append(net)
            trades_meta.append((sym, idx_arr[i], gross))

        # Candidate pool: all valid forward-hold returns (signed by direction)
        for i in range(len(close) - hold_bars):
            if not valid[i]:
                continue
            r = forward_return(close, i, hold_bars)
            if np.isnan(r):
                continue
            if not direction_long:
                r = -r
            pool_gross.append(r)

    trades_gross = np.array(trades_gross, dtype=float)
    trades_net = np.array(trades_net, dtype=float)

    if len(trades_net) == 0:
        return dict(n_trades=0)

    obs_mean_gross_bp = float(trades_gross.mean() * 1e4)
    obs_mean_net_bp = float(trades_net.mean() * 1e4)
    obs_t = t_stat(trades_net)

    perm = fee_aware_perm_test(
        observed_net_returns=trades_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=1000,
        rng_seed=42,
    )

    boot = bootstrap_ci(trades_net, n_boot=2000, block_size=1, alpha=0.05, rng_seed=42)
    ci_lower_bp = boot["ci_lower"] * 1e4
    ci_upper_bp = boot["ci_upper"] * 1e4
    prob_pos = boot.get("prob_positive", float("nan"))

    df_meta = pd.DataFrame(trades_meta, columns=["sym", "ts", "gross"])
    df_meta["net"] = df_meta["gross"] - FEE_RT
    df_meta["quarter"] = df_meta["ts"].dt.to_period("Q").astype(str)
    quarter_stats = []
    for q, sub in df_meta.groupby("quarter"):
        if len(sub) < 5:
            quarter_stats.append(dict(quarter=q, n=len(sub), t=float("nan"),
                                       mean_bp=float(sub["net"].mean() * 1e4),
                                       measurable=False))
            continue
        t = t_stat(sub["net"].values)
        quarter_stats.append(dict(quarter=q, n=len(sub), t=t,
                                   mean_bp=float(sub["net"].mean() * 1e4),
                                   measurable=True))
    n_q_measurable = sum(1 for q in quarter_stats if q["measurable"])
    n_q_pos_t = sum(1 for q in quarter_stats if q["measurable"] and q["t"] > 0)
    quarter_pos_t_ratio = n_q_pos_t / max(n_q_measurable, 1)

    syms_stats = []
    n_syms_ci_pos = 0
    n_syms_measurable = 0
    for sym in sorted(df_meta["sym"].unique()):
        sub = df_meta[df_meta["sym"] == sym]
        if len(sub) < 5:
            syms_stats.append(dict(sym=sym, n=int(len(sub)),
                                    mean_bp=float(sub["net"].mean() * 1e4) if len(sub) else 0.0,
                                    ci_lower_bp=float("nan"), ci_pos=False, measurable=False))
            continue
        n_syms_measurable += 1
        b = bootstrap_ci(sub["net"].values, n_boot=1000, block_size=1, alpha=0.05, rng_seed=42)
        ci_lo = b["ci_lower"] * 1e4
        ci_pos = ci_lo > 0
        if ci_pos:
            n_syms_ci_pos += 1
        syms_stats.append(dict(sym=sym, n=int(len(sub)),
                                mean_bp=float(sub["net"].mean() * 1e4),
                                ci_lower_bp=float(ci_lo), ci_pos=bool(ci_pos),
                                measurable=True))
    syms_ci_pos_ratio = n_syms_ci_pos / max(n_syms_measurable, 1)

    signal_t_excess = perm.get("signal_t_excess", float("nan"))
    perm_p_one_above = perm.get("perm_p_one_sided_above", float("nan"))
    gate1 = (not np.isnan(signal_t_excess)) and signal_t_excess >= 2.0
    gate2 = (not np.isnan(ci_lower_bp)) and ci_lower_bp > 0
    gate3 = (not np.isnan(perm_p_one_above)) and perm_p_one_above <= 0.10
    three_gate_pass = bool(gate1 and gate2 and gate3)

    conc_pass = (
        quarter_pos_t_ratio >= 0.5
        and syms_ci_pos_ratio >= 0.30
        and n_syms_ci_pos >= 3
    )

    n = len(trades_net)
    trades_per_year = n / N_YEARS_UNIVERSE
    per_trade_edge_pct = float(trades_net.mean() * 100)
    hold_hours = hold_bars * 4
    util = trades_per_year * hold_hours / (365 * 24) * 100
    sharpe_ann = (trades_net.mean() / trades_net.std(ddof=1)) * np.sqrt(trades_per_year) if trades_net.std(ddof=1) > 0 else float("nan")
    lc4 = dict(
        trades_per_year=trades_per_year,
        per_trade_edge_pct=per_trade_edge_pct,
        capital_util_pct=util,
        sharpe_ann=sharpe_ann,
        passes=(trades_per_year >= 12 and per_trade_edge_pct >= 2.0
                and util >= 30 and sharpe_ann >= 1.5),
    )

    return dict(
        n_trades=n,
        obs_mean_gross_bp=obs_mean_gross_bp,
        obs_mean_net_bp=obs_mean_net_bp,
        obs_t=obs_t,
        signal_t_excess=signal_t_excess,
        null_mean_t=perm.get("null_mean_t"),
        perm_p_two_sided=perm.get("perm_p_two_sided"),
        perm_p_one_sided_above=perm_p_one_above,
        perm_p_one_sided_below=perm.get("perm_p_one_sided_below"),
        ci_lower_bp=float(ci_lower_bp),
        ci_upper_bp=float(ci_upper_bp),
        prob_positive=float(prob_pos),
        three_gate_pass=three_gate_pass,
        gate1_sigex_ge_2=bool(gate1),
        gate2_ci_lower_pos=bool(gate2),
        gate3_perm_p_le_010=bool(gate3),
        quarter_pos_t_ratio=quarter_pos_t_ratio,
        n_quarters_measurable=n_q_measurable,
        n_quarters_pos_t=n_q_pos_t,
        per_quarter=quarter_stats,
        syms_ci_pos_ratio=syms_ci_pos_ratio,
        n_syms_ci_pos=n_syms_ci_pos,
        n_syms_measurable=n_syms_measurable,
        per_sym=syms_stats,
        concentration_gate_pass=bool(conc_pass),
        life_changing_4dim=lc4,
        n_candidate_pool=len(pool_gross),
    )


def main() -> None:
    log.info("paradigm %s R-1 start", PARADIGM)
    t0 = time.time()
    log.info("collecting per-sym signals (OI ratio z)...")
    per_sym = collect_per_sym()
    log.info("collected %d syms", len(per_sym))

    results = {
        "paradigm": PARADIGM,
        "counter": COUNTER,
        "host": "hcp_local",
        "fee_rt": FEE_RT,
        "z_threshold": Z_THRESH,
        "win_short_bars": WIN_SHORT,
        "win_long_bars": WIN_LONG,
        "win_z_bars": WIN_Z,
        "debounce_bars": DEBOUNCE_BARS,
        "syms_universe": SYMS,
        "primary_hold": PRIMARY_HOLD,
        "holds": list(HOLD_BARS.keys()),
        "n_years_universe": N_YEARS_UNIVERSE,
        "substrate_paths": {
            "oi": str(OI_CACHE_DIR),
            "price": str(PRICE_CACHE_DIR),
        },
    }

    quadrants = ["A_focus", "A_mirror", "B_same", "B_mirror"]
    cells = {}
    for hold_name, hold_bars in HOLD_BARS.items():
        log.info("hold=%s (%d bars)", hold_name, hold_bars)
        for q in quadrants:
            log.info("  quadrant %s ...", q)
            cell = evaluate_quadrant(per_sym, q, hold_bars)
            cells[f"{q}_h{hold_name}"] = cell
            n = cell.get("n_trades", 0)
            if n > 0:
                log.info(
                    "    n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f "
                    "perm_p_above=%s ci_lower=%.2fbp three_gate=%s conc=%s "
                    "syms_ci_pos=%d/%d (%.1f%%) lc4=%s",
                    n, cell["obs_mean_gross_bp"], cell["obs_mean_net_bp"], cell["obs_t"],
                    cell["signal_t_excess"],
                    f"{cell['perm_p_one_sided_above']:.3f}" if cell['perm_p_one_sided_above'] is not None else "NA",
                    cell["ci_lower_bp"], cell["three_gate_pass"],
                    cell["concentration_gate_pass"],
                    cell["n_syms_ci_pos"], cell["n_syms_measurable"],
                    cell["syms_ci_pos_ratio"] * 100,
                    cell["life_changing_4dim"]["passes"]
                )
    results["cells"] = cells

    # Sweep summary (Lesson #37)
    pass_cells_3gate = [k for k, c in cells.items() if c.get("three_gate_pass")]
    pass_cells_conc = [k for k, c in cells.items()
                       if c.get("three_gate_pass") and c.get("concentration_gate_pass")]
    pass_cells_lc4 = [k for k, c in cells.items()
                      if c.get("three_gate_pass") and c.get("concentration_gate_pass")
                      and c.get("life_changing_4dim", {}).get("passes")]
    results["sweep_summary"] = {
        "n_cells_total": len(cells),
        "n_three_gate_pass": len(pass_cells_3gate),
        "cells_three_gate_pass": pass_cells_3gate,
        "n_concentration_pass": len(pass_cells_conc),
        "cells_concentration_pass": pass_cells_conc,
        "n_life_changing_pass": len(pass_cells_lc4),
        "cells_life_changing_pass": pass_cells_lc4,
    }

    # Best cell by signal_t_excess
    best = None
    for k, c in cells.items():
        if c.get("n_trades", 0) < 30:
            continue
        sigex = c.get("signal_t_excess", float("nan"))
        if np.isnan(sigex):
            continue
        if best is None or sigex > best[1]:
            best = (k, sigex, c)
    results["best_cell"] = dict(
        key=best[0],
        signal_t_excess=best[1],
        n_trades=best[2]["n_trades"],
        gross_bp=best[2]["obs_mean_gross_bp"],
        net_bp=best[2]["obs_mean_net_bp"],
        ci_lower_bp=best[2]["ci_lower_bp"],
        three_gate_pass=best[2]["three_gate_pass"],
        concentration_gate_pass=best[2]["concentration_gate_pass"],
        syms_ci_pos_ratio=best[2]["syms_ci_pos_ratio"],
        n_syms_ci_pos=best[2]["n_syms_ci_pos"],
        n_syms_measurable=best[2]["n_syms_measurable"],
        life_changing_4dim=best[2]["life_changing_4dim"],
    ) if best else None

    # Lesson #42 8th dogfood diagnostic
    l42 = {}
    for hold_name in HOLD_BARS:
        b_mirror = cells.get(f"B_mirror_h{hold_name}", {})
        b_same = cells.get(f"B_same_h{hold_name}", {})
        if b_mirror.get("n_trades", 0) > 0 and b_same.get("n_trades", 0) > 0:
            l42[hold_name] = dict(
                B_mirror_net_bp=b_mirror.get("obs_mean_net_bp"),
                B_mirror_sigex=b_mirror.get("signal_t_excess"),
                B_mirror_three_gate=b_mirror.get("three_gate_pass"),
                B_mirror_conc_gate=b_mirror.get("concentration_gate_pass"),
                B_same_net_bp=b_same.get("obs_mean_net_bp"),
                B_same_sigex=b_same.get("signal_t_excess"),
                B_mirror_minus_B_same_net_bp=(
                    b_mirror.get("obs_mean_net_bp") - b_same.get("obs_mean_net_bp")
                ),
            )
    results["lesson_42_8th_dogfood"] = l42

    # paradigm 195 direct comparison (CRITICAL universe-level concentration limit test)
    # Compare best A_focus cells across hold horizons (paradigm 195 best was A_focus_h12h)
    p195_cmp = {}
    for hold_name in HOLD_BARS:
        cell = cells.get(f"A_focus_h{hold_name}", {})
        if cell.get("n_trades", 0) > 0:
            p195_cmp[hold_name] = dict(
                p196_oi_sigex=cell.get("signal_t_excess"),
                p196_oi_three_gate=cell.get("three_gate_pass"),
                p196_oi_conc_gate=cell.get("concentration_gate_pass"),
                p196_oi_syms_ci_pos_ratio=cell.get("syms_ci_pos_ratio"),
                p196_oi_n_syms_ci_pos=cell.get("n_syms_ci_pos"),
                p196_oi_n_syms_measurable=cell.get("n_syms_measurable"),
                p196_oi_net_bp=cell.get("obs_mean_net_bp"),
                p196_oi_n_trades=cell.get("n_trades"),
            )

    # Universe-level concentration limit verdict (based on best cell)
    if best is not None:
        bsyms_ratio = best[2].get("syms_ci_pos_ratio", 0.0)
        if bsyms_ratio >= 0.30:
            uni_verdict = "HYPOTHESIS_2_OI_SUBSTRATE_ALPHA_BEARING_DISPERSION"
        elif bsyms_ratio < 0.14:
            uni_verdict = "HYPOTHESIS_1_UNIVERSE_LEVEL_LIMIT_UNIVERSAL_14SYM_RETIRE_CANDIDATE"
        else:
            uni_verdict = "MARGINAL_PARTIAL_UNIVERSE_LIMIT"
    else:
        uni_verdict = "UNDETERMINED_NO_BEST_CELL"

    results["paradigm_195_direct_comparison"] = {
        "p195_axis": "per-sym 5d/30d realized variance ratio z (vol term structure)",
        "p196_axis": "per-sym 5d/30d open interest ratio z (OI term structure)",
        "p195_best_cell": "A_focus_h12h three-gate PASS sigex=3.42 Conc FAIL (2/14 syms ci_pos = 14.3%, ADA+LINK cluster)",
        "p196_a_focus_cells": p195_cmp,
        "p196_best_overall_cell": best[0] if best else None,
        "p196_best_syms_ci_pos_ratio": best[2].get("syms_ci_pos_ratio") if best else None,
        "p196_best_n_syms_ci_pos": best[2].get("n_syms_ci_pos") if best else None,
        "universe_level_concentration_limit_verdict": uni_verdict,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("wrote %s (elapsed %.1fs)", out_path, time.time() - t0)
    log.info("universe-level concentration limit verdict: %s", uni_verdict)


if __name__ == "__main__":
    main()
