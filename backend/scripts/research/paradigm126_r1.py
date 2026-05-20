"""paradigm 126 R-1 PoC — alt_volume_burst_intra5m_event_signed_directional_30m.

R-1 full panel measurement with 4-quadrant Symmetric Negative Test (Lesson #19).

Trigger: 1m volume > 30d rolling p99 (per-symbol) AND |1m_log_ret| > 0.5%
Direction: sign(1m_log_ret on burst minute) momentum continuation
Forward hold: 30 min
Universe: 13 active alts (ADA 143d short-window advisory per R-0 Lesson #30)
Fee: 16bp round-trip

Lessons applied:
  #11 sample density (PASS at R-0: pos 10/10 q, neg 10/10 q measurable, n=28k bursts)
  #16 Concentration Gate (q_pos_t_ratio + symbol_ci_pos_ratio + n_syms_ci_pos)
  #19 SNT 4-quadrant single batch
  #22 frame-grade (1m DB direct, 2.77M panel 5m bars)
  #30 data window advisory (ADAUSDT 143d only -- include but flag)
  #34 empirical distribution
  #39 sub-class A/B/C manual detection
  #41 AMENDMENT edge ≥ 2% gate FIRST + DIFFUSE_POSITIVE SECOND
  #43 trap awareness (novelty axes ≠ mechanism alpha)
  #44 amendment graveyard cross-reference (10th dogfood — see R-0 prescreen for full xref)
  #45 family-distinct (empirical p99, not unsupervised)
  #46 AMENDMENT REFINEMENT (R-0 stratified PASSED; verify inflation ratio at R-1)
  #48 candidate (brief inventory scope cross-reference applied at R-0)
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

# Ensure local helper import path
sys.path.insert(0, "/home/hcpark/antigravity/backend")
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p126_r1")

PARADIGM_NAME = "alt_volume_burst_intra5m_event_signed_directional_30m"
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# From R-0 prescreen (PASS)
ROLLING_DAYS = 30
ROLLING_BAR_WINDOW = ROLLING_DAYS * 24 * 60
PERCENTILE_VOLUME = 99.0
MAG_THRESHOLD = 0.005
FORWARD_HOLD_BARS_1M = 30  # 30 min
FEE_BP = 16.0
FEE_FRAC = FEE_BP / 10000.0
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df


def _t_stat(arr) -> float:
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n < 2:
        return 0.0
    sd = arr.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(arr.mean() / sd * math.sqrt(n))


def per_quadrant_stats(net_bp: pd.Series, gross_bp: pd.Series, syms: pd.Series, qtrs: pd.Series) -> dict:
    n = int(len(net_bp))
    if n < 30:
        return {"n": n, "skip": True}
    gross_mean = float(gross_bp.mean())
    net_mean = float(net_bp.mean())
    obs_t = _t_stat(net_bp.values)

    # per-quarter t-stats
    q_t_stats = {}
    for q in qtrs.unique():
        sub = net_bp[qtrs == q]
        if len(sub) >= 30:
            q_t_stats[q] = _t_stat(sub.values)
    n_q_measurable = len(q_t_stats)
    n_q_pos_t = sum(1 for t in q_t_stats.values() if t > 0)
    q_pos_t_ratio = n_q_pos_t / n_q_measurable if n_q_measurable else 0.0

    # per-symbol bootstrap CI (Lesson #16)
    sym_ci_pos = []
    sym_results = {}
    for s in syms.unique():
        sub_net = net_bp[syms == s]
        if len(sub_net) >= 30:
            ci = bootstrap_ci(sub_net.values / 10000.0, n_boot=500, block_size=10, rng_seed=42)
            ci_lower_bp = float(ci["ci_lower"]) * 10000
            sym_results[s] = {
                "n": int(len(sub_net)),
                "gross_bp": float(gross_bp[syms == s].mean()),
                "net_bp": float(sub_net.mean()),
                "ci_lower_bp": ci_lower_bp,
                "ci_pos": bool(ci_lower_bp > 0),
            }
            if ci_lower_bp > 0:
                sym_ci_pos.append(s)
    n_syms_measurable = len(sym_results)
    n_syms_ci_pos = len(sym_ci_pos)
    syms_ci_pos_ratio = n_syms_ci_pos / n_syms_measurable if n_syms_measurable else 0.0

    return {
        "n": n,
        "n_symbols": int(syms.nunique()),
        "gross_bp_mean": gross_mean,
        "net_bp_mean": net_mean,
        "obs_t": obs_t,
        "per_quarter_t": q_t_stats,
        "n_q_measurable": n_q_measurable,
        "n_q_pos_t": n_q_pos_t,
        "q_pos_t_ratio": q_pos_t_ratio,
        "per_symbol": sym_results,
        "n_syms_measurable": n_syms_measurable,
        "syms_ci_pos": sym_ci_pos,
        "n_syms_ci_pos": n_syms_ci_pos,
        "syms_ci_pos_ratio": syms_ci_pos_ratio,
    }


def evaluate_quadrant(quad_label: str, net_bp: pd.Series, candidate_pool_gross_bp: np.ndarray,
                      syms: pd.Series, qtrs: pd.Series, gross_bp: pd.Series, panel_years: float) -> dict:
    n = len(net_bp)
    if n < 30:
        return {"label": quad_label, "n": n, "skip": True}

    obs_t = _t_stat(net_bp.values)

    fee_result = fee_aware_perm_test(
        observed_net_returns=net_bp.values / 10000.0,
        candidate_pool_returns=candidate_pool_gross_bp / 10000.0,
        fee_per_trade=FEE_FRAC,
        n_perms=1000,
        rng_seed=42,
    )
    signal_t_excess = float(fee_result.get("signal_t_excess", float("nan")))
    null_mean_t = float(fee_result.get("null_mean_t", float("nan")))
    perm_p_two = float(fee_result.get("perm_p_two_sided", float("nan")))
    perm_p_above = float(fee_result.get("perm_p_one_sided_above", float("nan")))

    ci = bootstrap_ci(net_bp.values / 10000.0, n_boot=2000, block_size=20, rng_seed=42)
    ci_lower_bp = float(ci["ci_lower"]) * 10000
    ci_upper_bp = float(ci["ci_upper"]) * 10000
    prob_pos = float(ci.get("prob_positive", float("nan")))

    detail = per_quadrant_stats(net_bp, gross_bp, syms, qtrs)

    # 3-gate
    gate_excess = bool(signal_t_excess >= 2.0) if not math.isnan(signal_t_excess) else False
    gate_ci = bool(ci_lower_bp > 0)
    gate_perm = bool(perm_p_above <= 0.10) if not math.isnan(perm_p_above) else False
    three_gate_pass = gate_excess and gate_ci and gate_perm

    # Concentration gate (Lesson #16)
    qpos_ratio = detail.get("q_pos_t_ratio", 0.0)
    sci_ratio = detail.get("syms_ci_pos_ratio", 0.0)
    n_sci = detail.get("n_syms_ci_pos", 0)
    concentration_pass = bool(qpos_ratio >= 0.5 and sci_ratio >= 0.30 and n_sci >= 3)

    # Lesson #41 AMENDMENT edge-first gate
    trades_per_year = n / panel_years
    per_trade_edge_pct = detail["net_bp_mean"] / 100.0
    edge_first_gate = bool(per_trade_edge_pct >= 2.0)

    return {
        "label": quad_label,
        "n": detail["n"],
        "n_symbols": detail["n_symbols"],
        "gross_bp": detail["gross_bp_mean"],
        "net_bp": detail["net_bp_mean"],
        "obs_t": obs_t,
        "null_mean_t": null_mean_t,
        "signal_t_excess": signal_t_excess,
        "ci_lower_bp": ci_lower_bp,
        "ci_upper_bp": ci_upper_bp,
        "prob_positive": prob_pos,
        "perm_p_two_sided": perm_p_two,
        "perm_p_one_sided_above": perm_p_above,
        "gate_excess": gate_excess,
        "gate_ci": gate_ci,
        "gate_perm": gate_perm,
        "three_gate_pass": three_gate_pass,
        "q_pos_t_ratio": qpos_ratio,
        "n_syms_ci_pos": n_sci,
        "syms_ci_pos_ratio": sci_ratio,
        "n_syms_measurable": detail["n_syms_measurable"],
        "concentration_pass": concentration_pass,
        "per_quarter_t": detail["per_quarter_t"],
        "per_symbol": detail["per_symbol"],
        "trades_per_year_approx": trades_per_year,
        "per_trade_edge_pct": per_trade_edge_pct,
        "edge_first_gate_lesson41": edge_first_gate,
    }


def main():
    log.info("paradigm 126 R-1 start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    log.info("--- Step 1: Load 1m OHLCV per symbol ---")
    sym_data = {}
    per_sym_days = {}
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < ROLLING_BAR_WINDOW * 2:
                log.warning("%s: insufficient 1m bars (%d) — skip", sym, len(df))
                continue
            sym_data[sym] = df
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            log.info("%s: %d 1m bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded")
        sys.exit(1)

    full_window = max(per_sym_days.values())
    panel_years = full_window / 365.0
    log.info("full_window=%d days = %.2f years", full_window, panel_years)

    log.info("--- Step 2: 1m volume p99 rolling + magnitude filter + 5m frame aggregation ---")
    panel_rows = []
    for sym, j in sym_data.items():
        j = j.copy()
        j["log_ret_1m"] = np.log(j["close"]).diff()
        j["abs_log_ret_1m"] = j["log_ret_1m"].abs()
        j["vol_p99_30d"] = j["volume"].rolling(
            window=ROLLING_BAR_WINDOW, min_periods=ROLLING_BAR_WINDOW // 2
        ).quantile(0.99)
        j["burst"] = (
            (j["volume"] > j["vol_p99_30d"])
            & (j["abs_log_ret_1m"] > MAG_THRESHOLD)
        ).astype(int)
        j["burst_sign"] = np.where(j["burst"] == 1, np.sign(j["log_ret_1m"]), 0).astype(int)
        j["fwd_ret_30m"] = j["close"].pct_change(FORWARD_HOLD_BARS_1M).shift(-FORWARD_HOLD_BARS_1M)
        j["sym"] = sym

        # 5m aggregation: first burst sign within 5m bin (preserve cardinality of 5m frame)
        j_5m = j.resample("5min").agg({
            "burst": "max",
            "burst_sign": (lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0),
            "abs_log_ret_1m": "max",
            "fwd_ret_30m": "first",
            "close": "last",
            "sym": "first",
        })
        j_5m = j_5m.dropna(subset=["fwd_ret_30m"])
        panel_rows.append(j_5m)

    panel = pd.concat(panel_rows).sort_index()
    log.info("panel total 5m bars (with fwd_ret_30m): %d", len(panel))

    # Candidate pool for fee-aware perm null
    rng = np.random.default_rng(126)
    pool_size_target = 50000
    if len(panel) > pool_size_target:
        pool_idx = rng.choice(len(panel), size=pool_size_target, replace=False)
        candidate_pool_gross_bp = panel["fwd_ret_30m"].iloc[pool_idx].values * 10000
    else:
        candidate_pool_gross_bp = panel["fwd_ret_30m"].values * 10000
    log.info("candidate pool size for fee-aware perm: %d", len(candidate_pool_gross_bp))

    # Trigger events
    trig = panel[panel["burst"] == 1].copy()
    trig["direction"] = trig["burst_sign"].astype(int)
    trig["signed_ret_bp"] = trig["fwd_ret_30m"] * trig["direction"] * 10000
    trig["qtr"] = trig.index.to_period("Q").astype(str)

    n_trig_total = len(trig)
    n_trig_pos = int((trig["direction"] > 0).sum())
    n_trig_neg = int((trig["direction"] < 0).sum())
    log.info("Trigger total %d (pos %d / neg %d) rate=%.3f%%",
             n_trig_total, n_trig_pos, n_trig_neg, n_trig_total / len(panel) * 100)

    log.info("--- Step 3: 4-quadrant Symmetric Negative Test (Lesson #19) ---")

    # A focus: pos burst x LONG (sign-matched, continuation)
    a_focus = trig[trig["direction"] > 0].copy()
    a_focus_gross_bp = a_focus["signed_ret_bp"]
    a_focus_net_bp = a_focus_gross_bp - FEE_BP

    # A mirror: pos burst x SHORT
    a_mirror_gross_bp = -a_focus["signed_ret_bp"]
    a_mirror_net_bp = a_mirror_gross_bp - FEE_BP

    # B focus: neg burst x SHORT (sign-matched, continuation)
    b_focus = trig[trig["direction"] < 0].copy()
    b_focus_gross_bp = b_focus["signed_ret_bp"]
    b_focus_net_bp = b_focus_gross_bp - FEE_BP

    # B mirror: neg burst x LONG
    b_mirror_gross_bp = -b_focus["signed_ret_bp"]
    b_mirror_net_bp = b_mirror_gross_bp - FEE_BP

    quadrants = {
        "A_focus_burst_pos_LONG": evaluate_quadrant("A_focus_burst_pos_LONG",
                                                     a_focus_net_bp, candidate_pool_gross_bp,
                                                     a_focus["sym"], a_focus["qtr"], a_focus_gross_bp, panel_years),
        "A_mirror_burst_pos_SHORT": evaluate_quadrant("A_mirror_burst_pos_SHORT",
                                                       a_mirror_net_bp, -candidate_pool_gross_bp,
                                                       a_focus["sym"], a_focus["qtr"], a_mirror_gross_bp, panel_years),
        "B_focus_burst_neg_SHORT": evaluate_quadrant("B_focus_burst_neg_SHORT",
                                                      b_focus_net_bp, -candidate_pool_gross_bp,
                                                      b_focus["sym"], b_focus["qtr"], b_focus_gross_bp, panel_years),
        "B_mirror_burst_neg_LONG": evaluate_quadrant("B_mirror_burst_neg_LONG",
                                                      b_mirror_net_bp, candidate_pool_gross_bp,
                                                      b_focus["sym"], b_focus["qtr"], b_mirror_gross_bp, panel_years),
    }

    log.info("--- Step 4: Per-quadrant verdict summary ---")
    for label, q in quadrants.items():
        if q.get("skip"):
            log.info("  %s: SKIP n=%d", label, q.get("n", 0))
            continue
        log.info("  %s n=%d gross=%.2f net=%.2f obs_t=%.2f null_t=%.2f sigex=%.2f "
                 "ci_lower=%.2f perm_p=%.3f 3gate=%s qpos=%d/%d sci=%d/%d edge%%=%.3f conc=%s edge_first=%s",
                 label, q["n"], q["gross_bp"], q["net_bp"], q["obs_t"], q["null_mean_t"],
                 q["signal_t_excess"], q["ci_lower_bp"], q["perm_p_one_sided_above"],
                 q["three_gate_pass"],
                 sum(1 for t in q["per_quarter_t"].values() if t > 0),
                 len(q["per_quarter_t"]),
                 q["n_syms_ci_pos"], q.get("n_syms_measurable", 0),
                 q["per_trade_edge_pct"], q["concentration_pass"], q["edge_first_gate_lesson41"])

    # Lesson #39 sub-class manual detection
    def sub_class_signature(focus, mirror):
        if focus.get("skip") or mirror.get("skip"):
            return "indeterminate"
        s = focus["gross_bp"] + mirror["gross_bp"]
        focus_pos_net = focus["net_bp"] > 0
        focus_broad_neg = (focus["net_bp"] < 0 and focus["n_syms_ci_pos"] <= 1)
        focus_real_conc = (focus["n_syms_ci_pos"] >= 3 and focus["syms_ci_pos_ratio"] >= 0.30)
        mirror_real_conc = (mirror["n_syms_ci_pos"] >= 3 and mirror["syms_ci_pos_ratio"] >= 0.30)
        if abs(s) < 1.0:
            if focus_real_conc and not mirror_real_conc:
                return "C (mechanism-positive — focus concentrated real, mirror broad-uniform-negative)"
            if focus_broad_neg and not mirror_real_conc:
                return "A (broad uniform negative — exact-symmetric trigger noise)"
            elif focus_broad_neg and mirror_real_conc:
                return "B (mechanism-inverted — fee-bound real signal in mirror)"
            elif focus_pos_net:
                return "C (focus net positive — real directional signal in focus)"
            else:
                return "exact_symmetric_other"
        return "asymmetric"

    arm_a = sub_class_signature(quadrants["A_focus_burst_pos_LONG"], quadrants["A_mirror_burst_pos_SHORT"])
    arm_b = sub_class_signature(quadrants["B_focus_burst_neg_SHORT"], quadrants["B_mirror_burst_neg_LONG"])

    # Verdict logic — Lesson #41 amendment edge-first
    any_focus_pass = (
        quadrants["A_focus_burst_pos_LONG"].get("three_gate_pass", False)
        or quadrants["B_focus_burst_neg_SHORT"].get("three_gate_pass", False)
    )
    any_focus_conc_pass = (
        (quadrants["A_focus_burst_pos_LONG"].get("three_gate_pass", False)
         and quadrants["A_focus_burst_pos_LONG"].get("concentration_pass", False))
        or (quadrants["B_focus_burst_neg_SHORT"].get("three_gate_pass", False)
            and quadrants["B_focus_burst_neg_SHORT"].get("concentration_pass", False))
    )
    any_focus_edge_pass = (
        quadrants["A_focus_burst_pos_LONG"].get("edge_first_gate_lesson41", False)
        or quadrants["B_focus_burst_neg_SHORT"].get("edge_first_gate_lesson41", False)
    )

    if not any_focus_edge_pass:
        if not any_focus_pass:
            verdict = "BROAD_FALSIFIED_LIFE_CHANGING_EDGE_FAIL"
        elif any_focus_pass and not any_focus_conc_pass:
            verdict = "DIFFUSE_POSITIVE_LIFE_CHANGING_EDGE_FAIL_LESSON_41"
        else:
            verdict = "CONCENTRATED_LIFE_CHANGING_EDGE_FAIL_LESSON_41"
    else:
        if any_focus_conc_pass:
            verdict = "R1_PASS_CONCENTRATED_LIFE_CHANGING_QUALIFIED"
        elif any_focus_pass:
            verdict = "R1_PASS_DIFFUSE_POSITIVE_LIFE_CHANGING_QUALIFIED"
        else:
            verdict = "EDGE_PASS_3GATE_FAIL_INDETERMINATE"

    # All-negative special verdict
    all_focus_negative = all(
        q.get("net_bp", 0) < 0 for q in [
            quadrants["A_focus_burst_pos_LONG"], quadrants["B_focus_burst_neg_SHORT"]
        ] if not q.get("skip")
    )
    if all_focus_negative and verdict.startswith("BROAD_FALSIFIED"):
        verdict = "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE"

    # Lesson #46-B candidate: stratified/full panel inflation ratio (R-0 stratified vs R-1 full)
    # R-0 A_focus gross = 119.34bp, R-1 will measure
    r1_a_focus_gross = quadrants["A_focus_burst_pos_LONG"].get("gross_bp", float("nan"))
    r1_b_focus_gross = quadrants["B_focus_burst_neg_SHORT"].get("gross_bp", float("nan"))
    r0_a_focus_gross_stratified = 119.34  # from R-0 prescreen
    r0_b_focus_gross_stratified = 18.47
    inflation_a = (
        r0_a_focus_gross_stratified / r1_a_focus_gross
        if r1_a_focus_gross is not None and r1_a_focus_gross != 0 and not math.isnan(r1_a_focus_gross)
        else None
    )
    inflation_b = (
        r0_b_focus_gross_stratified / r1_b_focus_gross
        if r1_b_focus_gross is not None and r1_b_focus_gross != 0 and not math.isnan(r1_b_focus_gross)
        else None
    )

    out = {
        "paradigm_name": PARADIGM_NAME,
        "counter": 126,
        "phase": "R-1",
        "r1_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "trigger_params": {
            "rolling_days_for_p99": ROLLING_DAYS,
            "rolling_bar_window_1m": ROLLING_BAR_WINDOW,
            "volume_percentile": PERCENTILE_VOLUME,
            "magnitude_threshold_1m_log_ret": MAG_THRESHOLD,
            "forward_hold_min": 30,
            "panel_frame": "5m (1m bursts aggregated to first-burst-sign within 5m bin)",
        },
        "fee_bp_round_trip": FEE_BP,
        "universe": COHORT,
        "n_symbols": len(sym_data),
        "per_symbol_days_1m": per_sym_days,
        "panel_5m_bars": int(len(panel)),
        "panel_years": panel_years,
        "n_quarters": int(trig["qtr"].nunique()),
        "n_triggers_total": n_trig_total,
        "n_triggers_pos": n_trig_pos,
        "n_triggers_neg": n_trig_neg,
        "trigger_rate_pct": round(n_trig_total / len(panel) * 100, 4),
        "candidate_pool_size_for_perm": len(candidate_pool_gross_bp),
        "quadrants": quadrants,
        "lesson_19_snt": "applied — 4-quadrant single batch",
        "lesson_16_concentration_gate": {
            "criteria": "q_pos_t_ratio >= 0.5 AND syms_ci_pos_ratio >= 0.30 AND n_syms_ci_pos >= 3",
            "per_quadrant_result": {
                k: {
                    "q_pos_t_ratio": v.get("q_pos_t_ratio"),
                    "syms_ci_pos_ratio": v.get("syms_ci_pos_ratio"),
                    "n_syms_ci_pos": v.get("n_syms_ci_pos"),
                    "concentration_pass": v.get("concentration_pass"),
                }
                for k, v in quadrants.items() if not v.get("skip")
            },
        },
        "lesson_30_data_window_advisory": {
            "short_window_syms": {s: d for s, d in per_sym_days.items() if d < full_window * 0.30},
            "advisory": "ADAUSDT 143d (<30%) included but per-symbol verdict advisory",
        },
        "lesson_39_sub_class_manual": {
            "A_arm": arm_a,
            "B_arm": arm_b,
            "note": "sign-matched mirror = -focus by construction (exact-symmetric)",
        },
        "lesson_41_amendment_edge_first": {
            "criteria": "per_trade_edge_pct >= 2.0% (life-changing gate FIRST)",
            "per_quadrant_result": {
                k: {
                    "per_trade_edge_pct": v.get("per_trade_edge_pct"),
                    "trades_per_year_approx": v.get("trades_per_year_approx"),
                    "edge_first_gate_lesson41": v.get("edge_first_gate_lesson41"),
                }
                for k, v in quadrants.items() if not v.get("skip")
            },
            "any_focus_edge_pass": any_focus_edge_pass,
        },
        "lesson_43_trap_check": {
            "novelty_axes_3": "1m granularity + binary event + signed burst-minute direction",
            "mechanism_alpha_verified": "verified by per-quadrant 3-gate + concentration",
        },
        "lesson_44_amendment_xref_10th_dogfood": (
            "Full cross-reference at R-0 prescreen — paradigm 72/94/95/113/116/123/124 + "
            "RUNBOOK §3-K/§3-L/§3-M + INDEX volume-axis summary. PASSED 3 family-distinct axes."
        ),
        "lesson_45_family_distinct": "Empirical p99 percentile + magnitude filter, NOT unsupervised. PASS.",
        "lesson_46_amendment_refinement_inflation_ratio": {
            "r0_stratified_a_focus_gross_bp": r0_a_focus_gross_stratified,
            "r1_full_a_focus_gross_bp": r1_a_focus_gross,
            "inflation_ratio_a": inflation_a,
            "r0_stratified_b_focus_gross_bp": r0_b_focus_gross_stratified,
            "r1_full_b_focus_gross_bp": r1_b_focus_gross,
            "inflation_ratio_b": inflation_b,
            "lesson_46_B_advisory_threshold": ">=5x inflation = advisory",
        },
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-1 metrics JSON: %s", out_path)
    log.info("VERDICT: %s", verdict)
    log.info("Lesson #39 A-arm sub-class: %s", arm_a)
    log.info("Lesson #39 B-arm sub-class: %s", arm_b)
    if inflation_a is not None:
        log.info("Lesson #46-B inflation ratio A: %.2fx (R0 %.2f / R1 %.2f)",
                 inflation_a, r0_a_focus_gross_stratified, r1_a_focus_gross)
    if inflation_b is not None:
        log.info("Lesson #46-B inflation ratio B: %.2fx (R0 %.2f / R1 %.2f)",
                 inflation_b, r0_b_focus_gross_stratified, r1_b_focus_gross)


if __name__ == "__main__":
    main()
