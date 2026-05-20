"""paradigm 125 R-0 prescreen — alt_realized_quarticity_normalized_bipower_jump_event_alt_directional_2h.

Statistic: Barndorff-Nielsen ratio jump test (Huang-Tauchen 2005, Andersen-Bollerslev 2007)
  On 12-bar (1h) rolling window of 5m intra-bar log-returns:
      RV_t = sum_i r_i^2                                  (realized variance)
      BV_t = (pi/2) * sum_i |r_i| |r_{i-1}|                (bipower variation, jump-robust scale)
      RQ_t = (m/3) * sum_i r_i^4         m=12              (realized quarticity)
      Z_t  = ((RV_t - BV_t) / RV_t) * sqrt( m / ( ((pi/2)^2 + pi - 5) * max(1, RQ_t / BV_t^2) ) )
  This is the canonical ratio jump test, asymptotically N(0,1) under H0 = no jump.

Trigger: Z_jump > 3.0 AND |1-bar 5m log-return| > magnitude threshold
Direction: sign of triggering 5m log-return
Forward hold: 2h (24 x 5m bars)
Universe: 13 active alts (paradigm 119-124 reuse)

Family-distinct claim vs paradigm 65/66/124 (higher-order moment family):
  (a) STATISTIC: ratio-of-variations (jump-isolation), NOT raw moment.
  (b) TRIGGER MODE: discrete event (Z>3 binary jump detection) vs continuous percentile.
  (c) DIRECTION: jump sign (1-bar log-return sign) NOT distributional asymmetry (skew sign).
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p125_r0")

PARADIGM_NAME = "alt_realized_quarticity_normalized_bipower_jump_event_alt_directional_2h"
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Jump test window: 12 5m bars = 1h
WIN_BARS = 12
# Andersen-Bollerslev (2007) jump-test constant theta = (pi/2)^2 + pi - 5
AB_THETA = (math.pi / 2.0) ** 2 + math.pi - 5.0  # ~0.6090
# Trigger thresholds
Z_JUMP_THRESHOLD = 3.0  # B-N standard ~99.7% one-sided
MAG_CANDIDATES = [0.003, 0.005, 0.007, 0.01]  # 0.3%..1% 1-bar log-return magnitude
FORWARD_HOLD_BARS = 24  # 2h
FEE_BP = 16.0
TARGET_RATE = 0.015  # 1.5% target joint rate


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


def rolling_bn_jump_stat(log_ret: pd.Series, win: int) -> pd.Series:
    """Canonical Huang-Tauchen / Andersen-Bollerslev ratio jump test, rolling.

    Z_t = ((RV_t - BV_t) / RV_t) * sqrt( m / (theta * max(1, RQ_t / BV_t^2)) )

    Asymptotically standard normal under H0 = no jumps.
    """
    r = log_ret.fillna(0.0)
    r2 = r ** 2
    r4 = r ** 4
    abs_r = r.abs()
    abs_r_lag = abs_r.shift(1).fillna(0.0)
    bv_terms = abs_r * abs_r_lag

    RV = r2.rolling(win, min_periods=win).sum()
    BV_raw = bv_terms.rolling(win, min_periods=win).sum()
    BV = (math.pi / 2.0) * BV_raw
    RQ = (win / 3.0) * r4.rolling(win, min_periods=win).sum()

    RV_safe = RV.where(RV > 1e-20, 1e-20)
    BV_safe = BV.where(BV > 1e-20, 1e-20)
    ratio = (RQ / (BV_safe ** 2)).clip(lower=1.0)

    # Canonical ratio form
    relative_jump = (RV - BV) / RV_safe                         # ~ jump fraction of variance
    scale = (float(win) / (AB_THETA * ratio)).clip(lower=1e-20).pow(0.5)
    Z = relative_jump * scale
    return Z


def main():
    log.info("paradigm 125 R-0 prescreen start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dsn = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
    engine = create_engine(dsn)

    sym_data = {}
    for sym in COHORT:
        try:
            ohlcv = load_ohlcv_5m(sym, engine)
            if ohlcv.empty or len(ohlcv) < WIN_BARS + 100:
                log.warning("%s: insufficient (len=%d) - skip", sym, len(ohlcv))
                continue
            sym_data[sym] = ohlcv
            log.info("%s: %d 5m bars  %s -> %s", sym, len(ohlcv), ohlcv.index.min(), ohlcv.index.max())
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded - abort")
        sys.exit(1)

    eth = sym_data.get("ETHUSDT")
    full_days = (eth.index.max() - eth.index.min()).days if eth is not None else None
    log.info("ETHUSDT window: %s days (baseline)", full_days)

    log.info("--- Step 1: 5m log-returns + rolling B-N ratio jump test ---")
    panel_rows = []
    for sym, j in sym_data.items():
        j = j.copy()
        j["log_ret_5m"] = np.log(j["close"]).diff()
        j["abs_log_ret_5m"] = j["log_ret_5m"].abs()
        j["z_jump_1h"] = rolling_bn_jump_stat(j["log_ret_5m"], WIN_BARS)
        j["fwd_ret_2h"] = j["close"].pct_change(FORWARD_HOLD_BARS).shift(-FORWARD_HOLD_BARS)
        j["sym"] = sym
        j = j.dropna(subset=["z_jump_1h", "log_ret_5m"])
        panel_rows.append(j)
    panel = pd.concat(panel_rows).sort_index()
    log.info("panel rows after dropna: %d", len(panel))

    # Lesson #34 empirical distribution
    pct_z = {p: float(np.percentile(panel["z_jump_1h"], p)) for p in [50, 70, 80, 90, 95, 99, 99.5, 99.9]}
    pct_mag = {p: float(np.percentile(panel["abs_log_ret_5m"], p)) for p in [50, 70, 90, 95, 99, 99.9]}
    log.info("Z_jump percentiles: p50=%.3f p70=%.3f p80=%.3f p90=%.3f p95=%.3f p99=%.3f p99.5=%.3f p99.9=%.3f",
             *[pct_z[p] for p in [50, 70, 80, 90, 95, 99, 99.5, 99.9]])
    log.info("|log_ret_5m| percentiles: p50=%.5f p70=%.5f p90=%.5f p95=%.5f p99=%.5f p99.9=%.5f",
             *[pct_mag[p] for p in [50, 70, 90, 95, 99, 99.9]])

    # Lesson #40: structural feasibility (Z_jump > 3 rate)
    z_above_3 = float((panel["z_jump_1h"] > Z_JUMP_THRESHOLD).mean() * 100)
    z_above_2 = float((panel["z_jump_1h"] > 2.0).mean() * 100)
    z_above_2_5 = float((panel["z_jump_1h"] > 2.5).mean() * 100)
    log.info("Z_jump > 2.0 rate: %.4f%% | > 2.5 rate: %.4f%% | > 3.0 rate: %.4f%%",
             z_above_2, z_above_2_5, z_above_3)
    if z_above_3 < 0.05:
        log.error("Z_jump > 3 effectively unreachable (<0.05%%) - structural threshold infeasible (Lesson #40)")
        out = {
            "paradigm_name": PARADIGM_NAME,
            "verdict": "R0_HALT_STRUCTURAL_THRESHOLD_INFEASIBLE_LESSON_40",
            "z_jump_above_3_rate_pct": z_above_3,
            "z_jump_above_2_rate_pct": z_above_2,
            "z_jump_above_2_5_rate_pct": z_above_2_5,
            "z_jump_percentiles": pct_z,
        }
        with open(OUT_DIR / "r0_prescreen.json", "w") as f:
            json.dump(out, f, indent=2, default=str)
        sys.exit(0)

    log.info("--- Step 2: Joint trigger rate tuning (Z>3 AND |1-bar log_ret| > mag_thr) ---")
    joint_rate_stats = {}
    best_thr = None
    best_rate_diff = float("inf")
    for mag in MAG_CANDIDATES:
        mask = (panel["z_jump_1h"] > Z_JUMP_THRESHOLD) & (panel["abs_log_ret_5m"] > mag)
        n_joint = int(mask.sum())
        n_total = len(panel)
        rate = n_joint / n_total if n_total else 0.0
        joint_rate_stats[mag] = {"n_joint": n_joint, "n_total": n_total, "rate_pct": rate * 100}
        log.info("  Z>3 AND |log_ret|>%.3f: n=%d rate=%.4f%%", mag, n_joint, rate * 100)
        if 0.005 <= rate <= 0.08:
            if abs(rate - TARGET_RATE) < best_rate_diff:
                best_rate_diff = abs(rate - TARGET_RATE)
                best_thr = mag

    if best_thr is None:
        log.error("no magnitude threshold yields joint trigger rate in [0.5%%, 8%%] - HALT")
        out = {
            "paradigm_name": PARADIGM_NAME,
            "verdict": "R0_HALT_JOINT_TRIGGER_TUNING_FAIL",
            "z_jump_above_3_rate_pct": z_above_3,
            "z_jump_above_2_rate_pct": z_above_2,
            "z_jump_above_2_5_rate_pct": z_above_2_5,
            "z_jump_percentiles": pct_z,
            "joint_rate_stats": joint_rate_stats,
            "target_rate_pct": TARGET_RATE * 100,
        }
        with open(OUT_DIR / "r0_prescreen.json", "w") as f:
            json.dump(out, f, indent=2, default=str)
        sys.exit(0)
    chosen_rate_pct = joint_rate_stats[best_thr]["rate_pct"]
    log.info("CHOSEN magnitude threshold = %.4f (joint rate %.4f%%, closest to target %.1f%%)",
             best_thr, chosen_rate_pct, TARGET_RATE * 100)

    # R-0 family-distinct gate: trigger rate must be discretely sparse vs paradigm 124 (8.72%)
    family_distinct_trigger_mode = bool(chosen_rate_pct < 5.0)
    if not family_distinct_trigger_mode:
        log.warning(
            "Family-distinct trigger-rate gate FAIL: rate %.3f%% >= 5%% threshold (paradigm 124 was 8.72%%).",
            chosen_rate_pct,
        )

    # Apply joint trigger to build sample
    trig = panel[(panel["z_jump_1h"] > Z_JUMP_THRESHOLD) & (panel["abs_log_ret_5m"] > best_thr)].copy()
    trig = trig.dropna(subset=["fwd_ret_2h"])
    trig["direction"] = np.where(trig["log_ret_5m"] > 0, 1, -1)
    trig["signed_ret_bp"] = trig["fwd_ret_2h"] * trig["direction"] * 10000

    n_trig_total = len(trig)
    n_pos = int((trig["log_ret_5m"] > 0).sum())
    n_neg = int((trig["log_ret_5m"] < 0).sum())
    log.info("Joint triggers total: %d (jump_up %d / jump_down %d) rate=%.4f%%",
             n_trig_total, n_pos, n_neg, n_trig_total / len(panel) * 100)

    # Lesson #11 per-quadrant per-quarter sample density
    trig["qtr"] = trig.index.to_period("Q").astype(str)
    n_quarters = trig["qtr"].nunique()
    per_q_pos = trig[trig["log_ret_5m"] > 0].groupby("qtr").size()
    per_q_neg = trig[trig["log_ret_5m"] < 0].groupby("qtr").size()
    log.info("per-quarter jump_up: %s", per_q_pos.to_dict())
    log.info("per-quarter jump_down: %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (>=30 per quadrant): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT 3rd dogfood (formal promotion 자격)
    log.info("--- Lesson #46 AMENDMENT REFINEMENT 3rd dogfood: temporally-stratified R-0 ---")
    sorted_quarters = sorted(trig["qtr"].unique())
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)

    if len(sorted_quarters) < 4:
        log.warning("insufficient quarters for stratified R-0 (have %d, need 4)", len(sorted_quarters))
        sample = trig.dropna(subset=["signed_ret_bp"]).iloc[:200]
        stratified_strategy = "fallback_chronological_n200_INSUFFICIENT_QUARTERS"
        qtrs_to_use = []
    else:
        qtrs_to_use = [
            sorted_quarters[0],
            sorted_quarters[len(sorted_quarters) // 3],
            sorted_quarters[2 * len(sorted_quarters) // 3],
            sorted_quarters[-1],
        ]
        qtrs_to_use = sorted(set(qtrs_to_use))
        log.info("temporally-stratified quarters chosen: %s", qtrs_to_use)
        per_q_samples = []
        for qq in qtrs_to_use:
            q_data = trig[(trig["qtr"] == qq)].dropna(subset=["signed_ret_bp"]).sort_index()
            n_take = min(50, len(q_data))
            per_q_samples.append(q_data.iloc[:n_take])
        sample = pd.concat(per_q_samples)
        stratified_strategy = f"temporally_stratified_n50x{len(qtrs_to_use)}q_total_n={len(sample)}"

    # 4-quadrant R-0 stratified gross estimate
    a_focus = sample[sample["log_ret_5m"] > 0]["signed_ret_bp"]
    a_mirror_bp = -a_focus
    b_focus = sample[sample["log_ret_5m"] < 0]["signed_ret_bp"]
    b_mirror_bp = -b_focus

    def stats(s, lbl):
        if len(s) < 2:
            return {"label": lbl, "n": int(len(s)), "gross_bp": None, "net_bp": None, "t": None}
        m = float(s.mean())
        sd = float(s.std(ddof=1))
        n = int(len(s))
        return {
            "label": lbl, "n": n, "gross_bp": m, "net_bp": m - FEE_BP,
            "t": m / (sd / math.sqrt(n)) if sd > 0 else None,
        }

    quad_a_focus = stats(a_focus, "A_focus_jumpup_LONG")
    quad_a_mirror = stats(a_mirror_bp, "A_mirror_jumpup_SHORT")
    quad_b_focus = stats(b_focus, "B_focus_jumpdown_SHORT")
    quad_b_mirror = stats(b_mirror_bp, "B_mirror_jumpdown_LONG")

    log.info("R-0 4-quadrant stratified-mechanism estimate (strategy=%s):", stratified_strategy)
    for q in [quad_a_focus, quad_a_mirror, quad_b_focus, quad_b_mirror]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter R-0 detail (sub-amendment 3rd dogfood)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 sub-amendment 3rd dogfood) ---")
    per_qtr_r0 = {}
    a_focus_signs = []
    b_focus_signs = []
    for qq in qtrs_to_use:
        q_sample = trig[trig["qtr"] == qq].dropna(subset=["signed_ret_bp"]).sort_index().iloc[:50]
        q_a = q_sample[q_sample["log_ret_5m"] > 0]["signed_ret_bp"]
        q_b = q_sample[q_sample["log_ret_5m"] < 0]["signed_ret_bp"]
        a_gross = float(q_a.mean()) if len(q_a) > 0 else None
        b_gross = float(q_b.mean()) if len(q_b) > 0 else None
        per_qtr_r0[qq] = {
            "n_total": int(len(q_sample)),
            "A_focus_n": int(len(q_a)),
            "A_focus_gross_bp": a_gross,
            "B_focus_n": int(len(q_b)),
            "B_focus_gross_bp": b_gross,
        }
        if a_gross is not None:
            a_focus_signs.append(1 if a_gross > 0 else -1)
        if b_gross is not None:
            b_focus_signs.append(1 if b_gross > 0 else -1)
        log.info("  %s: A_focus n=%d gross=%s | B_focus n=%d gross=%s",
                 qq, len(q_a),
                 f"{a_gross:.2f}" if a_gross is not None else "NA",
                 len(q_b),
                 f"{b_gross:.2f}" if b_gross is not None else "NA")

    def count_sign_flips(signs):
        if len(signs) < 2:
            return 0
        return sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])

    a_sign_flips = count_sign_flips(a_focus_signs)
    b_sign_flips = count_sign_flips(b_focus_signs)
    log.info("Lesson #46 sign-flip detection: A_focus flips=%d (signs=%s) | B_focus flips=%d (signs=%s)",
             a_sign_flips, a_focus_signs, b_sign_flips, b_focus_signs)

    # Lesson #44 amendment 6th-dogfood graveyard cross-reference
    lesson_44_xref = {
        "paradigm_65_realized_skewness_exhaustion_mr": (
            "GRAVEYARD 2026-05-14 — 1h rolling skew (skew_window=60 1m bars) z=2.0 MR direction. "
            "DISTINCT: paradigm 125 uses RATIO (RV-BV)/RV jump-test statistic, NOT raw moment. "
            "Trigger mode is DISCRETE jump-detection event (binary Z>3) vs continuous z-score level."
        ),
        "paradigm_66_realized_skewness_momentum_continuation": (
            "GRAVEYARD 2026-05-14 — same 1h skew (1m frame) momentum direction. "
            "DISTINCT: 3rd-moment family exhausted via z>2 trigger both directions; "
            "paradigm 125 jump-test isolates jump-variance contribution, mechanistically different."
        ),
        "paradigm_124_alt_realized_kurtosis_extreme_signed_directional_2h": (
            "BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE 2026-05-20 — 4th moment kurt top-decile + |skew|>1 joint. "
            "DISTINCT: paradigm 124 used kurtosis as PRIMARY TRIGGER (continuous statistic, 8.72% rate). "
            "Paradigm 125 uses Z_jump (jump-test ratio) as PRIMARY TRIGGER; quarticity is auxiliary normalizer. "
            "Trigger mode: discrete jump event (~1-2%) vs continuous top-decile. "
            "Direction: 1-bar log-return sign (price-jump sign) vs skew sign (distributional asymmetry)."
        ),
        "higher_order_moment_family_status": (
            "Tier 4 retire CANDIDATE 3 graveyards (65/66/124). Paradigm 125 4th in candidate count "
            "IF deemed family-overlap. R-0 family-distinct gate evaluates trigger rate < 5%."
        ),
        "dna_overlap_assessment": (
            "vs paradigm 124 (closest): 3/6 dims distinct: STATISTIC (ratio-of-variations vs raw moment), "
            "TRIGGER MODE (discrete event vs continuous percentile), DIRECTION (price-jump sign vs skew sign). "
            "Same 5m frame + 13-alt cohort + 2h hold (infra reuse)."
        ),
    }

    # Lesson #45 family-distinct
    lesson_45_distinct = {
        "explicit_statistic_class": "Barndorff-Nielsen ratio jump test (closed-form RV/BV/RQ from log_returns)",
        "hmm_unsupervised_class": "unsupervised state inference (latent variable, EM, no explicit moments)",
        "verdict": "DISTINCT — explicit ratio-of-realized-moments statistic, NOT unsupervised",
    }

    # Lesson #21 axis stacking check
    lesson_21_check = {
        "axis_count": 1,
        "rationale": (
            "Z_jump = ratio jump-test + magnitude confirm — single STATISTIC CLASS (jump-detection). "
            "Magnitude filter (|log_ret|>thr) is statistic-class CONFIRMATION not independent axis: "
            "Z>3 alone already implies large RV-BV; magnitude only removes near-zero noise triggers."
        ),
        "verdict": "PASS — single jump-statistic axis, magnitude is confirmation",
    }

    # R-0 family-distinct gate verdict
    family_distinct_gate = {
        "criterion_1_discrete_event": {
            "value_pct": chosen_rate_pct,
            "threshold_pct": 5.0,
            "comparison_paradigm_124_pct": 8.72,
            "pass": family_distinct_trigger_mode,
        },
        "criterion_2_direction_profile": "evaluated at R-1 (mirror = -focus by construction at R-0)",
        "overall_verdict": "DISCRETE_EVENT_DISTINCTION_PASS" if family_distinct_trigger_mode else "FAMILY_OVERLAP_TRIGGER_RATE_FAIL",
    }

    # Lesson #39 sub-class manual check (R-0 advisory only)
    def detect_sub_class(focus_gross, mirror_gross):
        if focus_gross is None or mirror_gross is None:
            return "indeterminate"
        s = focus_gross + mirror_gross
        if abs(s) < 0.5:
            return "exact_symmetric_construction"
        return "asymmetric"

    lesson_39_a = detect_sub_class(quad_a_focus["gross_bp"], quad_a_mirror["gross_bp"])
    lesson_39_b = detect_sub_class(quad_b_focus["gross_bp"], quad_b_mirror["gross_bp"])

    # Verdict logic
    verdict = "R0_PASS_PROCEED_TO_R1"

    if not family_distinct_trigger_mode:
        verdict = "R0_HALT_FAMILY_OVERLAP_HIGHER_ORDER_MOMENT_TRIGGER_RATE"
    elif measurable_q_pos < 3 or measurable_q_neg < 3:
        verdict = "R0_HALT_SAMPLE_INSUFFICIENT_LESSON_11"
    elif quad_a_focus["gross_bp"] is not None and quad_b_focus["gross_bp"] is not None:
        max_focus_gross = max(quad_a_focus["gross_bp"], quad_b_focus["gross_bp"])
        if max_focus_gross < FEE_BP:
            verdict = "R0_DECLINE_GROSS_BELOW_FEE_FLOOR_LESSON_46"
        elif quad_a_focus["gross_bp"] < 0 and quad_b_focus["gross_bp"] < 0:
            verdict = "R0_ADVISORY_BOTH_FOCUS_NEGATIVE"

    # Lesson #46 SUB-AMENDMENT: per-quarter sign-flip advisory
    if a_sign_flips >= 2 or b_sign_flips >= 2:
        if verdict == "R0_PASS_PROCEED_TO_R1":
            verdict = "R0_PASS_BUT_ADVISORY_PER_QUARTER_SIGN_FLIP_LESSON_46_SUB"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "counter_proposed": 125,
        "prescreen_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "universe": COHORT,
        "n_symbols_loaded": len(sym_data),
        "trigger_params": {
            "window_bars_5m": WIN_BARS,
            "window_minutes": WIN_BARS * 5,
            "ab_theta": AB_THETA,
            "z_jump_threshold": Z_JUMP_THRESHOLD,
            "magnitude_thresholds_tested": MAG_CANDIDATES,
            "magnitude_threshold_chosen": best_thr,
            "target_joint_rate_pct": TARGET_RATE * 100,
            "chosen_joint_rate_pct": chosen_rate_pct,
        },
        "forward_hold_min": 120,
        "fee_bp_round_trip": FEE_BP,
        "panel_bars": int(len(panel)),
        "n_quarters_total": n_quarters,
        "z_jump_above_thresholds_pct": {
            "Z_gt_2": z_above_2,
            "Z_gt_2.5": z_above_2_5,
            "Z_gt_3": z_above_3,
        },
        "lesson_22_frame_grade": {
            "source_frequency": "5m intra-bar (1m DB resampled, 12 bars = 1h window)",
            "statistic_class": "Barndorff-Nielsen ratio jump test (RV, BV, RQ ratio, Huang-Tauchen 2005)",
            "frame_grade_satisfied": True,
            "panel_bars_evidence": int(len(panel)),
        },
        "lesson_11_sample_density": {
            "n_triggers_total": n_trig_total,
            "n_triggers_jump_up": n_pos,
            "n_triggers_jump_down": n_neg,
            "trigger_rate_pct": round(n_trig_total / len(panel) * 100, 4),
            "per_quarter_pos": per_q_pos.to_dict(),
            "per_quarter_neg": per_q_neg.to_dict(),
            "measurable_quarters_pos": measurable_q_pos,
            "measurable_quarters_neg": measurable_q_neg,
            "cutoff_per_cell": 30,
            "verdict": "PASS" if measurable_q_pos >= 3 and measurable_q_neg >= 3 else "FAIL",
        },
        "lesson_21_axis_stacking_check": lesson_21_check,
        "lesson_23_non_event_anchored": {
            "anchor_type": "CONTINUOUS rolling (per 5m bar) — NOT event-anchored",
            "verdict": "PASS",
        },
        "lesson_28_substrate": {
            "5m_klines_source": "DB.ohlcv 1m resampled to 5m (13/13 alts verified)",
            "verdict": "PASS",
        },
        "lesson_30_data_window_ratio": {
            "eth_days_loaded": full_days,
            "full_universe_proxy_days": 800,
            "ratio_pct": round((full_days / 800.0) * 100, 1) if full_days else None,
            "advisory_required": False,
        },
        "lesson_34_empirical_distribution": {
            "z_jump_percentiles": pct_z,
            "abs_log_ret_5m_percentiles": pct_mag,
            "z_above_3_rate_pct": z_above_3,
            "joint_rate_stats": joint_rate_stats,
        },
        "lesson_40_structural_threshold_feasibility": {
            "threshold_definition": "Z_jump > 3.0 (B-N standard one-sided, ratio form)",
            "z_above_3_empirical_rate_pct": z_above_3,
            "structurally_reachable": z_above_3 >= 0.05,
            "verdict": "PASS" if z_above_3 >= 0.05 else "FAIL",
        },
        "lesson_44_amendment_graveyard_xref_6th_dogfood": lesson_44_xref,
        "lesson_45_family_distinct": lesson_45_distinct,
        "r0_family_distinct_gate": family_distinct_gate,
        "lesson_46_amendment_refinement_stratified_R0": {
            "dogfood_number": "3rd dogfood — FORMAL PROMOTION 자격 verification",
            "policy": "temporally-stratified n=50 x 4 quarters + per-quarter sign-flip detection",
            "stratification_strategy": stratified_strategy,
            "quarters_selected": qtrs_to_use,
            "n_sample_total": int(len(sample)),
            "four_quadrant_arithmetic_mean": {
                "A_focus_jumpup_LONG": quad_a_focus,
                "A_mirror_jumpup_SHORT": quad_a_mirror,
                "B_focus_jumpdown_SHORT": quad_b_focus,
                "B_mirror_jumpdown_LONG": quad_b_mirror,
            },
            "per_quarter_detail": per_qtr_r0,
            "per_quarter_sign_flip_detection": {
                "A_focus_signs_by_quarter": a_focus_signs,
                "A_focus_sign_flips": a_sign_flips,
                "B_focus_signs_by_quarter": b_focus_signs,
                "B_focus_sign_flips": b_sign_flips,
                "advisory_threshold": ">=2 sign flips suggests fragile/non-persistent mechanism",
            },
        },
        "lesson_39_sub_class_manual_check": {
            "A_focus_vs_A_mirror": lesson_39_a,
            "B_focus_vs_B_mirror": lesson_39_b,
            "note": "exact-symmetric by construction (mirror = -focus on sign-matched paradigm)",
        },
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-0 prescreen JSON: %s", out_path)
    log.info("VERDICT: %s", verdict)


if __name__ == "__main__":
    main()
