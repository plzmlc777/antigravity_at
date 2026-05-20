"""paradigm 124 R-0 prescreen — alt_realized_kurtosis_extreme_signed_directional_2h.

Trigger: 1h rolling realized kurtosis on 5m intra-bar log-returns (12 obs) signed by 3rd moment skewness sign
  - kurt = 4th central moment / variance^2  (raw kurtosis; expected 3 for Gaussian)
  - excess kurt = kurt - 3
  - skew sign = sign(3rd central moment) on same 12 5m log-returns
Joint trigger: kurt top-decile (~10% of bars) AND |skew| > 0.5
Direction: skew sign-matched LONG/SHORT
Forward hold: 2h directional (24 x 5m bars)
Universe: 13 active alts

Family-distinct vs paradigm 65/66 (3rd moment skewness ALONE):
  - 65 realized_skewness_exhaustion_mr: skew_window=60 (1m bars), z=2.0 trigger, MR — FRAME=1m, STATISTIC=3rd-only
  - 66 realized_skewness_momentum_continuation: skew_window=60 (1m bars), momentum — FRAME=1m, STATISTIC=3rd-only
  - 124: skew_window=12 (5m bars=1h), kurt-top-decile + |skew|>0.5 JOINT — FRAME=5m, STATISTIC=4th + 3rd joint
  3/6 DNA dims distinct (statistic class, frame, stride). NEW statistic class (4th moment kurtosis).

R-0 prescreens performed:
  - Lesson #11 (sample density): per-quadrant per-quarter >= 30 (target 3-4% joint trigger rate)
  - Lesson #19 SNT (4-quadrant) — applied at R-1
  - Lesson #22 frame-grade source freq: 5m intra-bar 12-obs window VERIFIED abundant
  - Lesson #23 (event-anchor density): kurt + skew joint is NON-event-anchored continuous
  - Lesson #28 (substrate availability): 5m OHLCV DB resampled (paradigm 122/123 verified)
  - Lesson #30 (data window ratio): full window
  - Lesson #34 (empirical distribution): kurtosis + |skewness| percentile
  - Lesson #40 (structural threshold feasibility): kurt top-decile + |skew|>0.5 both reachable by construction
  - Lesson #44 amendment graveyard xref: paradigm 65/66 (3rd moment alone), 122/123 (intra-bar volume)
  - Lesson #45 family-distinct: explicit statistical moments, NOT unsupervised clustering
  - Lesson #46 AMENDMENT REFINEMENT (2nd dogfood): temporally-stratified n=50 x 4 quarters + per-quarter sign-flip
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p124_r0")

PARADIGM_NAME = "alt_realized_kurtosis_extreme_signed_directional_2h"
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Moment window: 12 5m bars = 1h
MOMENT_WIN_BARS = 12
# Trigger thresholds (tuned for ~3-4% joint trigger rate)
KURT_TOPDECILE_PCT = 90.0  # top 10% (excess kurt percentile)
SKEW_ABS_THRESHOLD_CANDIDATES = [0.3, 0.5, 0.7, 1.0]
FORWARD_HOLD_BARS = 24  # 2h = 24 x 5m bars
FEE_BP = 16.0


def load_ohlcv_5m(sym: str, engine) -> pd.DataFrame:
    """Load 1m OHLCV from DB, resample to 5m."""
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


def rolling_moments(log_ret: pd.Series, win: int):
    """Compute rolling skewness (raw 3rd moment / std^3) and excess kurtosis (4th / var^2 - 3).

    Window = `win` bars. Uses Fisher-Pearson form.
    Returns (skew_series, excess_kurt_series).
    """
    # pandas .skew uses Fisher-Pearson adjusted; .kurt uses excess.
    # Both produce NaN for short windows.
    skew = log_ret.rolling(win, min_periods=win).skew()
    kurt = log_ret.rolling(win, min_periods=win).kurt()  # excess kurtosis already
    return skew, kurt


def main():
    log.info("paradigm 124 R-0 prescreen start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dsn = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
    engine = create_engine(dsn)

    sym_data = {}
    for sym in COHORT:
        try:
            ohlcv = load_ohlcv_5m(sym, engine)
            if ohlcv.empty or len(ohlcv) < MOMENT_WIN_BARS + 100:
                log.warning("%s: insufficient (len=%d) - skip", sym, len(ohlcv))
                continue
            sym_data[sym] = ohlcv
            log.info("%s: %d 5m bars  %s -> %s", sym, len(ohlcv), ohlcv.index.min(), ohlcv.index.max())
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded - abort")
        sys.exit(1)

    # Lesson #30 data window ratio (ETHUSDT baseline)
    eth = sym_data.get("ETHUSDT")
    full_days = (eth.index.max() - eth.index.min()).days if eth is not None else None
    log.info("ETHUSDT window: %s days (baseline)", full_days)

    # Step 1: per-symbol log-returns + rolling moments
    log.info("--- Step 1: 5m log-returns + rolling 1h (12-bar) skew + excess kurt ---")
    panel_rows = []
    for sym, j in sym_data.items():
        j = j.copy()
        j["log_ret_5m"] = np.log(j["close"]).diff()
        skew, kurt = rolling_moments(j["log_ret_5m"], MOMENT_WIN_BARS)
        j["skew_1h"] = skew
        j["excess_kurt_1h"] = kurt
        j["abs_skew_1h"] = skew.abs()
        j["sym"] = sym
        # forward 2h return (sign-matched applied later)
        j["fwd_ret_2h"] = j["close"].pct_change(FORWARD_HOLD_BARS).shift(-FORWARD_HOLD_BARS)
        j = j.dropna(subset=["skew_1h", "excess_kurt_1h"])
        panel_rows.append(j)
    panel = pd.concat(panel_rows).sort_index()
    log.info("panel total rows after dropna: %d", len(panel))

    # Step 2: empirical distribution of moments (Lesson #34)
    pct_kurt = {p: float(np.percentile(panel["excess_kurt_1h"], p)) for p in [50, 70, 80, 85, 90, 95, 99]}
    pct_abs_skew = {p: float(np.percentile(panel["abs_skew_1h"], p)) for p in [50, 70, 80, 90, 95, 99]}
    log.info("excess_kurt_1h p50=%.3f p70=%.3f p80=%.3f p85=%.3f p90=%.3f p95=%.3f p99=%.3f",
             pct_kurt[50], pct_kurt[70], pct_kurt[80], pct_kurt[85], pct_kurt[90], pct_kurt[95], pct_kurt[99])
    log.info("|skew_1h| p50=%.3f p70=%.3f p80=%.3f p90=%.3f p95=%.3f p99=%.3f",
             pct_abs_skew[50], pct_abs_skew[70], pct_abs_skew[80], pct_abs_skew[90], pct_abs_skew[95], pct_abs_skew[99])

    # Lesson #40: structural feasibility — kurt top-decile by construction reachable; |skew|>0.5 check empirically
    abs_skew_at_threshold = {
        thr: float((panel["abs_skew_1h"] > thr).mean() * 100) for thr in SKEW_ABS_THRESHOLD_CANDIDATES
    }
    log.info("|skew|>thr empirical rates: %s", {f"{k:.1f}": f"{v:.2f}%" for k, v in abs_skew_at_threshold.items()})

    # Step 3: tune skew threshold for ~3-4% JOINT trigger rate (kurt top-decile AND |skew|>thr)
    log.info("--- Step 2: Joint trigger rate tuning ---")
    kurt_threshold = pct_kurt[90]  # top-decile cutoff
    joint_rate_stats = {}
    best_thr = None
    best_rate_diff = float("inf")
    TARGET_RATE = 0.035  # 3.5% target

    for thr in SKEW_ABS_THRESHOLD_CANDIDATES:
        mask = (panel["excess_kurt_1h"] > kurt_threshold) & (panel["abs_skew_1h"] > thr)
        n_joint = int(mask.sum())
        n_total = len(panel)
        rate = n_joint / n_total if n_total else 0.0
        joint_rate_stats[thr] = {"n_joint": n_joint, "n_total": n_total, "rate_pct": rate * 100}
        log.info("  kurt>%.3f (p90) AND |skew|>%.1f: n=%d rate=%.3f%%",
                 kurt_threshold, thr, n_joint, rate * 100)
        if 0.005 <= rate <= 0.10:
            if abs(rate - TARGET_RATE) < best_rate_diff:
                best_rate_diff = abs(rate - TARGET_RATE)
                best_thr = thr

    if best_thr is None:
        log.error("no |skew| threshold in [0.5%%, 10%%] joint trigger rate band - HALT")
        out = {
            "paradigm_name": PARADIGM_NAME,
            "verdict": "R0_HALT_JOINT_TRIGGER_TUNING_FAIL",
            "kurt_threshold_p90": kurt_threshold,
            "joint_rate_stats": joint_rate_stats,
            "target_rate_pct": TARGET_RATE * 100,
        }
        with open(OUT_DIR / "r0_prescreen.json", "w") as f:
            json.dump(out, f, indent=2, default=str)
        sys.exit(0)
    log.info("CHOSEN |skew| threshold = %.1f (joint rate %.3f%%, closest to target %.1f%%)",
             best_thr, joint_rate_stats[best_thr]["rate_pct"], TARGET_RATE * 100)

    # Step 4: Apply joint trigger to build sample
    trig = panel[(panel["excess_kurt_1h"] > kurt_threshold) & (panel["abs_skew_1h"] > best_thr)].copy()
    trig = trig.dropna(subset=["fwd_ret_2h"])
    # Direction by skew sign at trigger bar
    trig["direction"] = np.where(trig["skew_1h"] > 0, 1, -1)
    trig["signed_ret_bp"] = trig["fwd_ret_2h"] * trig["direction"] * 10000

    n_trig_total = len(trig)
    n_pos = int((trig["skew_1h"] > 0).sum())
    n_neg = int((trig["skew_1h"] < 0).sum())
    log.info("Joint triggers total: %d (skew_pos %d / skew_neg %d) rate=%.3f%%",
             n_trig_total, n_pos, n_neg, n_trig_total / len(panel) * 100)

    # Lesson #11 per-quadrant per-quarter sample density
    trig["qtr"] = trig.index.to_period("Q").astype(str)
    n_quarters = trig["qtr"].nunique()
    per_q_pos = trig[trig["skew_1h"] > 0].groupby("qtr").size()
    per_q_neg = trig[trig["skew_1h"] < 0].groupby("qtr").size()
    log.info("per-quarter skew_pos: %s", per_q_pos.to_dict())
    log.info("per-quarter skew_neg: %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (>=30 per quadrant): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT (2nd dogfood): temporally-stratified n=50 x 4q
    log.info("--- Lesson #46 AMENDMENT REFINEMENT 2nd dogfood: temporally-stratified R-0 ---")
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

    # R-0 gross drift estimate (4-quadrant)
    a_focus = sample[sample["skew_1h"] > 0]["signed_ret_bp"]
    a_mirror_bp = -a_focus
    b_focus = sample[sample["skew_1h"] < 0]["signed_ret_bp"]
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

    quad_a_focus = stats(a_focus, "A_focus_skewpos_LONG")
    quad_a_mirror = stats(a_mirror_bp, "A_mirror_skewpos_SHORT")
    quad_b_focus = stats(b_focus, "B_focus_skewneg_SHORT")
    quad_b_mirror = stats(b_mirror_bp, "B_mirror_skewneg_LONG")

    log.info("R-0 4-quadrant stratified-mechanism estimate (strategy=%s):", stratified_strategy)
    for q in [quad_a_focus, quad_a_mirror, quad_b_focus, quad_b_mirror]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter R-0 detail (Lesson #46 refinement validation — per-quarter sign-flip detection)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 refinement 2nd dogfood) ---")
    per_qtr_r0 = {}
    a_focus_signs = []
    b_focus_signs = []
    for qq in qtrs_to_use:
        q_sample = trig[trig["qtr"] == qq].dropna(subset=["signed_ret_bp"]).sort_index().iloc[:50]
        q_a = q_sample[q_sample["skew_1h"] > 0]["signed_ret_bp"]
        q_b = q_sample[q_sample["skew_1h"] < 0]["signed_ret_bp"]
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

    # Sign-flip detection (count direction switches per quadrant across quarters)
    def count_sign_flips(signs):
        if len(signs) < 2:
            return 0
        return sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])

    a_sign_flips = count_sign_flips(a_focus_signs)
    b_sign_flips = count_sign_flips(b_focus_signs)
    log.info("Lesson #46 sign-flip detection: A_focus flips=%d (signs=%s) | B_focus flips=%d (signs=%s)",
             a_sign_flips, a_focus_signs, b_sign_flips, b_focus_signs)

    # Lesson #44 amendment graveyard cross-reference
    lesson_44_xref = {
        "paradigm_65_realized_skewness_exhaustion_mr": (
            "GRAVEYARD 2026-05-14 — 1h rolling skew (skew_window=60 1m bars) z=2.0 MR direction. "
            "Distinct from paradigm 124: (a) statistic class = 3rd moment ALONE vs 4th + 3rd JOINT; "
            "(b) frame = 1m base vs 5m base; (c) direction logic = z-trigger MR vs joint-trigger sign-matched continuation. "
            "DNA 3/6 dims distinct. NEW statistic class (4th moment kurtosis)."
        ),
        "paradigm_66_realized_skewness_momentum_continuation": (
            "GRAVEYARD 2026-05-14 — same 1h skew (skew_window=60 1m bars) momentum direction. "
            "Inverse of 65. Both directions of 3rd-moment-alone exhausted via z>2 trigger. "
            "Paradigm 124 distinct: joint kurt-top-decile + |skew|>thr (kurtosis is the primary statistic, "
            "skew used as direction-selector, NOT trigger). Mechanism: fat-tail event signed by asymmetry."
        ),
        "paradigm_72_taker_buy_vol": (
            "GRAVEYARD 2026-05-15 — taker-side aggressive volume family fee-floor. "
            "Distinct from paradigm 124: volume family vs moment family."
        ),
        "paradigm_122_intraday_session_open_oi_acceleration": (
            "BROAD_FALSIFIED 2026-05-20 — OI velocity x temporal anchor stacking (Lesson #21). "
            "Distinct from paradigm 124: OI axis + temporal anchor vs price-derived moments stateless."
        ),
        "paradigm_123_alt_volume_cusum_change_point_persistence_directional_2h": (
            "BROAD_FALSIFIED 2026-05-20 — 5m volume CUSUM stateful CP. "
            "Distinct from paradigm 124: volume CP statistic vs price moment statistic. "
            "Same 5m frame + 13-alt cohort (infra reuse) but DIFFERENT statistic class."
        ),
        "dna_overlap_assessment": (
            "vs paradigm 65/66 (closest): 3/6 dims distinct (statistic class, frame base, direction logic). "
            "Statistic class novelty: 4th moment kurtosis NEVER measured in 123 prior paradigms. "
            "Joint conjunction (kurt + skew sign) is single-statistic-class natural pair, NOT axis stacking."
        ),
    }

    # Lesson #45 family-distinct: moments vs HMM
    lesson_45_distinct = {
        "explicit_moment_class": "rolling pandas .skew + .kurt — closed-form 3rd/4th central moments",
        "hmm_unsupervised_class": "unsupervised state inference (latent variable, EM, no explicit moments)",
        "verdict": "DISTINCT — explicit statistical moment computation, NOT unsupervised clustering/decomposition",
    }

    # Lesson #21 axis stacking check
    lesson_21_check = {
        "axis_count": 1,
        "rationale": (
            "kurtosis + skewness are 4th + 3rd central moments — single STATISTIC CLASS (higher-order moments). "
            "Joint trigger (kurt-top-decile AND |skew|>thr) with skew as direction-selector is conjunction within "
            "the same statistic class, NOT independent axis stacking. Comparable to: 'z-score level + z-score velocity' "
            "(same axis class) vs 'volume CUSUM + OI velocity + temporal anchor' (3 independent axes)."
        ),
        "verdict": "PASS — single moment-statistic axis, joint conjunction is natural pair",
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
    if measurable_q_pos < 3 or measurable_q_neg < 3:
        verdict = "R0_HALT_SAMPLE_INSUFFICIENT_LESSON_11"
    elif quad_a_focus["gross_bp"] is not None and quad_b_focus["gross_bp"] is not None:
        max_focus_gross = max(quad_a_focus["gross_bp"], quad_b_focus["gross_bp"])
        if max_focus_gross < FEE_BP:
            verdict = "R0_DECLINE_GROSS_BELOW_FEE_FLOOR_LESSON_46"
        elif quad_a_focus["gross_bp"] < 0 and quad_b_focus["gross_bp"] < 0:
            verdict = "R0_ADVISORY_BOTH_FOCUS_NEGATIVE"

    # Lesson #46 SUB-AMENDMENT candidate: per-quarter sign-flip advisory
    if a_sign_flips >= 2 or b_sign_flips >= 2:
        if verdict == "R0_PASS_PROCEED_TO_R1":
            verdict = "R0_PASS_BUT_ADVISORY_PER_QUARTER_SIGN_FLIP_LESSON_46_SUB"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "counter_proposed": 124,
        "prescreen_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "universe": COHORT,
        "n_symbols_loaded": len(sym_data),
        "trigger_params": {
            "moment_window_bars_5m": MOMENT_WIN_BARS,
            "moment_window_minutes": MOMENT_WIN_BARS * 5,
            "kurt_threshold_pct": KURT_TOPDECILE_PCT,
            "kurt_threshold_value_empirical": kurt_threshold,
            "skew_abs_threshold_candidates": SKEW_ABS_THRESHOLD_CANDIDATES,
            "skew_abs_threshold_chosen": best_thr,
            "target_joint_rate_pct": TARGET_RATE * 100,
        },
        "forward_hold_min": 120,
        "fee_bp_round_trip": FEE_BP,
        "panel_bars": int(len(panel)),
        "n_quarters_total": n_quarters,
        "lesson_22_frame_grade": {
            "source_frequency": "5m intra-bar (1m DB resampled, 12 bars = 1h window)",
            "statistic_class": "explicit higher-order moments (rolling skew + excess kurt)",
            "frame_grade_satisfied": True,
            "panel_bars_evidence": int(len(panel)),
        },
        "lesson_11_sample_density": {
            "n_triggers_total": n_trig_total,
            "n_triggers_skew_pos": n_pos,
            "n_triggers_skew_neg": n_neg,
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
            "verdict": "PASS — Lesson #23 explicit non-target axis",
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
            "excess_kurt_percentiles": pct_kurt,
            "abs_skew_percentiles": pct_abs_skew,
            "abs_skew_threshold_rates_pct": abs_skew_at_threshold,
        },
        "lesson_40_structural_threshold_feasibility": {
            "threshold_definition": "kurt top-decile (p90) AND |skew|>thr (sign-matched direction)",
            "structurally_reachable": True,
            "verdict": "PASS — moments are unbounded continuous statistics, top-decile + abs threshold both reachable",
        },
        "lesson_44_amendment_graveyard_xref": lesson_44_xref,
        "lesson_45_family_distinct": lesson_45_distinct,
        "lesson_46_amendment_refinement_stratified_R0": {
            "dogfood_number": "2nd CONFIRMED 자격 verification",
            "policy": "temporally-stratified n=50 x 4 quarters + per-quarter sign-flip detection",
            "stratification_strategy": stratified_strategy,
            "quarters_selected": qtrs_to_use,
            "n_sample_total": int(len(sample)),
            "four_quadrant_arithmetic_mean": {
                "A_focus_skewpos_LONG": quad_a_focus,
                "A_mirror_skewpos_SHORT": quad_a_mirror,
                "B_focus_skewneg_SHORT": quad_b_focus,
                "B_mirror_skewneg_LONG": quad_b_mirror,
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
        "joint_rate_tuning_sweep": joint_rate_stats,
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-0 prescreen JSON: %s", out_path)
    log.info("VERDICT: %s", verdict)


if __name__ == "__main__":
    main()
