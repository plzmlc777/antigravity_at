"""Paradigm 192 R-1 PoC: per-sym 30d hour-of-day seasonality z-score spike, 4h bilateral SNT.

Hypothesis
----------
For each (sym, UTC_hour ∈ {00,04,08,12,16,20}), maintain a rolling 30d window
of 4h bar returns AT THAT HOUR ONLY (~30 observations per hour). Compute the
hour's rolling 30d mean return `mu_hour`. Then for each 4h bar at time `t`
with hour H_t, compute the z-score of `mu_hour(H_t)` vs the sym's overall 30d
rolling distribution of 4h bar returns (~180 observations, all hours combined):
  z = (mu_hour - overall_mu) / (overall_sigma / sqrt(n_hour))

Trigger event: |z| >= 2.0 means the bar's hour is statistically distinct (out
of the sym's overall return distribution) — i.e. that hour has developed an
abnormal directional bias (institutional vs retail flow asymmetry signal).

4-quadrant Symmetric Negative Test (bilateral):
  A focus       : z >= +2 (positive hour outperformance) AND bar UP × LONG continuation
  A mirror      : z >= +2 AND bar UP × SHORT reversal
  B same-sign   : z >= +2 AND bar DOWN × SHORT continuation
  B mirror      : z >= +2 AND bar DOWN × LONG reversal (capitulation MR / Lesson #42 dogfood 5)

(NOTE: The trigger axis is z-positive only; the sign-conditioning is on the
CURRENT BAR's price direction, not on the z sign. This gives 4 directionally
distinct quadrants while keeping the seasonality trigger universally positive.)

Three-gate PASS per quadrant:
  signal_t_excess >= 2.0  AND  bootstrap ci_lower > 0  AND  perm_p_one_sided_above <= 0.10

Concentration gate (Lesson #16):
  quarter_pos_t_ratio >= 0.5  AND  symbol_ci_pos_ratio >= 0.30  AND  n_symbols_ci_pos >= 3

Sparse-strict life-changing 4-dim audit (Lesson #71 corollary):
  trades_per_year >= 12  AND  per_trade_edge_pct >= 2.0%
  AND  capital_util_pct >= 30%  AND  annualized_sharpe >= 1.5

Hold sweep: 4h primary, 8h, 12h secondary.

Per-hour contribution analysis: which UTC hours {00,04,08,12,16,20} carry alpha.
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
log = logging.getLogger("p192_r1")

PARADIGM = "alt_per_sym_30d_hour_of_day_seasonality_z_spike_directional_4h_bilateral"
CACHE_DIR = ROOT / "runs/ohlcv_cache_12col"
OUT_DIR = ROOT / "runs/research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "LINK", "LTC", "AVAX", "BCH", "FIL", "NEAR", "WIF"]
UTC_HOURS = [0, 4, 8, 12, 16, 20]

PER_HOUR_WINDOW_OBS = 30   # 30 same-hour observations (~30 days)
OVERALL_WINDOW_BARS = 180  # 180 4h-bars = 30 days
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
    if "close" not in df.columns or "open" not in df.columns:
        log.warning("missing columns in %s", sym)
        return None
    df = df.sort_index()
    return df[["open", "high", "low", "close"]].copy()


def compute_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-sym per-hour rolling 30d mean return + z-score vs overall 30d.

    Returns DataFrame indexed by 4h bar timestamp, with:
      - close, open
      - bar_ret           : (close - open) / open for current bar
      - hour              : UTC hour (0/4/8/12/16/20)
      - mu_hour           : rolling 30d mean return at SAME hour (excludes current bar)
      - mu_all            : rolling 180-bar (30d) mean return all hours (excludes current bar)
      - sigma_all         : rolling 180-bar std return all hours
      - z                 : (mu_hour - mu_all) / (sigma_all / sqrt(n_hour))
    """
    out = pd.DataFrame(index=df.index)
    out["open"] = df["open"].astype(float)
    out["close"] = df["close"].astype(float)
    out["bar_ret"] = (out["close"] - out["open"]) / out["open"]
    out["hour"] = df.index.hour.astype(int)

    # overall rolling stats over all hours (180 bars = 30d)
    # SHIFT(1) to exclude the current bar (causal)
    mu_all = out["bar_ret"].shift(1).rolling(OVERALL_WINDOW_BARS, min_periods=OVERALL_WINDOW_BARS).mean()
    sigma_all = out["bar_ret"].shift(1).rolling(OVERALL_WINDOW_BARS, min_periods=OVERALL_WINDOW_BARS).std()

    # per-hour rolling mean (30 same-hour observations, ~30 days)
    # Approach: per hour group, compute rolling-30 mean, then reindex to full df.
    mu_hour = pd.Series(np.nan, index=out.index, dtype=float)
    for h in UTC_HOURS:
        mask = out["hour"] == h
        sub = out.loc[mask, "bar_ret"]
        # SHIFT(1) inside the per-hour series so the current bar's own return is excluded
        rolled = sub.shift(1).rolling(PER_HOUR_WINDOW_OBS, min_periods=PER_HOUR_WINDOW_OBS).mean()
        mu_hour.loc[mask] = rolled.values

    # z: standardized difference between per-hour rolling mean and overall rolling mean,
    # normalized by std of overall mean estimator (sigma_all / sqrt(n_hour=30))
    z = (mu_hour - mu_all) / (sigma_all / np.sqrt(PER_HOUR_WINDOW_OBS))

    out["mu_hour"] = mu_hour
    out["mu_all"] = mu_all
    out["sigma_all"] = sigma_all
    out["z"] = z
    return out


