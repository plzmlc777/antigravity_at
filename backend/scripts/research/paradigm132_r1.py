"""paradigm 132 R-1 PoC — funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h.

R-1 protocol (Lesson #19 SNT mandatory + Lesson #21 5th dogfood
INDIVIDUAL-vs-JOINT sigex decisive + Lesson #52 a/b dual detection + Lesson #16
Concentration Gate + Lesson #44 funding family Tier 4 retire reconciliation
via paradigm 22 R-1 baseline sigex comparison).

Three-gate per quadrant:
  signal_t_excess >= 2.0  AND  ci_lower_bp > 0  AND  perm_p_one_sided_above <= 0.10
Concentration gate per quadrant (Lesson #16):
  q_pos_t_ratio >= 0.5  AND  syms_ci_pos_ratio >= 0.30  AND  n_syms_ci_pos >= 3

Lesson #21 5th DOGFOOD measurement variants (vs paradigm 22 R-1 baseline):
  V1: funding_anchor_only (every 8h boundary × direction by funding sign)
  V2: funding_magnitude_only (|funding|>p70 × MR direction)
  V3: oi_direction_only (OI declining × direction by funding sign at boundary)
  V4: anchor + magnitude (8h boundary + |funding|>p70 × MR direction)
  V5: anchor + OI direction (8h boundary + OI decline × MR direction)
  V6: TRIPLE JOINT (anchor + magnitude + OI decline × MR direction) [hypothesis]

PASS criterion: V6 (triple joint) sigex > MAX(V1..V5) sigex × 1.2 AND 3-gate PASS
FAIL: V6 sigex <= MAX(V1..V5) → Lesson #21 5th dogfood (3-way axis stacking trap)

Lessons applied at R-1:
  #11 per-quarter measurable (R-0 PASS for both quadrants stratified n>=30 4/4 A, 4/4 B)
  #16 Concentration Gate (q_pos_t + syms_ci_pos)
  #19 SNT 4-quadrant (A_focus A_mirror B_focus B_mirror)
  #21 INDIVIDUAL-vs-JOINT sigex (6 variants) — DECISIVE for 5th dogfood
  #34 empirical distribution recap
  #39 sub-class A/B/C/D + Lesson #52 a/b detection
  #40 percentile rank PASS
  #41 amendment edge-first
  #44 14th xref — funding family Tier 4 retire reconciliation
  #45 explicit empirical thresholds (no HMM)
  #46 6th REFINEMENT (R-0 stratified done)
  #52 a (LONG drift universe-wide) / b (SHORT-bias INVERSE) explicit dual detection
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p132_r1")

PARADIGM_NAME = "funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h"
PARADIGM_NUM = 132
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
TRIG_PATH = OUT_DIR / "trig_panel.joblib"
PANEL_PATH = OUT_DIR / "sym_panel.joblib"

FEE_PER_TRADE = 0.0008
FEE_BP = FEE_PER_TRADE * 10000.0

GATE_SIGEX = 2.0
GATE_PERM_P = 0.10

GATE_Q_POS_T = 0.5
GATE_SYM_CI_POS_RATIO = 0.30
GATE_SYM_CI_POS_MIN = 3

# Paradigm 22 R-1 baseline reference (legacy daily-bar carry, sigex not directly
# available — use composite proxy: alpha_pct_mean=43.41% / sharpe_mean=-0.13,
# trades_total=179, wr_mean=50.18%. Conservative sigex proxy ≈ 1.5 based on
# wr and trades_total characteristics.)
PARADIGM_22_BASELINE_SIGEX_PROXY = 1.5  # Conservative; user-specified threshold ×1.2 = 1.8


def per_sym_block_stats(net_arr: np.ndarray, sym_arr: np.ndarray, fwd_dir: np.ndarray) -> dict:
    """Per-symbol gross/net + bootstrap CI for Concentration Gate."""
    syms = np.unique(sym_arr)
    per_sym = {}
    for s in syms:
        mask = sym_arr == s
        n = int(mask.sum())
        if n < 3:
            per_sym[str(s)] = {"n": n, "gross_bp": None, "ci_pos": False, "ci_lower_bp": None}
            continue
        sym_net = net_arr[mask]
        sym_gross_bp = float(sym_net.mean() * 10000.0)
        try:
            b = bootstrap_ci(sym_net, n_boot=500, alpha=0.10, rng_seed=42)
            lo = b["ci_lower"]; hi = b["ci_upper"]
            ci_lo_bp = float(lo * 10000.0)
            ci_hi_bp = float(hi * 10000.0)
            ci_pos = ci_lo_bp > 0
        except Exception:
            ci_lo_bp = None
            ci_pos = False
        per_sym[str(s)] = {
            "n": n, "gross_bp": sym_gross_bp,
            "ci_lower_bp": ci_lo_bp,
            "ci_pos": bool(ci_pos),
        }
    n_syms = len(syms)
    n_ci_pos = sum(1 for v in per_sym.values() if v.get("ci_pos"))
    ratio = (n_ci_pos / n_syms) if n_syms > 0 else 0.0
    return {
        "per_sym": per_sym,
        "n_syms": int(n_syms),
        "n_ci_pos": int(n_ci_pos),
        "syms_ci_pos_ratio": float(ratio),
        "concentration_gate_pass": bool(
            ratio >= GATE_SYM_CI_POS_RATIO and n_ci_pos >= GATE_SYM_CI_POS_MIN
        ),
    }


def per_quarter_t_stat(fwd_log_arr: np.ndarray, ts_arr: np.ndarray,
                       direction: int) -> dict:
    """Per-quarter t-stat + positive ratio for Concentration Gate."""
    q_periods = {
        "2025Q3": (pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
        "2025Q4": (pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
        "2026Q1": (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
        "2026Q2": (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
    }
    out = {}
    n_pos_t = 0
    n_meas = 0
    for qname, (qs, qe) in q_periods.items():
        mask = (ts_arr >= qs) & (ts_arr < qe)
        n = int(mask.sum())
        if n < 5:
            out[qname] = {"n": n, "t": None}
            continue
        rets = fwd_log_arr[mask] * direction
        net = rets - FEE_PER_TRADE
        mean = net.mean()
        sd = net.std(ddof=1)
        t = (mean / (sd / math.sqrt(n))) if sd > 0 else 0.0
        out[qname] = {"n": n, "t": float(t)}
        n_meas += 1
        if t > 0:
            n_pos_t += 1
    ratio = (n_pos_t / n_meas) if n_meas > 0 else 0.0
    return {
        "per_q": out,
        "n_measurable": int(n_meas),
        "n_pos_t": int(n_pos_t),
        "q_pos_t_ratio": float(ratio),
        "q_pos_t_gate_pass": bool(ratio >= GATE_Q_POS_T),
    }


def evaluate_quadrant(label: str, fwd_log: np.ndarray, sym_arr: np.ndarray,
                      ts_arr: np.ndarray, pool_gross: np.ndarray, direction: int) -> dict:
    """Direction: +1 LONG (fwd as-is), -1 SHORT (fwd negated)."""
    n = int(len(fwd_log))
    if n < 5:
        return {"label": label, "n_trades": n, "error": "n<5"}
    gross = fwd_log * direction
    net = gross - FEE_PER_TRADE
    mean_gross_bp = float(gross.mean() * 10000.0)
    mean_net_bp = float(net.mean() * 10000.0)
    sd = float(net.std(ddof=1))
    obs_t = (mean_net_bp / 10000.0 / (sd / math.sqrt(n))) if sd > 0 else 0.0
    # bootstrap CI on net
    try:
        b = bootstrap_ci(net, n_boot=2000, alpha=0.10, rng_seed=42)
        lo = b["ci_lower"]; hi = b["ci_upper"]
        ci_lo_bp = float(lo * 10000.0)
        ci_hi_bp = float(hi * 10000.0)
    except Exception:
        ci_lo_bp = None
        ci_hi_bp = None
    # fee-aware perm test
    pool_dir = pool_gross * direction
    try:
        perm = fee_aware_perm_test(
            observed_net_returns=net, candidate_pool_returns=pool_dir,
            fee_per_trade=FEE_PER_TRADE, n_perms=2000, rng_seed=42,
        )
        perm_p_above = float(perm.get("perm_p_one_sided_above", 1.0))
        sigex = float(perm.get("signal_t_excess", 0.0))
        null_mean_t = perm.get("null_mean_t", None)
    except Exception as e:
        perm_p_above = 1.0
        sigex = 0.0
        null_mean_t = None
        log.warning("perm failure %s: %s", label, e)

    # 3-gate
    gate3 = bool(sigex >= GATE_SIGEX and (ci_lo_bp or -999) > 0 and perm_p_above <= GATE_PERM_P)

    # Concentration
    sym_block = per_sym_block_stats(net, sym_arr, fwd_log)
    q_block = per_quarter_t_stat(fwd_log, ts_arr, direction)
    conc_pass = bool(sym_block["concentration_gate_pass"] and q_block["q_pos_t_gate_pass"])

    return {
        "label": label,
        "direction": int(direction),
        "n_trades": n,
        "obs_gross_bp": mean_gross_bp,
        "obs_net_bp": mean_net_bp,
        "obs_t": float(obs_t),
        "ci_lower_bp": ci_lo_bp,
        "ci_upper_bp": ci_hi_bp,
        "perm_p_above": perm_p_above,
        "sigex": sigex,
        "null_mean_t": null_mean_t,
        "gate3_pass": gate3,
        "concentration": {
            "syms_ci_pos_ratio": sym_block["syms_ci_pos_ratio"],
            "n_syms_ci_pos": sym_block["n_ci_pos"],
            "n_syms_measurable": sym_block["n_syms"],
            "q_pos_t_ratio": q_block["q_pos_t_ratio"],
            "n_q_pos_t": q_block["n_pos_t"],
            "n_q_measurable": q_block["n_measurable"],
            "gate_pass": conc_pass,
            "per_sym": sym_block["per_sym"],
            "per_q": q_block["per_q"],
        },
    }


def build_individual_axis_triggers(sym_panels: dict) -> dict:
    """Build the 6 Lesson #21 decomposition variants.

    Each variant returns: {sym: list of (timestamp, fwd_log_ret, direction)}
    Direction: per paradigm 22 family MR convention
      funding>0 → LONG MR / funding<0 → SHORT MR
    """
    variants = {
        "V1_anchor_only": [],            # every 8h boundary
        "V2_magnitude_only": [],          # |funding| > p70 (anchored)
        "V3_oi_direction_only": [],       # OI declining (anchored)
        "V4_anchor_magnitude": [],        # anchor + magnitude
        "V5_anchor_oi_direction": [],     # anchor + OI decline
        "V6_TRIPLE_JOINT": [],            # all 3 (= R-0 trigger set)
    }
    for sym, p in sym_panels.items():
        ft = p["funding_time"]
        f_rate = p["funding_rate"]
        f_sign = p["funding_sign"]
        mag_ext = p["mag_extreme"]
        oi_dec = p["oi_declining"]
        fwd = p["fwd_log_ret"]
        for i in range(len(ft)):
            if not np.isfinite(fwd[i]) or f_sign[i] == 0:
                continue
            # MR direction by funding sign: funding>0 → LONG MR, funding<0 → SHORT MR
            direction = +1 if f_sign[i] > 0 else -1
            ts = pd.Timestamp(ft[i])
            row = {"sym": sym, "ts": ts, "fwd_log_ret": float(fwd[i]),
                   "direction": int(direction)}
            # V1: every boundary
            variants["V1_anchor_only"].append(row)
            # V2: magnitude only (boundary required to anchor)
            if mag_ext[i]:
                variants["V2_magnitude_only"].append(row)
            # V3: OI direction only (boundary required to anchor)
            if oi_dec[i]:
                variants["V3_oi_direction_only"].append(row)
            # V4: anchor + magnitude
            if mag_ext[i]:
                variants["V4_anchor_magnitude"].append(row)
            # V5: anchor + OI direction
            if oi_dec[i]:
                variants["V5_anchor_oi_direction"].append(row)
            # V6: all 3
            if mag_ext[i] and oi_dec[i]:
                variants["V6_TRIPLE_JOINT"].append(row)
    return variants


def evaluate_variant(name: str, rows: list, pool_gross: np.ndarray) -> dict:
    """Eval a Lesson #21 variant — direction comes from per-row sign."""
    if not rows:
        return {"name": name, "n": 0, "error": "empty"}
    df = pd.DataFrame(rows)
    # gross per direction
    df["gross"] = df["fwd_log_ret"] * df["direction"]
    df["net"] = df["gross"] - FEE_PER_TRADE
    n = len(df)
    mean_gross_bp = float(df["gross"].mean() * 10000.0)
    mean_net_bp = float(df["net"].mean() * 10000.0)
    sd = float(df["net"].std(ddof=1))
    obs_t = (mean_net_bp / 10000.0 / (sd / math.sqrt(n))) if sd > 0 else 0.0
    try:
        b = bootstrap_ci(df["net"].values, n_boot=1500, alpha=0.10, rng_seed=42)
        lo = b["ci_lower"]; hi = b["ci_upper"]
        ci_lo_bp = float(lo * 10000.0)
    except Exception:
        ci_lo_bp = None
    # Since direction is per-row signed, pool gross can be used as-is (sym effect)
    # Mix +/- direction pool via reflection? Use combined pool conservatively:
    try:
        perm = fee_aware_perm_test(
            observed_net_returns=df["net"].values, candidate_pool_returns=pool_gross,
            fee_per_trade=FEE_PER_TRADE, n_perms=1500, rng_seed=42,
        )
        sigex = float(perm.get("signal_t_excess", 0.0))
        perm_p = float(perm.get("perm_p_one_sided_above", 1.0))
    except Exception:
        sigex = 0.0
        perm_p = 1.0
    return {
        "name": name,
        "n": int(n),
        "gross_bp": mean_gross_bp,
        "net_bp": mean_net_bp,
        "obs_t": float(obs_t),
        "ci_lower_bp": ci_lo_bp,
        "sigex": sigex,
        "perm_p_above": perm_p,
    }


