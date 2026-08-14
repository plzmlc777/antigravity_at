"""Paradigm 195 R-1 — per-sym 5d/30d realized variance ABSOLUTE SPREAD z-spike,
bilateral 4-quadrant SNT. paradigm 194 ratio formulation follow-up.

Hypothesis:
    Per-sym 4h close-to-close log returns. Compute (mean variance per bar):
        short_var  = mean of squared returns over last 5d (30 bars)
        long_var   = mean of squared returns over last 30d (180 bars)
        spread     = short_var - long_var   (absolute, can be +/-)
        z_spread   = 90d rolling z-score of spread
    |z_spread| >= +2 trigger primary (vol expansion: 5d > 30d).
    4-quadrant SNT split by concurrent bar direction:
        A_focus  : z>=+2 × bar UP   × LONG  (vol expansion at top → continuation)
        A_mirror : z>=+2 × bar UP   × SHORT (vol expansion at top → exhaustion fade)
        B_same   : z>=+2 × bar DOWN × SHORT (vol expansion at bottom → cascade continuation)
        B_mirror : z>=+2 × bar DOWN × LONG  (vol expansion at bottom → capitulation MR;
                                             Lesson #42 7th dogfood)

Lesson #40 dual-function test (CRITICAL hypothesis):
    paradigm 194 used ratio (5d_var / 30d_var) which is BOUNDED below by 0.
    paradigm 195 uses absolute spread which is UNBOUNDED both directions.
    Does removing the ratio compression liberate per-sym CI dispersal?
    paradigm 194: 3 cells three-gate PASS but ALL FAIL conc (max 2/14=14.3% syms ci_pos).
    paradigm 195: if conc >= 30% with same axis class → ratio-compression IS limiter
                  (Lesson #40 dual-function CONFIRMED).
                  if conc still <30% → universe-level limit (ratio not at fault).

Substrate:
    backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib × 14 syms × 2.25yr (4920 4h bars).
    [[feedback-no-freemium-trial]] FULL compliant, zero backfill.

Empirical sample density (R-0 prescreen):
    z>=+2 raw triggers: 3669 / 58814 valid (6.24%) — similar to p194 (6.43%)
    Per-sym pos2: 164 (WIF) to 371 (BNB) — robust dispersion
    Expected per-cell per-quarter: 203.8 → PASS Lesson #11

Lesson refs:
    #11 sample density (prescreen PASS empirically measured)
    #19 4-quadrant SNT bilateral mandatory (z>=+2 trigger × bar dir split)
    #21 single derived statistic, no axis stacking
    #34 empirical distribution prescreen (done; |z|>=2 = 6.76%)
    #40 structural threshold — absolute spread UNBOUNDED both directions;
        z<=-2 reachable (0.52%) but primary z>=+2 trigger only.
        **Dual-function hypothesis test vs paradigm 194 ratio**.
    #42 7th dogfood (capitulation MR universal scope test on absolute spread)
    #61 slug grep audit clean (rv_spread/variance_spread/vol_spread: 0 prior)
    #62 family-distinct: same axis class (RV term-structure) but absolute vs ratio
        formulation. Lesson #70 R-1 graveyard follow-up scope (paradigm 194 same-mechanism
        formulation refinement).
    #67/68/70 ESCAPE (per-sym idiosyncratic / continuous rolling / R-1 follow-up not R-5 LIVE expansion)
    #69 5-item summary
    #71 sparse-strict mode (per-trade edge >=2% target)
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
log = logging.getLogger("paradigm195_r1")

PARADIGM = "alt_per_sym_5d_30d_realized_variance_spread_absolute_directional_4h_bilateral"
CACHE_DIR = REPO_ROOT / "runs" / "ohlcv_cache_12col"
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


def compute_signal(close: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (z_spread, bar_ret, valid_mask).

    z_spread : 90d z-score of (5d mean variance - 30d mean variance)
    bar_ret  : 1-bar (4h) simple return
    valid    : all windows filled
    """
    ser = pd.Series(close)
    log_ret = np.log(ser / ser.shift(1))
    sq = log_ret.pow(2)
    # MEAN variance (per-bar comparable scale)
    short_var = sq.rolling(WIN_SHORT, min_periods=WIN_SHORT).mean()
    long_var = sq.rolling(WIN_LONG, min_periods=WIN_LONG).mean()
    spread = short_var - long_var
    mu = spread.rolling(WIN_Z, min_periods=WIN_Z).mean()
    sd = spread.rolling(WIN_Z, min_periods=WIN_Z).std()
    z = (spread - mu) / sd
    z_arr = z.values
    bar_ret = (ser / ser.shift(1) - 1.0).values
    valid = ~np.isnan(z_arr) & ~np.isnan(bar_ret) & np.isfinite(z_arr)
    return z_arr, bar_ret, valid


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
    out = {}
    for sym in SYMS:
        p = CACHE_DIR / f"{sym}USDT_4h.joblib"
        if not p.exists():
            log.warning("missing %s", sym)
            continue
        df = joblib.load(p).sort_index()
        close = df["close"].astype(float).values
        z, bar_ret, valid = compute_signal(close)
        out[sym] = dict(
            close=close,
            z=z,
            bar_ret=bar_ret,
            valid=valid,
            index=df.index,
        )
    return out