def compute_forward_returns(close: pd.Series, hold_bars: int) -> pd.Series:
    """Forward close-to-close gross return over hold_bars 4h-bars."""
    return close.shift(-hold_bars) / close - 1.0


def quadrant_trades_per_sym(
    sigs: pd.DataFrame, fwd_ret: pd.Series, quadrant: str, z_sign: str = "pos"
) -> pd.DataFrame:
    """Filter to z-positive triggers, then sign-condition on current bar direction.

    For z_sign='pos': triggers when z >= +Z_THRESHOLD (hour outperforming sym's overall)
    For z_sign='neg': triggers when z <= -Z_THRESHOLD (hour underperforming sym's overall)
                     [used for symmetric mirror diagnostic only; primary uses z_sign='pos']

    Quadrant directions (z_sign='pos'):
      A_focus:  bar_ret > 0 × LONG  (positive hour + bar UP → continuation)
      A_mirror: bar_ret > 0 × SHORT (positive hour + bar UP → reversal)
      B_same:   bar_ret < 0 × SHORT (positive hour + bar DOWN → SHORT continuation)
      B_mirror: bar_ret < 0 × LONG  (positive hour + bar DOWN → LONG capitulation MR)
    """
    df = pd.DataFrame({
        "z": sigs["z"],
        "bar_ret": sigs["bar_ret"],
        "hour": sigs["hour"],
        "gross": fwd_ret,
    }).dropna()

    if z_sign == "pos":
        df = df.loc[df["z"] >= Z_THRESHOLD]
    elif z_sign == "neg":
        df = df.loc[df["z"] <= -Z_THRESHOLD]
    else:
        raise ValueError(f"unknown z_sign {z_sign}")

    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))

    if quadrant == "A_focus":
        df = df.loc[df["bar_ret"] > 0]
        direction = 1.0
    elif quadrant == "A_mirror":
        df = df.loc[df["bar_ret"] > 0]
        direction = -1.0
    elif quadrant == "B_same_sign":
        df = df.loc[df["bar_ret"] < 0]
        direction = -1.0
    elif quadrant == "B_mirror":
        df = df.loc[df["bar_ret"] < 0]
        direction = 1.0
    else:
        raise ValueError(f"unknown quadrant {quadrant}")

    if df.empty:
        return df.assign(direction=pd.Series(dtype=float), net=pd.Series(dtype=float))

    df = df.assign(direction=direction)
    df["net"] = df["direction"] * df["gross"] - FEE_PER_TRADE
    return df