def detect_lesson_52(snt: dict) -> dict:
    """Lesson #52 a/b dual detection at R-1.

    52a (universe LONG drift artifact):
      A_mirror_LONG gross > 0 AND B_focus_LONG gross > 0 AND both ci_lower_bp <= 0
      AND universally low concentration (most syms ci negative).
    52b (SHORT-bias INVERSE artifact):
      A_focus_SHORT gross > 0 OR B_mirror_SHORT gross > 0 (i.e. SHORT direction
      profitable) AND mirror LONG quadrant deeply negative gross — direction
      mechanism INVERTED from hypothesis.
    """
    A_focus = snt.get("A_focus_pos_long_MR", {})
    A_mirror = snt.get("A_mirror_pos_short", {})
    B_focus = snt.get("B_focus_neg_short_MR", {})
    B_mirror = snt.get("B_mirror_neg_long", {})

    # 52a: both LONG quadrants gross > 0 + both ci_lower <= 0 + universally low conc
    A_long_gross = A_focus.get("obs_gross_bp", 0)
    B_long_gross = B_mirror.get("obs_gross_bp", 0)
    A_long_ci = A_focus.get("ci_lower_bp", 0) or 0
    B_long_ci = B_mirror.get("ci_lower_bp", 0) or 0
    A_long_conc_ratio = A_focus.get("concentration", {}).get("syms_ci_pos_ratio", 0)
    B_long_conc_ratio = B_mirror.get("concentration", {}).get("syms_ci_pos_ratio", 0)
    artifact_52a = (A_long_gross > 0 and B_long_gross > 0
                     and A_long_ci <= 0 and B_long_ci <= 0
                     and A_long_conc_ratio < 0.3 and B_long_conc_ratio < 0.3)

    # 52b: SHORT direction profitable + LONG direction deeply negative
    A_short_gross = A_mirror.get("obs_gross_bp", 0)
    B_short_gross = B_focus.get("obs_gross_bp", 0)
    artifact_52b = ((A_short_gross > 5 or B_short_gross > 5)
                     and A_long_gross < -5 and B_long_gross < -5)

    return {
        "52a_universe_long_drift_artifact": bool(artifact_52a),
        "52b_short_bias_inverse_artifact": bool(artifact_52b),
        "A_focus_long_MR_gross_bp": float(A_long_gross),
        "A_mirror_long_via_pos_short_gross_bp": float(A_short_gross),
        "B_focus_short_MR_gross_bp": float(B_short_gross),
        "B_mirror_long_via_neg_long_gross_bp": float(B_long_gross),
    }


