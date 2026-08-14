"""paradigm 131 R-1 PoC — alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h.

R-1 protocol (Lesson #19 4-quadrant SNT mandatory + Lesson #21 individual-vs-joint
sigex comparison mandatory + Lesson #52 a/b dual detection mandatory).

Three-gate criterion per quadrant:
  signal_t_excess >= 2.0  AND  ci_lower_bp > 0  AND  perm_p_one_sided_above <= 0.10
Concentration gate per quadrant (Lesson #16):
  q_pos_t_ratio >= 0.5  AND  syms_ci_pos_ratio >= 0.30  AND  n_syms_ci_pos >= 3

R-0 prescreen status: R0_HALT_INSUFFICIENT_DENSITY (Lesson #11 per-quarter floor
1/5 per quadrant). Dispatch ANYWAY for:
  (1) Lesson #21 individual-vs-joint comparison decisive measurement
  (2) Lesson #52 a/b dual artifact detection
  (3) full R-1 sample n_A=118 + n_B=91 sufficient for quadrant aggregate,
      Concentration Gate per-quarter measurement informative
  → results carry SAMPLE_INSUFFICIENT_PER_QUARTER caveat in verdict.

Lessons applied at R-1 stage:
  #11 PER-QUARTER caveat advised (R-0 1/5 measurable per quadrant)
  #16 Concentration Gate (q_pos_t + syms_ci_pos)
  #19 4-quadrant SNT (single batch)
  #21 INDIVIDUAL-vs-JOINT sigex comparison (basis_only, range_close_only, joint)
  #34 empirical distribution recap (R-0)
  #39 sub-class A/B detection
  #40 axis 2 upper tail only (acknowledged)
  #41 amendment edge-first
  #44 13th xref
  #45 explicit empirical thresholds (no HMM)
  #51 universe LONG drift detection (1 dogfood as of paradigm 129)
  #52 a (LONG drift, paradigm 99+129) and b (SHORT-bias INVERSE, paradigm 130) dual detection
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
log = logging.getLogger("p131_r1")

PARADIGM_NAME = "alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h"
PARADIGM_NUM = 131
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")

# Triggers + per-sym panels from R-0
TRIG_PATH = OUT_DIR / "trig_panel.joblib"
PANEL_PATH = OUT_DIR / "sym_4h_panel.joblib"

FEE_PER_TRADE = 0.0008
FEE_BP = FEE_PER_TRADE * 10000.0
BASIS_Z_THRESHOLD = 1.5
RANGE_CLOSE_Z_THRESHOLD = 1.5

# Three-gate
GATE_SIGEX = 2.0
GATE_PERM_P = 0.10

# Concentration gate
GATE_Q_POS_T = 0.5
GATE_SYM_CI_POS_RATIO = 0.30
GATE_SYM_CI_POS_MIN = 3


def quadrant_stats(net_arr: np.ndarray, label: str) -> dict:
    n = int(len(net_arr))
    if n < 5:
        return {"label": label, "n_trades": n, "error": "n<5"}
    mean_net = float(net_arr.mean())
    sd = float(net_arr.std(ddof=1))
    t = (mean_net / (sd / math.sqrt(n))) if sd > 0 else 0.0
    return {
        "label": label,
        "n_trades": n,
        "obs_mean_net_bp": mean_net * 10000.0,
        "obs_t": t,
    }


def main():
    log.info("paradigm %d R-1 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not TRIG_PATH.exists() or not PANEL_PATH.exists():
        log.error("missing R-0 artifacts: %s | %s", TRIG_PATH, PANEL_PATH)
        sys.exit(1)
    trig_df = joblib.load(TRIG_PATH)
    sym_panel = joblib.load(PANEL_PATH)
    log.info("loaded trig_df n=%d (A=%d B=%d) syms=%d", len(trig_df),
             int((trig_df["quadrant_kind"] == "A_pos_basis").sum()),
             int((trig_df["quadrant_kind"] == "B_neg_basis").sum()),
             len(sym_panel))

    # ------------------------------------------------------------------
    # Build candidate pool returns for fee_aware_perm_test
    # Pool = all 4h forward returns regardless of trigger (per-sym concatenated)
    # ------------------------------------------------------------------
    all_fwd_pool = []
    for sym, panel in sym_panel.items():
        fwd = panel["fwd_log_ret_4h"].dropna().values
        all_fwd_pool.extend(fwd.tolist())
    pool_gross = np.array(all_fwd_pool, dtype=float)
    log.info("candidate pool size (all 4h fwd returns): n=%d", len(pool_gross))

    # ------------------------------------------------------------------
    # 4-quadrant SNT (mean-reversion direction)
    #   A_focus pos_basis × wide_range × SHORT
    #   A_mirror pos_basis × wide_range × LONG
    #   B_focus neg_basis × wide_range × LONG
    #   B_mirror neg_basis × wide_range × SHORT
    # ------------------------------------------------------------------
    quadrants = {}
    for qname, kind, direction in [
        ("A_focus_pos_basis_wide_range_SHORT_4h_MR", "A_pos_basis", -1),
        ("A_mirror_pos_basis_wide_range_LONG_4h", "A_pos_basis", +1),
        ("B_focus_neg_basis_wide_range_LONG_4h_MR", "B_neg_basis", +1),
        ("B_mirror_neg_basis_wide_range_SHORT_4h", "B_neg_basis", -1),
    ]:
        sub = trig_df[trig_df["quadrant_kind"] == kind].copy()
        if sub.empty:
            quadrants[qname] = {"label": qname, "error": "empty"}
            continue
        # signed forward gross = direction × fwd_log_ret_4h
        sub["gross"] = direction * sub["fwd_log_ret_4h"]
        net = sub["gross"].values - FEE_PER_TRADE
        gross_arr = sub["gross"].values

        # Stats
        stats = quadrant_stats(net, qname)
        # Bootstrap CI on net
        ci = bootstrap_ci(net, n_boot=2000, block_size=20)
        # Fee-aware perm test against full 4h pool, using same direction sign
        # Pool is undirected gross; apply same direction modifier as observed mean direction
        # For MR direction we use direction × fwd, but pool is symmetric. We test obs t-stat
        # against pool null where each draw is multiplied by random sign and fee applied.
        # Use sign-aware pool: multiply pool by direction to match sign distribution.
        signed_pool = pool_gross * direction
        perm = fee_aware_perm_test(
            observed_net_returns=net,
            candidate_pool_returns=signed_pool,
            fee_per_trade=FEE_PER_TRADE,
            n_perms=1000,
            rng_seed=42,
        )

        # Per-quarter pos_t (Lesson #16)
        per_quarter = {}
        for qtr, qdf in sub.groupby("qtr"):
            qnet = qdf["gross"].values - FEE_PER_TRADE
            qn = int(len(qnet))
            if qn < 2:
                per_quarter[qtr] = {"n": qn, "mean_bp": None, "t": None, "pos_t": False}
                continue
            qm = float(qnet.mean())
            qsd = float(qnet.std(ddof=1))
            qt = (qm / (qsd / math.sqrt(qn))) if qsd > 0 else 0.0
            per_quarter[qtr] = {
                "n": qn,
                "mean_bp": qm * 10000.0,
                "t": qt,
                "pos_t": qt > 0,
            }
        n_q_meas = sum(1 for v in per_quarter.values() if v.get("n", 0) >= 10)
        n_q_pos = sum(1 for v in per_quarter.values() if v.get("pos_t", False))
        q_pos_ratio = (n_q_pos / n_q_meas) if n_q_meas > 0 else 0.0

        # Per-symbol bootstrap CI (Lesson #16)
        per_symbol = {}
        for sym, sdf in sub.groupby("sym"):
            snet = sdf["gross"].values - FEE_PER_TRADE
            sn = int(len(snet))
            if sn < 5:
                per_symbol[sym] = {"n": sn, "mean_bp": None, "ci_lower_bp": None,
                                    "ci_upper_bp": None, "ci_pos": False}
                continue
            sci = bootstrap_ci(snet, n_boot=1000, block_size=5)
            per_symbol[sym] = {
                "n": sn,
                "mean_bp": float(snet.mean()) * 10000.0,
                "ci_lower_bp": sci["ci_lower"] * 10000.0,
                "ci_upper_bp": sci["ci_upper"] * 10000.0,
                "ci_pos": bool(sci["ci_lower"] > 0),
            }
        n_syms_ci_pos = sum(1 for v in per_symbol.values() if v.get("ci_pos", False))
        n_syms_total = len(per_symbol)
        sym_ci_ratio = (n_syms_ci_pos / n_syms_total) if n_syms_total > 0 else 0.0

        # 3-gate
        sigex = perm.get("signal_t_excess", float("nan"))
        ci_lower_bp = ci["ci_lower"] * 10000.0
        ci_upper_bp = ci["ci_upper"] * 10000.0
        # For SHORT/MR negative direction we use perm_p_one_sided_above as "above null"
        # since obs_t direction depends on whether direction is + or -. Use above for
        # LONG (positive expected mean) and below for SHORT (negative? — we want net > 0
        # in trade returns, so always above-null is positive evidence).
        perm_p = perm.get("perm_p_one_sided_above", float("nan"))
        gate_3 = (
            (not math.isnan(sigex)) and sigex >= GATE_SIGEX
            and ci_lower_bp > 0
            and (not math.isnan(perm_p)) and perm_p <= GATE_PERM_P
        )

        gate_conc = (
            q_pos_ratio >= GATE_Q_POS_T
            and sym_ci_ratio >= GATE_SYM_CI_POS_RATIO
            and n_syms_ci_pos >= GATE_SYM_CI_POS_MIN
        )

        # Life-changing 4-dim
        trades_per_year = int(len(net)) / (364.0 / 365.0)
        per_trade_edge_pct = (float(net.mean()) if len(net) else 0.0) * 100.0
        annualized_sharpe = (
            float(net.mean()) / float(net.std(ddof=1)) * math.sqrt(trades_per_year)
            if len(net) > 1 and net.std(ddof=1) > 0 else 0.0
        )
        life_changing = {
            "trades_per_year": trades_per_year,
            "per_trade_edge_pct": per_trade_edge_pct,
            "capital_util_pct": 100.0,
            "annualized_sharpe": annualized_sharpe,
            "pass_trades_per_year_12": trades_per_year >= 12,
            "pass_edge_2pct": per_trade_edge_pct >= 2.0,
            "pass_util_30pct": True,
            "pass_sharpe_1_5": annualized_sharpe >= 1.5,
            "pass_all_4_dim": (trades_per_year >= 12 and per_trade_edge_pct >= 2.0
                                and annualized_sharpe >= 1.5),
        }

        quadrants[qname] = {
            "label": qname,
            "n_trades": int(len(net)),
            "obs_mean_gross_bp": float(gross_arr.mean()) * 10000.0,
            "obs_mean_net_bp": float(net.mean()) * 10000.0,
            "obs_t": stats.get("obs_t", 0.0),
            "ci_lower_bp": ci_lower_bp,
            "ci_upper_bp": ci_upper_bp,
            "ci_pos": bool(ci["ci_lower"] > 0),
            "prob_positive": ci.get("prob_positive", float("nan")),
            "perm_obs_t": perm.get("obs_t", float("nan")),
            "perm_null_mean_t": perm.get("null_mean_t", float("nan")),
            "perm_null_std_t": perm.get("null_std_t", float("nan")),
            "signal_t_excess": sigex,
            "perm_p_two_sided": perm.get("perm_p_two_sided", float("nan")),
            "perm_p_one_sided_above": perm.get("perm_p_one_sided_above", float("nan")),
            "perm_p_one_sided_below": perm.get("perm_p_one_sided_below", float("nan")),
            "gate_3_pass": gate_3,
            "per_quarter": per_quarter,
            "n_q_measurable_ge10": n_q_meas,
            "n_q_pos_t": n_q_pos,
            "q_pos_ratio": q_pos_ratio,
            "per_symbol": per_symbol,
            "n_syms_ci_pos": n_syms_ci_pos,
            "n_syms_total": n_syms_total,
            "syms_ci_pos_ratio": sym_ci_ratio,
            "gate_concentration_pass": gate_conc,
            "life_changing_4dim": life_changing,
        }
        log.info(
            "%s: n=%d gross=%.2fbp net=%.2fbp t=%.2f ci_lower=%.2f sigex=%.2f "
            "perm_p=%.3f q_pos=%d/%d sym_ci_pos=%d/%d gate3=%s gate_conc=%s",
            qname, len(net),
            float(gross_arr.mean()) * 10000.0,
            float(net.mean()) * 10000.0,
            stats.get("obs_t", 0.0),
            ci_lower_bp,
            sigex if not math.isnan(sigex) else float("nan"),
            perm_p if not math.isnan(perm_p) else float("nan"),
            n_q_pos, n_q_meas,
            n_syms_ci_pos, n_syms_total,
            gate_3, gate_conc,
        )

    # ------------------------------------------------------------------
    # Lesson #21 INDIVIDUAL-vs-JOINT sigex comparison
    # Recompute basis_only triggers + range_close_only triggers separately
    # (no conjunction) and measure A_focus equivalent on each axis alone.
    # ------------------------------------------------------------------
    log.info("--- Lesson #21 INDIVIDUAL-vs-JOINT sigex comparison ---")
    indiv = {}
    for axis_label, build_mask in [
        ("basis_only_pos_z_gt_1_5_SHORT_MR",
         lambda p: (p["basis_z"] > BASIS_Z_THRESHOLD)),
        ("basis_only_neg_z_lt_neg_1_5_LONG_MR",
         lambda p: (p["basis_z"] < -BASIS_Z_THRESHOLD)),
        ("range_close_only_z_gt_1_5_undirected_LONG_drift_proxy",
         lambda p: (p["range_close_z"] > RANGE_CLOSE_Z_THRESHOLD)),
    ]:
        rows = []
        # Per-sym debounced triggers
        for sym, panel in sym_panel.items():
            mask = build_mask(panel)
            ts_trig = panel.index[mask & panel["fwd_log_ret_4h"].notna()]
            last_t = None
            for ts in ts_trig:
                if last_t is not None and (ts - last_t).total_seconds() < 8 * 3600:
                    continue
                fwd = panel.at[ts, "fwd_log_ret_4h"]
                if pd.isna(fwd):
                    continue
                rows.append({"sym": sym, "ts": ts, "fwd": float(fwd)})
                last_t = ts
        if not rows:
            indiv[axis_label] = {"label": axis_label, "n": 0, "error": "no triggers"}
            continue
        sub = pd.DataFrame(rows)
        # Direction depends on axis_label
        if "SHORT_MR" in axis_label:
            direction = -1
        elif "LONG_MR" in axis_label or "LONG_drift" in axis_label:
            direction = +1
        else:
            direction = +1
        gross = (direction * sub["fwd"]).values
        net = gross - FEE_PER_TRADE
        n = int(len(net))
        if n < 5:
            indiv[axis_label] = {"label": axis_label, "n": n, "error": "n<5"}
            continue
        m_net = float(net.mean())
        sd = float(net.std(ddof=1))
        t = (m_net / (sd / math.sqrt(n))) if sd > 0 else 0.0
        ci = bootstrap_ci(net, n_boot=2000, block_size=20)
        signed_pool = pool_gross * direction
        perm = fee_aware_perm_test(
            observed_net_returns=net,
            candidate_pool_returns=signed_pool,
            fee_per_trade=FEE_PER_TRADE,
            n_perms=1000,
            rng_seed=42,
        )
        indiv[axis_label] = {
            "label": axis_label,
            "direction": direction,
            "n_trades": n,
            "obs_mean_gross_bp": float(gross.mean()) * 10000.0,
            "obs_mean_net_bp": m_net * 10000.0,
            "obs_t": t,
            "ci_lower_bp": ci["ci_lower"] * 10000.0,
            "ci_upper_bp": ci["ci_upper"] * 10000.0,
            "ci_pos": bool(ci["ci_lower"] > 0),
            "signal_t_excess": perm.get("signal_t_excess", float("nan")),
            "perm_p_one_sided_above": perm.get("perm_p_one_sided_above", float("nan")),
        }
        log.info(
            "  INDIV %s: n=%d gross=%.2fbp net=%.2fbp t=%.2f sigex=%.2f ci_lower=%.2f",
            axis_label, n,
            float(gross.mean()) * 10000.0,
            m_net * 10000.0,
            t,
            indiv[axis_label]["signal_t_excess"]
            if not math.isnan(indiv[axis_label]["signal_t_excess"]) else float("nan"),
            indiv[axis_label]["ci_lower_bp"],
        )

    # Lesson #21 verdict on axis stacking
    joint_a_sigex = quadrants.get(
        "A_focus_pos_basis_wide_range_SHORT_4h_MR", {}).get("signal_t_excess", float("nan"))
    joint_a_mirror_sigex = quadrants.get(
        "A_mirror_pos_basis_wide_range_LONG_4h", {}).get("signal_t_excess", float("nan"))
    joint_b_sigex = quadrants.get(
        "B_focus_neg_basis_wide_range_LONG_4h_MR", {}).get("signal_t_excess", float("nan"))
    indiv_basis_pos_sigex = indiv.get(
        "basis_only_pos_z_gt_1_5_SHORT_MR", {}).get("signal_t_excess", float("nan"))
    indiv_basis_neg_sigex = indiv.get(
        "basis_only_neg_z_lt_neg_1_5_LONG_MR", {}).get("signal_t_excess", float("nan"))

    lesson_21 = {
        "joint_A_focus_SHORT_MR_sigex": joint_a_sigex,
        "joint_A_mirror_LONG_sigex": joint_a_mirror_sigex,
        "joint_B_focus_LONG_MR_sigex": joint_b_sigex,
        "individual_basis_only_pos_SHORT_MR_sigex": indiv_basis_pos_sigex,
        "individual_basis_only_neg_LONG_MR_sigex": indiv_basis_neg_sigex,
        "joint_A_focus_minus_individual_basis_pos": (
            (joint_a_sigex - indiv_basis_pos_sigex)
            if not (math.isnan(joint_a_sigex) or math.isnan(indiv_basis_pos_sigex))
            else float("nan")
        ),
        "joint_B_focus_minus_individual_basis_neg": (
            (joint_b_sigex - indiv_basis_neg_sigex)
            if not (math.isnan(joint_b_sigex) or math.isnan(indiv_basis_neg_sigex))
            else float("nan")
        ),
    }
    log.info("Lesson #21 verdict: joint_A vs indiv_basis_pos: %.2f vs %.2f (delta %+.2f)",
             joint_a_sigex if not math.isnan(joint_a_sigex) else float("nan"),
             indiv_basis_pos_sigex if not math.isnan(indiv_basis_pos_sigex) else float("nan"),
             lesson_21["joint_A_focus_minus_individual_basis_pos"]
             if not math.isnan(lesson_21["joint_A_focus_minus_individual_basis_pos"]) else float("nan"))
    log.info("Lesson #21 verdict: joint_B vs indiv_basis_neg: %.2f vs %.2f (delta %+.2f)",
             joint_b_sigex if not math.isnan(joint_b_sigex) else float("nan"),
             indiv_basis_neg_sigex if not math.isnan(indiv_basis_neg_sigex) else float("nan"),
             lesson_21["joint_B_focus_minus_individual_basis_neg"]
             if not math.isnan(lesson_21["joint_B_focus_minus_individual_basis_neg"]) else float("nan"))

    # ------------------------------------------------------------------
    # Lesson #52 a/b dual detection
    # 52a: universe LONG drift artifact = both A_mirror_LONG + B_focus_LONG gross > 0
    #                                      AND ci_lower<0 in both AND syms_ci_pos<10%
    # 52b: conditional-overextension SHORT-bias INVERSE = both LONG quadrants gross<0
    #                                                       AND both SHORT gross>0
    # ------------------------------------------------------------------
    A_mirror = quadrants.get("A_mirror_pos_basis_wide_range_LONG_4h", {})
    B_focus = quadrants.get("B_focus_neg_basis_wide_range_LONG_4h_MR", {})
    A_focus = quadrants.get("A_focus_pos_basis_wide_range_SHORT_4h_MR", {})
    B_mirror = quadrants.get("B_mirror_neg_basis_wide_range_SHORT_4h", {})

    a_mirror_gross = A_mirror.get("obs_mean_gross_bp", float("nan"))
    a_mirror_ci_lower = A_mirror.get("ci_lower_bp", float("nan"))
    a_mirror_sym_ci_pos = A_mirror.get("syms_ci_pos_ratio", float("nan"))
    b_focus_gross = B_focus.get("obs_mean_gross_bp", float("nan"))
    b_focus_ci_lower = B_focus.get("ci_lower_bp", float("nan"))
    b_focus_sym_ci_pos = B_focus.get("syms_ci_pos_ratio", float("nan"))
    a_focus_gross = A_focus.get("obs_mean_gross_bp", float("nan"))
    b_mirror_gross = B_mirror.get("obs_mean_gross_bp", float("nan"))

    is_long_drift_artifact_52a = (
        not math.isnan(a_mirror_gross) and not math.isnan(b_focus_gross)
        and a_mirror_gross > 0 and b_focus_gross > 0
        and a_mirror_ci_lower < 0 and b_focus_ci_lower < 0
        and a_mirror_sym_ci_pos < 0.10 and b_focus_sym_ci_pos < 0.10
    )
    is_short_bias_artifact_52b = (
        not math.isnan(a_focus_gross) and not math.isnan(b_mirror_gross)
        and not math.isnan(a_mirror_gross) and not math.isnan(b_focus_gross)
        and a_mirror_gross < 0 and b_focus_gross < 0
        and a_focus_gross > 0 and b_mirror_gross > 0
        and A_focus.get("syms_ci_pos_ratio", 0.0) < 0.10
        and B_mirror.get("syms_ci_pos_ratio", 0.0) < 0.10
    )
    lesson_52_detection = {
        "52a_long_drift_artifact": is_long_drift_artifact_52a,
        "52b_short_bias_inverse_artifact": is_short_bias_artifact_52b,
        "raw": {
            "A_focus_SHORT_gross_bp": a_focus_gross,
            "A_mirror_LONG_gross_bp": a_mirror_gross,
            "B_focus_LONG_gross_bp": b_focus_gross,
            "B_mirror_SHORT_gross_bp": b_mirror_gross,
        },
    }
    log.info("Lesson #52 detection: 52a (LONG drift) = %s | 52b (SHORT-bias INVERSE) = %s",
             is_long_drift_artifact_52a, is_short_bias_artifact_52b)

    # ------------------------------------------------------------------
    # Verdict synthesis
    # ------------------------------------------------------------------
    n_pass_3gate = sum(1 for q in quadrants.values()
                       if isinstance(q, dict) and q.get("gate_3_pass", False))
    n_pass_concentration = sum(1 for q in quadrants.values()
                                if isinstance(q, dict) and q.get("gate_concentration_pass", False))
    n_pass_lc = sum(1 for q in quadrants.values()
                    if isinstance(q, dict)
                    and q.get("life_changing_4dim", {}).get("pass_all_4_dim", False))

    if n_pass_3gate >= 1 and n_pass_concentration >= 1:
        verdict = "PASS_R1_FULL_NEEDS_R2"
    elif n_pass_3gate == 0 and is_long_drift_artifact_52a:
        verdict = "BROAD_FALSIFIED_LESSON_52A_LONG_DRIFT_ARTIFACT"
    elif n_pass_3gate == 0 and is_short_bias_artifact_52b:
        verdict = "BROAD_FALSIFIED_LESSON_52B_SHORT_BIAS_INVERSE"
    elif n_pass_3gate == 0:
        verdict = "BROAD_FALSIFIED_ALL_4_QUADRANTS_FAIL_3GATE"
    else:
        verdict = "MIXED_3GATE_PASS_NO_CONCENTRATION"

    # Lesson #21 axis stacking judgment
    axis_stacking_trap = False
    if (not math.isnan(joint_a_sigex) and not math.isnan(indiv_basis_pos_sigex)
            and joint_a_sigex <= indiv_basis_pos_sigex):
        axis_stacking_trap = True
    if (not math.isnan(joint_b_sigex) and not math.isnan(indiv_basis_neg_sigex)
            and joint_b_sigex <= indiv_basis_neg_sigex):
        axis_stacking_trap = True

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-1",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "verdict_caveat": "R-0 SAMPLE_INSUFFICIENT_PER_QUARTER (Lesson #11 1/5 measurable per quadrant). "
                          "R-1 quadrant aggregate is informative but per-quarter concentration "
                          "carries low-power caveat.",
        "n_pass_3gate": n_pass_3gate,
        "n_pass_concentration": n_pass_concentration,
        "n_pass_life_changing_4dim": n_pass_lc,
        "fee_bp": FEE_BP,
        "quadrants": quadrants,
        "lesson_21_individual_vs_joint": {
            "joint_quadrants": {
                "A_focus_SHORT_MR_sigex": joint_a_sigex,
                "A_mirror_LONG_sigex": joint_a_mirror_sigex,
                "B_focus_LONG_MR_sigex": joint_b_sigex,
            },
            "individual_axes": indiv,
            "comparison_delta": lesson_21,
            "axis_stacking_trap_detected": axis_stacking_trap,
        },
        "lesson_52_detection": lesson_52_detection,
        "_summary_one_liner": {
            "paradigm": PARADIGM_NAME,
            "verdict": verdict,
            "n_quadrants_pass_3gate": n_pass_3gate,
            "n_quadrants_pass_concentration": n_pass_concentration,
            "A_focus_sigex": joint_a_sigex,
            "B_focus_sigex": joint_b_sigex,
            "lesson_21_axis_stacking_trap": axis_stacking_trap,
            "lesson_52a_long_drift": is_long_drift_artifact_52a,
            "lesson_52b_short_bias_inverse": is_short_bias_artifact_52b,
        },
    }

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("VERDICT: %s", verdict)
    log.info("R-1 saved to %s", out_path)


if __name__ == "__main__":
    main()