def per_quadrant_eval(per_sym_trades: dict, candidate_pool: list, label: str) -> dict:
    all_net = []
    per_sym_summary = {}
    quarter_t_data = {}
    per_hour_data = {h: [] for h in UTC_HOURS}

    for sym, df in per_sym_trades.items():
        if df is None or df.empty:
            continue
        net_arr = df["net"].values
        all_net.extend(net_arr.tolist())
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
        q_series = df.index.to_series().dt.to_period("Q")
        for q, sub in df.groupby(q_series):
            qkey = str(q)
            quarter_t_data.setdefault(qkey, []).extend(sub["net"].values.tolist())
        # per-hour contribution
        for h in UTC_HOURS:
            sub_h = df.loc[df["hour"] == h]
            if not sub_h.empty:
                per_hour_data[h].extend(sub_h["net"].values.tolist())

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

    ci_agg = bootstrap_ci(all_net_arr, n_boot=2000, block_size=1)

    quadrant_direction = {"A_focus": 1.0, "A_mirror": -1.0, "B_same_sign": -1.0, "B_mirror": 1.0}[label]
    pool_signed = np.asarray(candidate_pool, dtype=float) * quadrant_direction
    perm = fee_aware_perm_test(
        observed_net_returns=all_net_arr,
        candidate_pool_returns=pool_signed,
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )

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

    # per-hour contribution
    per_hour_summary = {}
    for h in UTC_HOURS:
        arr = np.asarray(per_hour_data[h], dtype=float)
        if len(arr) >= 5:
            mn = float(arr.mean())
            sd = arr.std(ddof=1)
            t = mn / sd * np.sqrt(len(arr)) if sd > 0 else 0.0
            per_hour_summary[h] = {
                "n": int(len(arr)),
                "mean_bp": float(mn * 10000),
                "t": float(t),
                "pos_t": bool(t > 0),
            }
        else:
            per_hour_summary[h] = {
                "n": int(len(arr)),
                "mean_bp": float(arr.mean() * 10000) if len(arr) else 0.0,
                "t": 0.0,
                "pos_t": False,
            }

    gate_signal_t = bool(perm["signal_t_excess"] >= 2.0) if not np.isnan(perm["signal_t_excess"]) else False
    gate_ci = bool(ci_agg["ci_lower"] > 0)
    gate_perm = bool(perm["perm_p_one_sided_above"] <= 0.10) if not np.isnan(perm["perm_p_one_sided_above"]) else False
    three_gate_pass = gate_signal_t and gate_ci and gate_perm

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
        "per_hour": per_hour_summary,
        "per_sym": per_sym_summary,
    }


def life_changing_4dim_audit(quadrant_result: dict, hold_bars: int, n_syms: int, total_bars_per_sym: int) -> dict:
    n_trades = quadrant_result.get("n_trades", 0)
    obs_mean = quadrant_result.get("obs_mean_bp", 0.0) / 10000  # net per trade
    obs_std_proxy = None
    # Reconstruct std proxy from obs_t (if available)
    obs_t = quadrant_result.get("obs_t", 0.0)
    if obs_t != 0 and n_trades >= 2:
        obs_std_proxy = obs_mean / (obs_t / np.sqrt(n_trades))
    sigma = abs(obs_std_proxy) if obs_std_proxy else 0.0

    span_years = (total_bars_per_sym * 4) / (24 * 365)  # 4h-bars -> years
    trades_per_year = n_trades / span_years if span_years > 0 else 0.0
    per_trade_edge_pct = obs_mean * 100  # in %
    capital_at_risk_bars = n_trades * hold_bars
    total_capacity = n_syms * total_bars_per_sym
    capital_util_pct = (capital_at_risk_bars / total_capacity) * 100 if total_capacity > 0 else 0.0
    # annualized sharpe: per-trade mean/std × sqrt(trades_per_year)
    annualized_sharpe = (obs_mean / sigma) * np.sqrt(trades_per_year) if sigma > 0 else 0.0

    pass_trades = trades_per_year >= 12
    pass_edge = per_trade_edge_pct >= 2.0
    pass_util = capital_util_pct >= 30.0
    pass_sharpe = annualized_sharpe >= 1.5

    return {
        "n_trades": n_trades,
        "span_years": float(span_years),
        "trades_per_year": float(trades_per_year),
        "per_trade_edge_pct": float(per_trade_edge_pct),
        "capital_util_pct": float(capital_util_pct),
        "annualized_sharpe": float(annualized_sharpe),
        "pass_trades": bool(pass_trades),
        "pass_edge": bool(pass_edge),
        "pass_util": bool(pass_util),
        "pass_sharpe": bool(pass_sharpe),
        "pass_all_4_dim": bool(pass_trades and pass_edge and pass_util and pass_sharpe),
    }


