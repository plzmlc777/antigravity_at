"""Paradigm 193 R-1 — per-sym 30d max drawdown depth z-spike, bilateral 4-quadrant SNT.

Hypothesis:
    Per-sym 4h candle close → 30d rolling MAX drawdown depth (peak-to-trough),
    z-scored over 90d. z>=+2 = "this sym is in its deepest drawdown vs own 90d norm".
    4 quadrants split by concurrent bar direction:
        A_focus  : z>=+2 × bar UP   × LONG  (drawdown bottom + initial recovery LONG)
        A_mirror : z>=+2 × bar UP   × SHORT (false dawn fade)
        B_same   : z>=+2 × bar DOWN × SHORT (capitulation cascade continuation)
        B_mirror : z>=+2 × bar DOWN × LONG  (capitulation MR — Lesson #42 5th dogfood)

Substrate:
    backend/runs/ohlcv_cache_12col/{SYM}USDT_4h.joblib × 14 syms × 2.25yr (4920 4h bars).

Sample density (empirically measured pre-dispatch):
    z>=+2 raw triggers: 3552 (rate 6.04%)
    24h-debounced: 760 events
    Bar-UP: 224, Bar-DOWN: 536
    A per-quarter ~24.9 (MARGINAL aggregate-only), B per-quarter ~59.6 (PASS).

Lesson refs:
    #11 sample density (prescreen passed)
    #19 4-quadrant SNT joint-trigger mandatory (here unary trigger split by bar dir)
    #21 axis-stacking — single derived statistic, PASS
    #26 temporal walk-forward (R-2 concern, not R-1)
    #34 empirical distribution prescreen (done)
    #40 structural threshold (dd_abs non-negative; z<=-T skipped, primary z>=+T)
    #42 5th dogfood B_mirror cell capitulation MR universal scope test
    #61 slug grep audit — paradigm 117 statistic class distinct (24h absolute vs 30d rolling z)
    #62 5/5 family-distinct strict
    #67/68/70 ESCAPE verified
    #69 5-item summary
    #71 sparse-strict mode (per-trade edge ≥ 2%)
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
log = logging.getLogger("paradigm193_r1")

PARADIGM = "alt_per_sym_30d_drawdown_depth_z_spike_directional_4h_bilateral"
CACHE_DIR = REPO_ROOT / "runs" / "ohlcv_cache_12col"
OUT_DIR = REPO_ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX",
        "LINK", "LTC", "BCH", "NEAR", "FIL", "WIF"]

WIN_30D = 30 * 6   # 180 bars (4h)
WIN_90D = 90 * 6   # 540 bars
DEBOUNCE_BARS = 6  # 24h debounce
Z_THRESH = 2.0     # primary trigger threshold

HOLD_BARS = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}
PRIMARY_HOLD = "4h"

FEE_RT = 0.0008  # 8 bp round-trip


def compute_signal(close: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (z_dd, bar_ret, valid_mask).

    z_dd : 90d z-score of 30d rolling max drawdown depth (positive = deeper)
    bar_ret : 1-bar (4h) return
    valid_mask : both windows filled
    """
    rolling_peak = pd.Series(close).rolling(WIN_30D, min_periods=WIN_30D).max().values
    dd_abs = -(close - rolling_peak) / rolling_peak  # non-negative; 0 at peak
    ser = pd.Series(dd_abs)
    z = ((ser - ser.rolling(WIN_90D, min_periods=WIN_90D).mean())
         / ser.rolling(WIN_90D, min_periods=WIN_90D).std()).values
    bar_ret = np.diff(close, prepend=np.nan) / np.roll(close, 1)
    bar_ret[0] = np.nan
    valid = ~np.isnan(z) & ~np.isnan(bar_ret)
    return z, bar_ret, valid


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

        # Candidate pool: all valid (non-trigger or trigger) forward-hold returns
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

    # fee-aware permutation
    perm = fee_aware_perm_test(
        observed_net_returns=trades_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=1000,
        rng_seed=42,
    )

    # bootstrap CI (in bp)
    boot = bootstrap_ci(trades_net, n_boot=2000, block_size=1, alpha=0.05, rng_seed=42)
    ci_lower_bp = boot["ci_lower"] * 1e4
    ci_upper_bp = boot["ci_upper"] * 1e4
    prob_pos = boot.get("prob_positive", float("nan"))

    # Per-quarter pos t
    df_meta = pd.DataFrame(trades_meta, columns=["sym", "ts", "gross"])
    df_meta["net"] = df_meta["gross"] - (FEE_RT if direction_long else FEE_RT)
    # adjust net if direction short: gross already inverted; just subtract fee
    df_meta["net"] = df_meta["gross"] - FEE_RT
    df_meta["quarter"] = df_meta["ts"].dt.to_period("Q").astype(str)
    quarter_stats = []
    for q, sub in df_meta.groupby("quarter"):
        if len(sub) < 5:
            quarter_stats.append(dict(quarter=q, n=len(sub), t=float("nan"), mean_bp=float(sub["net"].mean() * 1e4), measurable=False))
            continue
        t = t_stat(sub["net"].values)
        quarter_stats.append(dict(quarter=q, n=len(sub), t=t,
                                   mean_bp=float(sub["net"].mean() * 1e4),
                                   measurable=True))
    n_q_measurable = sum(1 for q in quarter_stats if q["measurable"])
    n_q_pos_t = sum(1 for q in quarter_stats if q["measurable"] and q["t"] > 0)
    quarter_pos_t_ratio = n_q_pos_t / max(n_q_measurable, 1)

    # Per-sym bootstrap CI
    syms_stats = []
    n_syms_ci_pos = 0
    n_syms_measurable = 0
    for sym in sorted(df_meta["sym"].unique()):
        sub = df_meta[df_meta["sym"] == sym]
        if len(sub) < 5:
            syms_stats.append(dict(sym=sym, n=int(len(sub)), mean_bp=float(sub["net"].mean() * 1e4) if len(sub) else 0.0, ci_lower_bp=float("nan"), ci_pos=False, measurable=False))
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

    # Three-gate (Research Track standard)
    signal_t_excess = perm.get("signal_t_excess", float("nan"))
    perm_p_one_above = perm.get("perm_p_one_sided_above", float("nan"))
    gate1 = (not np.isnan(signal_t_excess)) and signal_t_excess >= 2.0
    gate2 = (not np.isnan(ci_lower_bp)) and ci_lower_bp > 0
    gate3 = (not np.isnan(perm_p_one_above)) and perm_p_one_above <= 0.10
    three_gate_pass = bool(gate1 and gate2 and gate3)

    # Concentration Gate (Lesson #16)
    conc_pass = (
        quarter_pos_t_ratio >= 0.5
        and syms_ci_pos_ratio >= 0.30
        and n_syms_ci_pos >= 3
    )

    # life-changing 4-dim (rough estimate using only this hold's events)
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

    results = {"paradigm": PARADIGM, "host": "hcp_local", "fee_rt": FEE_RT,
               "z_threshold": Z_THRESH, "debounce_bars": DEBOUNCE_BARS,
               "syms_universe": SYMS, "primary_hold": PRIMARY_HOLD,
               "holds": list(HOLD_BARS.keys())}

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
                log.info("    n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f perm_p_above=%s ci_lower=%.2fbp three_gate=%s conc=%s lc4=%s",
                         n, cell["obs_mean_gross_bp"], cell["obs_mean_net_bp"], cell["obs_t"],
                         cell["signal_t_excess"],
                         f"{cell['perm_p_one_sided_above']:.3f}" if cell['perm_p_one_sided_above'] is not None else "NA",
                         cell["ci_lower_bp"], cell["three_gate_pass"], cell["concentration_gate_pass"],
                         cell["life_changing_4dim"]["passes"])
    results["cells"] = cells

    # Summary: best cell across hold sweep
    best = None
    for k, c in cells.items():
        if c.get("n_trades", 0) < 30:
            continue
        sigex = c.get("signal_t_excess", float("nan"))
        if np.isnan(sigex):
            continue
        if best is None or sigex > best[1]:
            best = (k, sigex, c)
    results["best_cell"] = dict(key=best[0], signal_t_excess=best[1]) if best else None

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("wrote %s (elapsed %.1fs)", out_path, time.time() - t0)


if __name__ == "__main__":
    main()
