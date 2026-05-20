"""paradigm 124 R-1 PoC — alt_realized_kurtosis_extreme_signed_directional_2h.

R-1 full panel measurement with 4-quadrant Symmetric Negative Test (Lesson #19).

Trigger: 1h rolling moments on 5m intra-bar log-returns (12 obs)
  - kurt top-decile (p90 cutoff from R-0: excess_kurt > 2.401)
  - |skew| > 1.0 (chosen at R-0; joint trigger rate 8.72%)
Direction: sign-matched LONG/SHORT via skew sign
Forward hold: 2h (24 x 5m bars)
Universe: 13 active alts
Fee: 16bp round-trip

Family-distinct vs paradigm 65 (`realized_skewness_exhaustion_mr`) and paradigm 66
(`realized_skewness_momentum_continuation`):
  - Statistic class: 4th moment kurtosis + 3rd moment skewness JOINT vs 3rd-only
  - Frame: 5m intra-bar (12 bars = 1h window) vs 1m intra-bar (60 bars = 1h window)
  - Direction logic: joint-trigger sign-matched vs z-trigger MR/momentum

R-0 advisory: per-quarter sign-flip in B_focus (2 flips across 4 quarters) → fragile mechanism risk
R-0 R0_PASS_BUT_ADVISORY_PER_QUARTER_SIGN_FLIP_LESSON_46_SUB.

Lessons applied:
  #11 sample density (PASS at R-0: measurable_q 10/10)
  #16 Concentration Gate
  #19 SNT 4-quadrant single batch
  #21 single statistic-class axis (moments natural pair)
  #22 frame-grade (5m, 2.77M panel bars)
  #34 empirical distribution
  #39 sub-class A/B/C manual detection
  #41 AMENDMENT edge >= 2% gate FIRST + DIFFUSE_POSITIVE SECOND
  #44 amendment graveyard cross-reference (5th dogfood: paradigm 65/66 distinct)
  #45 family-distinct (explicit moments, not unsupervised)
  #46 AMENDMENT REFINEMENT 2nd dogfood (R-0 stratified + sign-flip advisory)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

# Helper import path
sys.path.insert(0, "/home/hcpark/antigravity/backend")
from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p124_r1")

PARADIGM_NAME = "alt_realized_kurtosis_extreme_signed_directional_2h"
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# From R-0 prescreen
MOMENT_WIN_BARS = 12  # 5m bars (1h)
KURT_THRESHOLD = 2.401  # excess kurt p90 from R-0
SKEW_ABS_THRESHOLD = 1.0  # chosen at R-0 (joint rate 8.72%)
FORWARD_HOLD_BARS = 24  # 2h
FEE_BP = 16.0
FEE_FRAC = FEE_BP / 10000.0


def load_ohlcv_5m(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    o5 = df.resample("5min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    return o5


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
    """Compute full R-1 stats for one quadrant arm."""
    n = int(len(net_bp))
    if n < 30:
        return {"n": n, "skip": True}
    gross_mean = float(gross_bp.mean())
    net_mean = float(net_bp.mean())
    obs_t = _t_stat(net_bp.values)

    q_t_stats = {}
    for q in qtrs.unique():
        sub = net_bp[qtrs == q]
        if len(sub) >= 30:
            q_t_stats[q] = _t_stat(sub.values)
    n_q_measurable = len(q_t_stats)
    n_q_pos_t = sum(1 for t in q_t_stats.values() if t > 0)
    q_pos_t_ratio = n_q_pos_t / n_q_measurable if n_q_measurable else 0.0

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
    """Run fee-aware perm + bootstrap CI + concentration gate per quadrant."""
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

    gate_excess = bool(signal_t_excess >= 2.0) if not math.isnan(signal_t_excess) else False
    gate_ci = bool(ci_lower_bp > 0)
    gate_perm = bool(perm_p_above <= 0.10) if not math.isnan(perm_p_above) else False
    three_gate_pass = gate_excess and gate_ci and gate_perm

    qpos_ratio = detail.get("q_pos_t_ratio", 0.0)
    sci_ratio = detail.get("syms_ci_pos_ratio", 0.0)
    n_sci = detail.get("n_syms_ci_pos", 0)
    concentration_pass = bool(qpos_ratio >= 0.5 and sci_ratio >= 0.30 and n_sci >= 3)

    # Lesson #41 AMENDMENT edge-first gate
    trades_per_year = n / panel_years if panel_years > 0 else 0
    per_trade_edge_pct = detail["net_bp_mean"] / 100.0  # bp -> pct
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
        "concentration_pass": concentration_pass,
        "per_quarter_t": detail["per_quarter_t"],
        "n_q_measurable": detail["n_q_measurable"],
        "n_q_pos_t": detail["n_q_pos_t"],
        "per_symbol": detail["per_symbol"],
        "n_syms_measurable": detail["n_syms_measurable"],
        "trades_per_year_approx": trades_per_year,
        "per_trade_edge_pct": per_trade_edge_pct,
        "edge_first_gate_lesson41": edge_first_gate,
    }


def main():
    log.info("paradigm 124 R-1 start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dsn = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
    engine = create_engine(dsn)

    log.info("--- Step 1: Load 5m OHLCV per symbol ---")
    sym_data = {}
    for sym in COHORT:
        try:
            ohlcv = load_ohlcv_5m(sym, engine)
            if ohlcv.empty or len(ohlcv) < MOMENT_WIN_BARS + 100:
                log.warning("%s: insufficient - skip", sym)
                continue
            sym_data[sym] = ohlcv
            log.info("%s: %d 5m bars", sym, len(ohlcv))
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded")
        sys.exit(1)

    log.info("--- Step 2: Compute rolling 1h moments (skew + excess kurt) + forward 2h returns ---")
    panel_rows = []
    panel_years_per_sym = []
    for sym, j in sym_data.items():
        j = j.copy()
        j["log_ret_5m"] = np.log(j["close"]).diff()
        skew = j["log_ret_5m"].rolling(MOMENT_WIN_BARS, min_periods=MOMENT_WIN_BARS).skew()
        kurt = j["log_ret_5m"].rolling(MOMENT_WIN_BARS, min_periods=MOMENT_WIN_BARS).kurt()
        j["skew_1h"] = skew
        j["excess_kurt_1h"] = kurt
        j["abs_skew_1h"] = skew.abs()
        j["fwd_ret_2h"] = j["close"].pct_change(FORWARD_HOLD_BARS).shift(-FORWARD_HOLD_BARS)
        j["sym"] = sym
        j_clean = j.dropna(subset=["skew_1h", "excess_kurt_1h", "fwd_ret_2h"])
        panel_rows.append(j_clean)
        if len(j_clean) > 0:
            yrs = (j_clean.index.max() - j_clean.index.min()).total_seconds() / (365.25 * 86400)
            panel_years_per_sym.append(yrs)
    panel = pd.concat(panel_rows).sort_index()
    log.info("panel total bars (with fwd_ret_2h available): %d", len(panel))

    panel_years = float(np.mean(panel_years_per_sym)) if panel_years_per_sym else 2.0
    log.info("panel mean years per symbol: %.2f", panel_years)

    # Candidate pool for fee-aware perm
    rng = np.random.default_rng(124)
    pool_size_target = 50000
    if len(panel) > pool_size_target:
        pool_idx = rng.choice(len(panel), size=pool_size_target, replace=False)
        candidate_pool_gross_bp = panel["fwd_ret_2h"].iloc[pool_idx].values * 10000
    else:
        candidate_pool_gross_bp = panel["fwd_ret_2h"].values * 10000
    log.info("candidate pool size for fee-aware perm: %d", len(candidate_pool_gross_bp))

    # Trigger: joint kurt > threshold AND |skew| > threshold
    trig = panel[(panel["excess_kurt_1h"] > KURT_THRESHOLD) & (panel["abs_skew_1h"] > SKEW_ABS_THRESHOLD)].copy()
    trig["direction"] = np.where(trig["skew_1h"] > 0, 1, -1)
    trig["signed_ret_bp"] = trig["fwd_ret_2h"] * trig["direction"] * 10000
    trig["qtr"] = trig.index.to_period("Q").astype(str)

    n_trig_total = len(trig)
    n_trig_pos = int((trig["skew_1h"] > 0).sum())
    n_trig_neg = int((trig["skew_1h"] < 0).sum())
    log.info("Joint trigger total %d (skew_pos %d / skew_neg %d) rate=%.3f%%",
             n_trig_total, n_trig_pos, n_trig_neg, n_trig_total / len(panel) * 100)

    # Build 4 quadrants
    log.info("--- Step 3: 4-quadrant Symmetric Negative Test (Lesson #19) ---")

    # A focus: skew_pos × LONG (sign-matched continuation up)
    a_focus = trig[trig["skew_1h"] > 0].copy()
    a_focus_gross_bp = a_focus["signed_ret_bp"]  # already direction-signed (LONG since direction=+1)
    a_focus_net_bp = a_focus_gross_bp - FEE_BP

    # A mirror: skew_pos × SHORT
    a_mirror_gross_bp = -a_focus["signed_ret_bp"]
    a_mirror_net_bp = a_mirror_gross_bp - FEE_BP

    # B focus: skew_neg × SHORT (sign-matched continuation down)
    b_focus = trig[trig["skew_1h"] < 0].copy()
    b_focus_gross_bp = b_focus["signed_ret_bp"]  # direction=-1, signed_ret = fwd * -1
    b_focus_net_bp = b_focus_gross_bp - FEE_BP

    # B mirror: skew_neg × LONG
    b_mirror_gross_bp = -b_focus["signed_ret_bp"]
    b_mirror_net_bp = b_mirror_gross_bp - FEE_BP

    quadrants = {
        "A_focus_skewpos_LONG": evaluate_quadrant("A_focus_skewpos_LONG",
                                                   a_focus_net_bp, candidate_pool_gross_bp,
                                                   a_focus["sym"], a_focus["qtr"], a_focus_gross_bp, panel_years),
        "A_mirror_skewpos_SHORT": evaluate_quadrant("A_mirror_skewpos_SHORT",
                                                     a_mirror_net_bp, -candidate_pool_gross_bp,
                                                     a_focus["sym"], a_focus["qtr"], a_mirror_gross_bp, panel_years),
        "B_focus_skewneg_SHORT": evaluate_quadrant("B_focus_skewneg_SHORT",
                                                     b_focus_net_bp, -candidate_pool_gross_bp,
                                                     b_focus["sym"], b_focus["qtr"], b_focus_gross_bp, panel_years),
        "B_mirror_skewneg_LONG": evaluate_quadrant("B_mirror_skewneg_LONG",
                                                     b_mirror_net_bp, candidate_pool_gross_bp,
                                                     b_focus["sym"], b_focus["qtr"], b_mirror_gross_bp, panel_years),
    }

    log.info("--- Step 4: Per-quadrant verdict summary ---")
    for label, q in quadrants.items():
        if q.get("skip"):
            log.info("  %s: SKIP n=%d", label, q.get("n", 0))
            continue
        log.info("  %s n=%d gross=%.2f net=%.2f obs_t=%.2f null_t=%.2f sigex=%.2f "
                 "ci_lower=%.2f perm_p=%.3f 3gate=%s qpos=%d/%d sci=%d/%d conc=%s edge_first(2pct)=%s "
                 "trades/yr=%.0f edge_pct=%.4f",
                 label, q["n"], q["gross_bp"], q["net_bp"], q["obs_t"], q["null_mean_t"],
                 q["signal_t_excess"], q["ci_lower_bp"], q["perm_p_one_sided_above"],
                 q["three_gate_pass"],
                 q["n_q_pos_t"], q["n_q_measurable"],
                 q["n_syms_ci_pos"], q["n_syms_measurable"],
                 q["concentration_pass"], q["edge_first_gate_lesson41"],
                 q["trades_per_year_approx"], q["per_trade_edge_pct"])

    # Lesson #39 sub-class manual detection
    def sub_class_signature(focus, mirror):
        if focus.get("skip") or mirror.get("skip"):
            return "indeterminate"
        s = focus["gross_bp"] + mirror["gross_bp"]
        focus_neg = focus["net_bp"] < 0
        focus_broad_neg = (focus_neg and focus["n_syms_ci_pos"] <= 1)
        mirror_real_conc = (mirror["n_syms_ci_pos"] >= 3 and mirror["syms_ci_pos_ratio"] >= 0.30)
        if abs(s) < 1.0:
            if focus_broad_neg and not mirror_real_conc:
                return "A (broad uniform negative - exact-symmetric trigger noise)"
            elif focus_broad_neg and mirror_real_conc:
                return "B (mechanism-inverted - fee-bound real signal in mirror)"
            else:
                return "exact_symmetric_other"
        return "asymmetric"

    arm_a = sub_class_signature(quadrants["A_focus_skewpos_LONG"], quadrants["A_mirror_skewpos_SHORT"])
    arm_b = sub_class_signature(quadrants["B_focus_skewneg_SHORT"], quadrants["B_mirror_skewneg_LONG"])

    # Verdict logic
    any_focus_pass = (
        quadrants["A_focus_skewpos_LONG"].get("three_gate_pass", False)
        or quadrants["B_focus_skewneg_SHORT"].get("three_gate_pass", False)
    )
    any_focus_conc_pass = (
        (quadrants["A_focus_skewpos_LONG"].get("three_gate_pass", False) and quadrants["A_focus_skewpos_LONG"].get("concentration_pass", False))
        or (quadrants["B_focus_skewneg_SHORT"].get("three_gate_pass", False) and quadrants["B_focus_skewneg_SHORT"].get("concentration_pass", False))
    )
    any_focus_edge_pass = (
        (quadrants["A_focus_skewpos_LONG"].get("edge_first_gate_lesson41", False))
        or (quadrants["B_focus_skewneg_SHORT"].get("edge_first_gate_lesson41", False))
    )

    # Lesson #41 AMENDMENT: edge-first FIRST, then 3-gate, then concentration
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
        q.get("net_bp", 0) < 0 for q in [quadrants["A_focus_skewpos_LONG"], quadrants["B_focus_skewneg_SHORT"]]
        if not q.get("skip")
    )
    if all_focus_negative and verdict.startswith("BROAD_FALSIFIED"):
        verdict = "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE"

    # Asymmetric focus: only one quadrant carries the signal
    a_focus_pos = quadrants["A_focus_skewpos_LONG"].get("net_bp", 0) > 0
    b_focus_pos = quadrants["B_focus_skewneg_SHORT"].get("net_bp", 0) > 0
    asymmetric_focus = (a_focus_pos and not b_focus_pos) or (b_focus_pos and not a_focus_pos)

    out = {
        "paradigm_name": PARADIGM_NAME,
        "counter": 124,
        "phase": "R-1",
        "r1_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "trigger_params": {
            "moment_window_bars_5m": MOMENT_WIN_BARS,
            "moment_window_minutes": MOMENT_WIN_BARS * 5,
            "kurt_threshold_excess": KURT_THRESHOLD,
            "skew_abs_threshold": SKEW_ABS_THRESHOLD,
        },
        "forward_hold_min": 120,
        "fee_bp_round_trip": FEE_BP,
        "universe": COHORT,
        "n_symbols": len(sym_data),
        "panel_bars": int(len(panel)),
        "panel_years_per_sym_mean": panel_years,
        "n_quarters": int(trig["qtr"].nunique()),
        "n_triggers_total": n_trig_total,
        "n_triggers_skew_pos": n_trig_pos,
        "n_triggers_skew_neg": n_trig_neg,
        "trigger_rate_pct": round(n_trig_total / len(panel) * 100, 4),
        "candidate_pool_size_for_perm": len(candidate_pool_gross_bp),
        "quadrants": quadrants,
        "asymmetric_focus": asymmetric_focus,
        "lesson_19_snt": "applied - 4-quadrant single batch",
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
        "lesson_44_amendment_xref_5th_dogfood": (
            "paradigm 65 realized_skewness_exhaustion_mr (1h 3rd-moment-only z=2.0 MR) GRAVEYARD 2026-05-14; "
            "paradigm 66 realized_skewness_momentum_continuation (1h 3rd-moment-only momentum) GRAVEYARD 2026-05-14. "
            "Paradigm 124 distinct via: (a) 4th moment kurtosis NEW statistic class; "
            "(b) joint conjunction kurt-top-decile + |skew|>1 (sign as direction selector, NOT trigger); "
            "(c) 5m frame base vs 1m frame base. DNA 3/6 dims distinct."
        ),
        "lesson_45_family_distinct": "Explicit moments (pandas .skew + .kurt closed-form) NOT unsupervised clustering. PASS.",
        "lesson_46_amendment_refinement_R0_prior": "R-0 stratified n=50x4q + sign-flip detection: A_focus 1 flip / B_focus 2 flips (advisory)",
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-1 metrics JSON: %s", out_path)
    log.info("VERDICT: %s", verdict)
    log.info("Lesson #39 A-arm sub-class: %s", arm_a)
    log.info("Lesson #39 B-arm sub-class: %s", arm_b)
    log.info("asymmetric_focus: %s", asymmetric_focus)


if __name__ == "__main__":
    main()