def main():
    log.info("paradigm 192 R-1 starting — 14 syms × 4h × 2.25yr × 6 UTC hours × 4-quadrant SNT × 3 holds")

    # 1) Load + signals
    sym_signals = {}
    sym_raw = {}
    total_bars_per_sym = None
    for sym in SYMS:
        df = load_symbol(sym)
        if df is None:
            continue
        sigs = compute_signals(df)
        sym_signals[sym] = sigs
        sym_raw[sym] = df
        if total_bars_per_sym is None:
            total_bars_per_sym = len(df)
        log.info(
            "  %s: rows=%d valid_z=%d z_p99=%.2f z_p01=%.2f frac_|z|>=2=%.3f",
            sym, len(sigs), int(sigs["z"].notna().sum()),
            float(sigs["z"].quantile(0.99, interpolation="lower")) if sigs["z"].notna().any() else float("nan"),
            float(sigs["z"].quantile(0.01, interpolation="lower")) if sigs["z"].notna().any() else float("nan"),
            float((sigs["z"].abs() >= Z_THRESHOLD).sum() / max(int(sigs["z"].notna().sum()), 1)),
        )

    # 2) Empirical trigger rate diagnostics (Lesson #11/#34)
    n_valid_total = 0
    n_trig_pos_total = 0
    n_trig_neg_total = 0
    for sym, sigs in sym_signals.items():
        z = sigs["z"].dropna()
        n_valid_total += len(z)
        n_trig_pos_total += int((z >= Z_THRESHOLD).sum())
        n_trig_neg_total += int((z <= -Z_THRESHOLD).sum())
    emp_trig_rate_pos = n_trig_pos_total / n_valid_total if n_valid_total else 0.0
    emp_trig_rate_neg = n_trig_neg_total / n_valid_total if n_valid_total else 0.0
    log.info(
        "EMPIRICAL TRIGGER: valid=%d pos|z|>=2=%d (%.3f%%) neg|z|<=-2=%d (%.3f%%)",
        n_valid_total, n_trig_pos_total, emp_trig_rate_pos * 100,
        n_trig_neg_total, emp_trig_rate_neg * 100,
    )

    # 3) Per-hold evaluation, 4-quadrant SNT (z_sign='pos' primary)
    results_all_holds = {}
    for hold_label, hold_bars in HOLDS_BARS.items():
        log.info("=== HOLD %s (%d bars) ===", hold_label, hold_bars)

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
                    sym_signals[sym], per_sym_fwd[sym], quad, z_sign="pos"
                )
                per_sym_trades[sym] = df_q
            r = per_quadrant_eval(per_sym_trades, pool, quad)
            hold_result["quadrants"][quad] = r
            log.info(
                "  %s n=%d obs_t=%.2f sigex=%.2f ci_lo_bp=%.1f perm_p_above=%.3f three_gate=%s conc_gate=%s",
                quad, r.get("n_trades", 0), r.get("obs_t", 0.0),
                r.get("signal_t_excess", float("nan")) if r.get("signal_t_excess") is not None else float("nan"),
                r.get("ci_lower_bp", float("nan")),
                r.get("perm_p_one_sided_above", float("nan")) if r.get("perm_p_one_sided_above") is not None else float("nan"),
                r.get("gates", {}).get("three_gate_pass", False),
                r.get("concentration", {}).get("concentration_gate_pass", False),
            )
        results_all_holds[hold_label] = hold_result

    # 4) Life-changing 4-dim audit (primary hold)
    primary = results_all_holds[PRIMARY_HOLD]
    n_syms_loaded = len(sym_signals)
    lc_audit = {}
    for quad in QUADRANTS:
        lc_audit[quad] = life_changing_4dim_audit(
            primary["quadrants"][quad], HOLDS_BARS[PRIMARY_HOLD], n_syms_loaded, total_bars_per_sym or 4920
        )

    # 5) Off-primary scan (Lesson #37)
    overall_three_gate_pass_cells = []
    overall_full_pass_cells = []
    for hold_label, hres in results_all_holds.items():
        for quad, qres in hres["quadrants"].items():
            if qres.get("gates", {}).get("three_gate_pass"):
                overall_three_gate_pass_cells.append({"hold": hold_label, "quadrant": quad})
                if qres.get("concentration", {}).get("concentration_gate_pass"):
                    overall_full_pass_cells.append({"hold": hold_label, "quadrant": quad})

    # 6) Verdict logic
    n_primary_pass = sum(1 for q in QUADRANTS if primary["quadrants"][q].get("gates", {}).get("three_gate_pass"))
    n_primary_full_pass = 0
    for quad in QUADRANTS:
        qres = primary["quadrants"][quad]
        if (qres.get("gates", {}).get("three_gate_pass")
                and qres.get("concentration", {}).get("concentration_gate_pass")
                and lc_audit[quad]["pass_all_4_dim"]):
            n_primary_full_pass += 1

    if n_primary_pass == 0 and not overall_three_gate_pass_cells:
        verdict = "BROAD_FALSIFIED"
        verdict_reason = "All 4 quadrants × 3 holds three-gate FAIL"
    elif n_primary_full_pass >= 1:
        verdict = "PASS_R1_FULL"
        verdict_reason = f"≥1 primary quadrant: three-gate + Concentration + life-changing 4-dim ALL PASS"
    elif n_primary_pass >= 1:
        # three-gate PASS but failed Concentration or LC4-dim
        any_conc_pass = any(
            primary["quadrants"][q].get("concentration", {}).get("concentration_gate_pass") for q in QUADRANTS
        )
        any_lc_pass = any(lc_audit[q]["pass_all_4_dim"] for q in QUADRANTS)
        if any_conc_pass and not any_lc_pass:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_reason = "three-gate + Conc PASS but life-changing 4-dim FAIL"
        elif not any_conc_pass:
            verdict = "CONCENTRATED_R1_PASS"
            verdict_reason = "three-gate PASS but Concentration FAIL"
        else:
            verdict = "PARTIAL_R1_PASS"
            verdict_reason = "three-gate PASS; LC4-dim+Conc not jointly satisfied"
    elif overall_three_gate_pass_cells:
        verdict = "BROAD_FALSIFIED_PRIMARY_OFF_PRIMARY_CELL_PASS"
        verdict_reason = f"Primary all FAIL; off-primary PASS: {overall_three_gate_pass_cells}"
    else:
        verdict = "BROAD_FALSIFIED"
        verdict_reason = "All cells FAIL"

    # 7) Lesson #42 dogfood 5th — B mirror cell
    b_mirror_primary = primary["quadrants"]["B_mirror"]
    b_same_primary = primary["quadrants"]["B_same_sign"]
    lesson42_check = {
        "B_mirror_three_gate_pass": b_mirror_primary.get("gates", {}).get("three_gate_pass", False),
        "B_same_sign_three_gate_pass": b_same_primary.get("gates", {}).get("three_gate_pass", False),
        "B_mirror_conc_gate_pass": b_mirror_primary.get("concentration", {}).get("concentration_gate_pass", False),
        "B_mirror_lc4dim_pass": lc_audit["B_mirror"]["pass_all_4_dim"],
        "lesson42_5th_dogfood_pattern_partial": bool(
            b_mirror_primary.get("gates", {}).get("three_gate_pass", False)
            and not b_same_primary.get("gates", {}).get("three_gate_pass", False)
        ),
        "lesson42_5th_dogfood_full_pass": bool(
            b_mirror_primary.get("gates", {}).get("three_gate_pass", False)
            and b_mirror_primary.get("concentration", {}).get("concentration_gate_pass", False)
            and lc_audit["B_mirror"]["pass_all_4_dim"]
        ),
    }

    output = {
        "paradigm": PARADIGM,
        "paradigm_counter": 192,
        "phase": "R-1",
        "universe": [f"{s}USDT" for s in SYMS],
        "n_syms": n_syms_loaded,
        "trigger": {
            "statistic": "(mu_hour_30d - mu_all_30d) / (sigma_all_30d / sqrt(30))",
            "per_hour_window_obs": PER_HOUR_WINDOW_OBS,
            "overall_window_bars": OVERALL_WINDOW_BARS,
            "z_threshold_abs": Z_THRESHOLD,
            "z_sign_primary": "pos",
            "utc_hours": UTC_HOURS,
        },
        "empirical_trigger": {
            "n_valid_total": int(n_valid_total),
            "n_pos_trig": int(n_trig_pos_total),
            "n_neg_trig": int(n_trig_neg_total),
            "pos_rate": float(emp_trig_rate_pos),
            "neg_rate": float(emp_trig_rate_neg),
        },
        "fee_per_trade": FEE_PER_TRADE,
        "holds_tested": list(HOLDS_BARS.keys()),
        "primary_hold": PRIMARY_HOLD,
        "results": results_all_holds,
        "life_changing_4dim": lc_audit,
        "summary": {
            "verdict": verdict,
            "verdict_reason": verdict_reason,
            "primary_hold_quadrants_three_gate_pass": n_primary_pass,
            "primary_hold_quadrants_full_pass": n_primary_full_pass,
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
