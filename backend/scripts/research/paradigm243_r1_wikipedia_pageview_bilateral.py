"""Paradigm #243 R-1 PoC — Wikipedia page-view attention spike bilateral 1d-3d.

Design
------
- Universe: 10 Binance USDT-perp symbols with ≥500 days of Wikipedia data.
- Signal: per-symbol rolling 30d z-score of log(page_views + 1), computed on
  each calendar UTC day; observed strictly on day D based on data ≤ D.
- Entry: day D+1 close (avoids intraday look-ahead — the day-D view count is
  only complete after end of UTC day D).
- Hold: 1d / 2d / 3d (Lesson #37 sweep).
- 4-quadrant Symmetric Negative Test (Lesson #19):
    A_focus:  z ≥ +1.5 → LONG
    A_mirror: z ≥ +1.5 → SHORT
    B_focus:  z ≤ -1.5 → SHORT
    B_mirror: z ≤ -1.5 → LONG
- Fee: 8 bp one-way => 16 bp round-trip subtracted from gross.
- Statistics: fee_aware_perm_test + bootstrap_ci from _perm_utils.
- Concentration gates:
    * n_pos_t_quarters / n_measurable_quarters >= 0.5 (Lesson #16)
    * syms_ci_pos / n_syms >= 0.30 (>=4/10) (Lesson #16)
    * n_measurable_quarters >= 4 (Lesson #26)
- Life-changing 4-dim reported for best cell (Lesson #41).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import joblib

# ensure repo root on path
sys.path.insert(0, "/home/mint/auto_trading/backend")
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p243_r1")

PARADIGM = "alt_wikipedia_pageview_attention_spike_bilateral_1d_to_3d"
ROOT = Path("/home/mint/auto_trading/backend")
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
CACHE_PATH = OUT_DIR / "wiki_views_cache.json"
METRICS_PATH = OUT_DIR / "r1__metrics.json"
OHLCV_DIR = ROOT / "runs" / "ohlcv_cache"

FEE_RTRIP = 0.0016          # 16 bp round-trip
Z_HI = 1.5
Z_LO = -1.5
HOLDS = [1, 2, 3]           # in days
Z_WINDOW = 30


def _t_stat(arr: np.ndarray) -> float:
    n = len(arr)
    if n < 2:
        return 0.0
    sd = arr.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(arr.mean() / sd * np.sqrt(n))


def load_wiki_frame() -> pd.DataFrame:
    with CACHE_PATH.open() as f:
        raw = json.load(f)
    frames = []
    for sym, rec in raw.items():
        rows = rec.get("rows") or []
        if len(rows) < 500:
            continue
        s = pd.Series({pd.Timestamp(ts): int(v) for ts, v in rows},
                      name=sym).sort_index()
        frames.append(s)
    df = pd.concat(frames, axis=1)
    return df


def load_daily_close(sym: str) -> pd.Series:
    df = joblib.load(OHLCV_DIR / f"{sym}_1m.joblib")
    close = df["close"].astype(float)
    return close.resample("1D").last().dropna()


def compute_z(views: pd.Series) -> pd.Series:
    lv = np.log(views.astype(float).clip(lower=1) + 1.0)
    m = lv.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    s = lv.rolling(Z_WINDOW, min_periods=Z_WINDOW).std(ddof=1)
    return (lv - m) / s.replace(0, np.nan)


def build_forward_returns(close: pd.Series, hold: int) -> pd.Series:
    """Return series of hold-day forward log returns aligned by entry-day close.

    Entry at close of day D+1 (day after the observation day). Exit at close
    of day D+1+hold. Return series indexed by observation day D (so we can
    align with z-scores computed on data up through day D).
    """
    # entry price at close of day D+1, exit at close of day D+1+hold
    entry = close.shift(-1)
    exit_ = close.shift(-(1 + hold))
    fwd = (exit_ / entry) - 1.0
    return fwd.rename("fwd")


def per_quadrant_stats(observed_net: np.ndarray,
                       pool_gross: np.ndarray) -> Dict[str, float]:
    if len(observed_net) < 5 or len(pool_gross) < 20:
        return {"n_obs": int(len(observed_net)), "note": "too few observations"}
    perm = fee_aware_perm_test(observed_net_returns=observed_net,
                               candidate_pool_returns=pool_gross,
                               fee_per_trade=FEE_RTRIP,
                               n_perms=1000,
                               rng_seed=42)
    ci = bootstrap_ci(observed_net, n_boot=2000, block_size=1)
    return {
        "n_obs": int(len(observed_net)),
        "n_pool": int(len(pool_gross)),
        "gross_mean_bp": float(np.mean(observed_net + FEE_RTRIP) * 1e4),
        "net_mean_bp": float(np.mean(observed_net) * 1e4),
        "net_median_bp": float(np.median(observed_net) * 1e4),
        "obs_t": perm["obs_t"],
        "null_mean_t": perm["null_mean_t"],
        "signal_t_excess": perm["signal_t_excess"],
        "perm_p_two_sided": perm["perm_p_two_sided"],
        "perm_p_one_sided_below": perm["perm_p_one_sided_below"],
        "perm_p_one_sided_above": perm["perm_p_one_sided_above"],
        "ci_lower_bp": ci["ci_lower"] * 1e4,
        "ci_upper_bp": ci["ci_upper"] * 1e4,
        "ci_mean_bp": ci["mean"] * 1e4,
        "ci_prob_positive": ci["prob_positive"],
    }


def compute_concentration(per_trade_df: pd.DataFrame) -> Dict[str, object]:
    """per_trade_df has columns: sym, entry_ts, net_ret. Returns per-quarter and
    per-symbol diagnostics."""
    if per_trade_df.empty:
        return {"n_quarters_measurable": 0, "n_pos_t_quarters": 0,
                "quarter_pos_t_ratio": 0.0, "n_syms_ci_pos": 0,
                "n_syms": 0, "syms_ci_pos_ratio": 0.0,
                "per_quarter": {}, "per_symbol": {}}
    df = per_trade_df.copy()
    df["quarter"] = df["entry_ts"].dt.to_period("Q").astype(str)
    per_q: Dict[str, dict] = {}
    for q, g in df.groupby("quarter"):
        arr = g["net_ret"].values
        if len(arr) < 5:
            continue
        per_q[q] = {"n": int(len(arr)),
                    "t": _t_stat(arr),
                    "mean_bp": float(arr.mean() * 1e4)}
    n_measurable = len(per_q)
    n_pos_t = sum(1 for v in per_q.values() if v["t"] > 0)
    per_s: Dict[str, dict] = {}
    for s, g in df.groupby("sym"):
        arr = g["net_ret"].values
        if len(arr) < 5:
            continue
        ci = bootstrap_ci(arr, n_boot=1000, block_size=1)
        per_s[s] = {"n": int(len(arr)),
                    "mean_bp": float(arr.mean() * 1e4),
                    "ci_lower_bp": float(ci["ci_lower"] * 1e4),
                    "ci_pos": ci["ci_lower"] > 0}
    n_syms_ci_pos = sum(1 for v in per_s.values() if v["ci_pos"])
    n_syms = len(per_s)
    return {
        "n_quarters_measurable": n_measurable,
        "n_pos_t_quarters": n_pos_t,
        "quarter_pos_t_ratio": (n_pos_t / n_measurable) if n_measurable else 0.0,
        "n_syms_ci_pos": n_syms_ci_pos,
        "n_syms": n_syms,
        "syms_ci_pos_ratio": (n_syms_ci_pos / n_syms) if n_syms else 0.0,
        "per_quarter": per_q,
        "per_symbol": per_s,
    }


def run_quadrant(views_df: pd.DataFrame,
                 close_by_sym: Dict[str, pd.Series],
                 z_by_sym: Dict[str, pd.Series],
                 quadrant: str,
                 hold: int) -> Dict[str, object]:
    """Compute per-trade net returns and pool of candidate gross returns
    across all symbols for one quadrant × one hold horizon."""
    obs_rows: List[Tuple[str, pd.Timestamp, float]] = []
    pool_gross_all: List[float] = []
    for sym, z in z_by_sym.items():
        close = close_by_sym.get(sym)
        if close is None or z is None:
            continue
        fwd = build_forward_returns(close, hold)  # indexed by observation day
        df = pd.concat([z.rename("z"), fwd.rename("fwd")], axis=1).dropna()
        if df.empty:
            continue
        if quadrant.startswith("A"):
            mask = df["z"] >= Z_HI
        else:
            mask = df["z"] <= Z_LO
        if quadrant.endswith("_focus"):
            direction = +1 if quadrant.startswith("A") else -1
        else:  # _mirror
            direction = -1 if quadrant.startswith("A") else +1
        events = df.loc[mask]
        if events.empty:
            continue
        gross = direction * events["fwd"].values
        net = gross - FEE_RTRIP
        for ts, r_net in zip(events.index, net):
            obs_rows.append((sym, ts, float(r_net)))
        # candidate pool: all rows in df (with same direction applied)
        pool_gross_all.extend((direction * df["fwd"].values).tolist())

    per_trade_df = pd.DataFrame(obs_rows,
                                columns=["sym", "entry_ts", "net_ret"])
    if per_trade_df.empty:
        return {"quadrant": quadrant, "hold_days": hold, "n_events": 0,
                "note": "no events"}

    observed_net = per_trade_df["net_ret"].values
    pool_gross = np.asarray(pool_gross_all)
    stats = per_quadrant_stats(observed_net, pool_gross)
    conc = compute_concentration(per_trade_df)

    # Three-gate
    three_gate_pass = (
        stats.get("signal_t_excess", -99) >= 2.0
        and stats.get("ci_lower_bp", -99) > 0
        and stats.get("perm_p_two_sided", 1) <= 0.10
    )
    # Concentration gate
    conc_pass = (
        conc["syms_ci_pos_ratio"] >= 0.30
        and conc["quarter_pos_t_ratio"] >= 0.5
        and conc["n_quarters_measurable"] >= 4
    )

    return {
        "quadrant": quadrant,
        "hold_days": hold,
        "stats": stats,
        "concentration": conc,
        "three_gate_pass": bool(three_gate_pass),
        "concentration_pass": bool(conc_pass),
        "overall_pass": bool(three_gate_pass and conc_pass),
    }


def life_changing_4d(cell: dict, years: float) -> Dict[str, float]:
    n = cell["stats"].get("n_obs", 0)
    if n == 0 or years <= 0:
        return {"trades_per_year": 0, "edge_pct": 0, "util": 0, "sharpe": 0}
    edge = cell["stats"].get("net_mean_bp", 0) / 100.0  # bp -> %
    trades_yr = n / years
    hold = cell["hold_days"]
    util = trades_yr * hold / 365.0
    # simple sharpe estimate on daily-eq returns
    n_obs = cell["stats"]["n_obs"]
    obs_t = cell["stats"].get("obs_t", 0)
    ann_sharpe = obs_t / (n_obs ** 0.5) * (trades_yr ** 0.5) if n_obs else 0
    return {
        "trades_per_year": trades_yr,
        "edge_pct_per_trade": edge,
        "util": util,
        "ann_sharpe_est": ann_sharpe,
    }


def main() -> None:
    log.info("=== paradigm #243 R-1 PoC: %s ===", PARADIGM)
    views_df = load_wiki_frame()
    syms = list(views_df.columns)
    log.info("universe (%d syms): %s", len(syms), syms)

    close_by_sym: Dict[str, pd.Series] = {}
    z_by_sym: Dict[str, pd.Series] = {}
    for sym in syms:
        try:
            close = load_daily_close(sym)
        except Exception as e:
            log.warning("skip %s daily close: %s", sym, e)
            continue
        close_by_sym[sym] = close
        z_by_sym[sym] = compute_z(views_df[sym].dropna())
    log.info("loaded daily closes for %d symbols", len(close_by_sym))

    # years covered: use views df date span
    start = views_df.index.min()
    end = views_df.index.max()
    years = (end - start).days / 365.25
    log.info("date span: %s..%s (%.2f years)", start.date(), end.date(), years)

    quadrants = ["A_focus", "A_mirror", "B_focus", "B_mirror"]
    results: List[dict] = []
    for quad in quadrants:
        for hold in HOLDS:
            log.info(">>> quadrant=%s hold=%dd", quad, hold)
            cell = run_quadrant(views_df, close_by_sym, z_by_sym, quad, hold)
            cell["life_changing_4d"] = life_changing_4d(cell, years)
            results.append(cell)
            if "stats" in cell:
                s = cell["stats"]
                log.info("  n=%d gross=%.1fbp net=%.1fbp t=%.2f "
                         "excess=%.2f ci_low=%.1fbp perm_p=%.3f",
                         s.get("n_obs", 0),
                         s.get("gross_mean_bp", 0),
                         s.get("net_mean_bp", 0),
                         s.get("obs_t", 0),
                         s.get("signal_t_excess", 0),
                         s.get("ci_lower_bp", 0),
                         s.get("perm_p_two_sided", 0))
                log.info("  conc: syms_ci_pos=%d/%d q_pos_t=%d/%d "
                         "3gate=%s conc=%s OVERALL=%s",
                         cell["concentration"]["n_syms_ci_pos"],
                         cell["concentration"]["n_syms"],
                         cell["concentration"]["n_pos_t_quarters"],
                         cell["concentration"]["n_quarters_measurable"],
                         cell["three_gate_pass"],
                         cell["concentration_pass"],
                         cell["overall_pass"])

    # Full sweep verdict scan (Lesson #37)
    any_full_pass = any(c.get("overall_pass") for c in results)
    any_three_gate = any(c.get("three_gate_pass") for c in results)
    pass_cells = [f"{c['quadrant']}/{c['hold_days']}d"
                  for c in results if c.get("overall_pass")]
    three_gate_only = [f"{c['quadrant']}/{c['hold_days']}d"
                       for c in results
                       if c.get("three_gate_pass")
                       and not c.get("concentration_pass")]

    if any_full_pass:
        verdict = "R1_PASS"
    elif any_three_gate:
        verdict = "R1_CONCENTRATED_R1_PASS"
    else:
        verdict = "R1_GRAVEYARD"

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1",
        "verdict": verdict,
        "years_covered": years,
        "universe": syms,
        "fee_round_trip": FEE_RTRIP,
        "z_threshold_hi": Z_HI,
        "z_threshold_lo": Z_LO,
        "holds": HOLDS,
        "z_window_days": Z_WINDOW,
        "full_sweep_results": results,
        "cells_overall_pass": pass_cells,
        "cells_three_gate_only": three_gate_only,
    }
    METRICS_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("=== R-1 verdict: %s ===", verdict)
    log.info("full-pass cells: %s", pass_cells)
    log.info("3-gate-only cells: %s", three_gate_only)
    log.info("metrics -> %s", METRICS_PATH)


if __name__ == "__main__":
    main()