def evaluate_quadrant(per_sym: dict, quadrant: str, hold_bars: int) -> dict:
    trades_gross = []
    trades_net = []
    trades_meta = []  # (sym, ts, gross)
    pool_gross = []

    direction_long = quadrant in ("A_focus", "B_mirror")
    bar_dir_up = quadrant in ("A_focus", "A_mirror")

    for sym, d in per_sym.items():
        close = d["close"]
        z = d["z"]
        bar_ret = d["bar_ret"]
        valid = d["valid"]
        idx_arr = d["index"]

        trig_raw = (z >= Z_THRESH) & valid
        if bar_dir_up:
            trig_raw = trig_raw & (bar_ret > 0)
        else:
            trig_raw = trig_raw & (bar_ret < 0)
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
    n_years = 2.25
    trades_per_year = n / n_years
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
    log.info("collecting per-sym signals...")
    per_sym = collect_per_sym()
    log.info("collected %d syms", len(per_sym))

    results = {
        "paradigm": PARADIGM,
        "counter": 195,
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
        "formulation": "absolute_spread (5d_mean_var - 30d_mean_var) — unbounded both dirs",
        "p194_formulation_was": "ratio (5d_var / 30d_var) — bounded below by 0",
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
                    "perm_p_above=%s ci_lower=%.2fbp three_gate=%s conc=%s syms_ci_pos=%d/%d lc4=%s",
                    n, cell["obs_mean_gross_bp"], cell["obs_mean_net_bp"], cell["obs_t"],
                    cell["signal_t_excess"],
                    f"{cell['perm_p_one_sided_above']:.3f}" if cell['perm_p_one_sided_above'] is not None else "NA",
                    cell["ci_lower_bp"], cell["three_gate_pass"],
                    cell["concentration_gate_pass"],
                    cell["n_syms_ci_pos"], cell["n_syms_measurable"],
                    cell["life_changing_4dim"]["passes"]
                )
    results["cells"] = cells

    # Lesson #37 full hold×threshold sweep verdict scan
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
        life_changing_4dim=best[2]["life_changing_4dim"],
    ) if best else None

    # Lesson #42 7th dogfood diagnostic
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
                B_mirror_syms_ci_pos=f"{b_mirror.get('n_syms_ci_pos', 0)}/{b_mirror.get('n_syms_measurable', 0)}",
                B_same_net_bp=b_same.get("obs_mean_net_bp"),
                B_same_sigex=b_same.get("signal_t_excess"),
            )
    results["lesson_42_7th_dogfood"] = l42

    # Paradigm 194 direct comparison (Lesson #40 dual-function test)
    p194_path = REPO_ROOT / "runs" / "research_track" / "alt_per_sym_5d_30d_realized_variance_short_long_ratio_z_spike_directional_4h_bilateral" / "r1__metrics.json"
    p194_compare = {}
    if p194_path.exists():
        with open(p194_path) as f:
            p194 = json.load(f)
        p194_cells = p194.get("cells", {})
        for k in cells.keys():
            p194_cell = p194_cells.get(k, {})
            p195_cell = cells[k]
            if p194_cell.get("n_trades", 0) > 0 and p195_cell.get("n_trades", 0) > 0:
                p194_compare[k] = dict(
                    p194_n=p194_cell["n_trades"],
                    p195_n=p195_cell["n_trades"],
                    p194_net_bp=p194_cell["obs_mean_net_bp"],
                    p195_net_bp=p195_cell["obs_mean_net_bp"],
                    p194_sigex=p194_cell["signal_t_excess"],
                    p195_sigex=p195_cell["signal_t_excess"],
                    delta_sigex=p195_cell["signal_t_excess"] - p194_cell["signal_t_excess"],
                    p194_syms_ci_pos=f"{p194_cell.get('n_syms_ci_pos', 0)}/{p194_cell.get('n_syms_measurable', 0)}",
                    p195_syms_ci_pos=f"{p195_cell.get('n_syms_ci_pos', 0)}/{p195_cell.get('n_syms_measurable', 0)}",
                    delta_syms_ci_pos=p195_cell.get("n_syms_ci_pos", 0) - p194_cell.get("n_syms_ci_pos", 0),
                    p194_three_gate=p194_cell["three_gate_pass"],
                    p195_three_gate=p195_cell["three_gate_pass"],
                    p194_conc=p194_cell["concentration_gate_pass"],
                    p195_conc=p195_cell["concentration_gate_pass"],
                )

        # Lesson #40 dual-function verdict
        # CONFIRMED: paradigm 195 conc PASS in any cell where paradigm 194 conc FAILED
        # REJECTED: both fail conc → universe-level limit
        p194_max_syms = max(c.get("n_syms_ci_pos", 0) for c in p194_cells.values() if c.get("n_trades", 0) > 0)
        p195_max_syms = max(c.get("n_syms_ci_pos", 0) for c in cells.values() if c.get("n_trades", 0) > 0)
        p194_any_conc = any(c.get("concentration_gate_pass") for c in p194_cells.values() if c.get("n_trades", 0) > 0)
        p195_any_conc = any(c.get("concentration_gate_pass") for c in cells.values() if c.get("n_trades", 0) > 0)
        if p195_any_conc and not p194_any_conc:
            l40_verdict = "DUAL_FUNCTION_CONFIRMED — absolute spread liberates per-sym CI dispersal; ratio was compression limiter"
        elif p195_max_syms > p194_max_syms * 1.5:
            l40_verdict = "DUAL_FUNCTION_PARTIAL — absolute spread improves CI dispersal but not enough to PASS conc gate"
        elif p195_max_syms <= p194_max_syms:
            l40_verdict = "DUAL_FUNCTION_REJECTED — absolute spread same/worse CI dispersal than ratio; universe-level limit, ratio formulation not at fault"
        else:
            l40_verdict = "DUAL_FUNCTION_INCONCLUSIVE — marginal improvement, neither formulation passes conc gate"
        results["lesson_40_dual_function"] = dict(
            verdict=l40_verdict,
            p194_max_syms_ci_pos=p194_max_syms,
            p195_max_syms_ci_pos=p195_max_syms,
            p194_any_conc_pass=p194_any_conc,
            p195_any_conc_pass=p195_any_conc,
        )
    results["paradigm_194_direct_comparison"] = p194_compare

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("wrote %s (elapsed %.1fs)", out_path, time.time() - t0)


if __name__ == "__main__":
    main()