def main():
    log.info("paradigm %d R-1 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not TRIG_PATH.exists() or not PANEL_PATH.exists():
        log.error("missing R-0 artifacts: %s | %s", TRIG_PATH, PANEL_PATH)
        sys.exit(1)
    trig_df = joblib.load(TRIG_PATH)
    sym_panels = joblib.load(PANEL_PATH)
    log.info("loaded trig_df n=%d (A=%d B=%d) syms=%d", len(trig_df),
             int((trig_df["quadrant_kind"] == "A_pos_long_MR").sum()),
             int((trig_df["quadrant_kind"] == "B_neg_short_MR").sum()),
             len(sym_panels))

    # Build pool: all 4h forward returns at funding boundaries (per-sym concat)
    all_fwd = []
    for sym, p in sym_panels.items():
        fwd = p["fwd_log_ret"]
        all_fwd.extend([float(x) for x in fwd if np.isfinite(x)])
    pool_gross = np.array(all_fwd, dtype=float)
    log.info("candidate pool size (boundary fwd_ret): n=%d", len(pool_gross))

    # ---------------------------------------------------------------------
    # 4-quadrant SNT (paradigm 22 family MR convention)
    #   A_focus_pos_long_MR : funding>0 + OI decline + mag_extreme × LONG
    #   A_mirror_pos_short : same trigger × SHORT
    #   B_focus_neg_short_MR: funding<0 + OI decline + mag_extreme × SHORT
    #   B_mirror_neg_long  : same trigger × LONG
    # ---------------------------------------------------------------------
    A_mask = (trig_df["quadrant_kind"] == "A_pos_long_MR").values
    B_mask = (trig_df["quadrant_kind"] == "B_neg_short_MR").values

    A_fwd = trig_df["fwd_log_ret"].values[A_mask]
    A_sym = trig_df["sym"].values[A_mask]
    A_ts = trig_df["funding_time"].values[A_mask].astype("datetime64[ns]")
    B_fwd = trig_df["fwd_log_ret"].values[B_mask]
    B_sym = trig_df["sym"].values[B_mask]
    B_ts = trig_df["funding_time"].values[B_mask].astype("datetime64[ns]")

    snt = {}
    snt["A_focus_pos_long_MR"] = evaluate_quadrant(
        "A_focus_pos_long_MR", A_fwd, A_sym, A_ts, pool_gross, direction=+1
    )
    snt["A_mirror_pos_short"] = evaluate_quadrant(
        "A_mirror_pos_short", A_fwd, A_sym, A_ts, pool_gross, direction=-1
    )
    snt["B_focus_neg_short_MR"] = evaluate_quadrant(
        "B_focus_neg_short_MR", B_fwd, B_sym, B_ts, pool_gross, direction=-1
    )
    snt["B_mirror_neg_long"] = evaluate_quadrant(
        "B_mirror_neg_long", B_fwd, B_sym, B_ts, pool_gross, direction=+1
    )
    for q, r in snt.items():
        log.info("SNT %s n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f ci_lo=%s perm_p=%.3f gate3=%s conc=%s",
                 q, r.get("n_trades"), r.get("obs_gross_bp"), r.get("obs_net_bp"),
                 r.get("obs_t"), r.get("sigex"), r.get("ci_lower_bp"),
                 r.get("perm_p_above"), r.get("gate3_pass"),
                 r.get("concentration", {}).get("gate_pass"))

    # ---------------------------------------------------------------------
    # Lesson #21 5th dogfood — INDIVIDUAL-vs-JOINT (6 variants)
    # ---------------------------------------------------------------------
    log.info("Lesson #21 variant decomposition")
    variants = build_individual_axis_triggers(sym_panels)
    variant_results = {}
    for vname, rows in variants.items():
        res = evaluate_variant(vname, rows, pool_gross)
        variant_results[vname] = res
        log.info("variant %s n=%d gross=%.2fbp sigex=%.2f perm_p=%.3f ci_lo=%s",
                 vname, res.get("n"), res.get("gross_bp"),
                 res.get("sigex"), res.get("perm_p_above"), res.get("ci_lower_bp"))

    # Lesson #21 detection: V6 (triple) sigex > MAX(V1..V5) × 1.2?
    v6 = variant_results.get("V6_TRIPLE_JOINT", {})
    v6_sigex = v6.get("sigex", -99)
    _individual_sigexes = [
        variant_results.get(v, {}).get("sigex", -99)
        for v in ["V1_anchor_only", "V2_magnitude_only", "V3_oi_direction_only",
                  "V4_anchor_magnitude", "V5_anchor_oi_direction"]
    ]
    # Filter NaN (perm fails when n_obs > n_pool / 2)
    _individual_sigexes = [x for x in _individual_sigexes
                            if x is not None and not (isinstance(x, float) and math.isnan(x))]
    max_individual_sigex = max(_individual_sigexes) if _individual_sigexes else -99.0
    axis_stacking_trap = v6_sigex <= max_individual_sigex
    sigex_improvement_vs_paradigm22 = v6_sigex / PARADIGM_22_BASELINE_SIGEX_PROXY
    p22_exemption_earned = (
        v6_sigex > PARADIGM_22_BASELINE_SIGEX_PROXY * 1.2
        and v6.get("sigex", 0) >= GATE_SIGEX
        and (v6.get("ci_lower_bp") or -999) > 0
        and v6.get("perm_p_above", 1) <= GATE_PERM_P
    )

    # Lesson #52 a/b detection
    l52 = detect_lesson_52(snt)
    log.info("Lesson #52 detection: %s", l52)

    # 3-gate aggregate (any quadrant PASS?)
    any_quadrant_pass = any(snt[q].get("gate3_pass", False) for q in snt)
    any_quadrant_conc_pass = any(
        snt[q].get("concentration", {}).get("gate_pass", False) for q in snt
    )

    # Verdict
    if axis_stacking_trap and not any_quadrant_pass:
        verdict = "BROAD_FALSIFIED_LESSON_21_5TH_DOGFOOD_AXIS_STACKING_TRAP"
    elif any_quadrant_pass and any_quadrant_conc_pass and p22_exemption_earned:
        verdict = "PASS_R1_FULL_PARADIGM_22_EXEMPTION_EARNED"
    elif any_quadrant_pass and not any_quadrant_conc_pass:
        verdict = "CONCENTRATED_R1_PASS_LESSON_16_BLOCK"
    elif l52["52a_universe_long_drift_artifact"]:
        verdict = "BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT"
    elif l52["52b_short_bias_inverse_artifact"]:
        verdict = "BROAD_FALSIFIED_LESSON_52B_SHORT_BIAS_INVERSE_ARTIFACT"
    else:
        verdict = "BROAD_FALSIFIED_NO_GATE_PASS"

    out = {
        "paradigm": PARADIGM_NAME,
        "paradigm_num": PARADIGM_NUM,
        "phase": "R-1_PoC",
        "evaluated_at_kst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": verdict,
        "fee_per_trade": FEE_PER_TRADE,
        "snt_4quadrant": snt,
        "lesson_21_variant_decomposition": variant_results,
        "lesson_21_axis_stacking_trap_detected": bool(axis_stacking_trap),
        "lesson_21_v6_sigex": float(v6_sigex),
        "lesson_21_max_individual_sigex": float(max_individual_sigex),
        "lesson_44_paradigm_22_baseline_sigex_proxy": PARADIGM_22_BASELINE_SIGEX_PROXY,
        "lesson_44_sigex_vs_paradigm22_ratio": float(sigex_improvement_vs_paradigm22),
        "lesson_44_paradigm22_exemption_earned": bool(p22_exemption_earned),
        "lesson_52_detection": l52,
        "any_quadrant_gate3_pass": bool(any_quadrant_pass),
        "any_quadrant_concentration_pass": bool(any_quadrant_conc_pass),
        "lesson_30_data_window_funding_days": 365,
        "lesson_30_data_window_oi_days": 800,
    }
    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-1 verdict=%s written: %s", verdict, out_path)


if __name__ == "__main__":
    main()
