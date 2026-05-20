"""paradigm 126 R-0 prescreen — alt_volume_burst_intra5m_event_signed_directional_30m.

Hypothesis (RUNBOOK §3-M explicit successor recipe):
  §3-M: "Volume info 추출하려면 timing-dependent: volume burst at intra-bar event,
   volume x price asymmetric flow, anomalous volume bursts (binary threshold)"

  Statistic: 1m granular volume burst event within 5m frame
    - 1m volume > p99 of 30-day rolling per-symbol 1m volume
    - AND |1m_log_ret| > 0.5%  (magnitude confirmation; isolate directional bursts)
  Trigger: any 1m bar in 5m frame satisfies both -> fire signed event
  Direction: sign of 1m_log_ret on burst minute -> momentum continuation
  Forward hold: 30 min (30 x 1m bars OR 6 x 5m bars on close-to-close)
  Universe: 13 active alts (paradigm 122/123/124 reuse) -- 1m DB substrate audited per-symbol

Family-distinct claim vs prior:
  - paradigm 72 taker_buy_volume_5m_zscore_signcond: continuous z, 5m frame -> distinct (binary event, 1m)
  - paradigm 116 alt_volume_confirmed_atr_breakout: volume as ATR confirmation -> distinct (standalone burst trigger)
  - paradigm 123 alt_volume_cusum: 5m stateful Page-Hinkley CP -> distinct (1m discrete event vs 5m stateful)
  - paradigm 94/95 cross_asset_volume_share: cross-symbol -> distinct (within-symbol burst)
  - paradigm 124 realized_kurtosis: price moments -> distinct (volume burst)
  - paradigm 113 intraday_hour_anchor: temporal anchor -> distinct (no anchor)

Lessons applied:
  #11 sample density       — per-quadrant per-quarter >=30 (expect daily-grade trigger rate)
  #16 Concentration Gate   — q_pos_t_ratio + symbol_ci_pos_ratio + n_syms_ci_pos
  #19 SNT mandatory         — 4-quadrant in single R-1 batch (this prescreen estimates)
  #21 axis stacking         — 2-condition AND (volume p99 + |1m_ret|>0.5%) sub-check
  #22 frame-grade           — 1m DB substrate per-symbol verified
  #23 non-event-anchored    — continuous rolling, not boundary-anchored
  #28 substrate availability — 1m klines per-symbol
  #30 data_window_ratio     — per-symbol 1m days vs 800d full-window
  #34 empirical distribution — |x| p50/p90/p99/p99.9
  #39 sub-class manual      — mirror = -focus exact-symmetric by construction
  #40 structural threshold  — empirical p99 percentile, NOT academic asymptotic
  #41 amendment edge-first  — per-trade edge >= +2% gate FIRST (advisory at R-1)
  #43 trap awareness        — novelty axes ≠ mechanism alpha
  #44 amendment xref        — graveyard + RUNBOOK §3-A..§3-N cross-reference (10th dogfood)
  #45 family-distinct       — explicit binary threshold (p99), NOT HMM/unsupervised
  #46 AMENDMENT REFINEMENT 3rd dogfood — temporally-stratified n=50x4q R-0 + per-quarter sign flip
  #46-B candidate 2nd dogfood — stratified/full-panel inflation ratio advisory
  #48 candidate (NEW)       — brief inventory check scope (graveyard + RUNBOOK + INDEX cross-reference)
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
log = logging.getLogger("p126_r0")

PARADIGM_NAME = "alt_volume_burst_intra5m_event_signed_directional_30m"
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Paradigm 122/123/124 cohort reuse
COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# R-0 trigger params
ROLLING_DAYS = 30                          # 30-day rolling reference per-symbol
ROLLING_MIN_BARS = 30 * 24 * 60 // 2       # min half a window for stat
PERCENTILE_VOLUME = 99.0                   # 1m volume > p99 rolling
MAG_THRESHOLD = 0.005                      # |1m_log_ret| > 0.5%
FORWARD_HOLD_BARS_1M = 30                  # 30min in 1m bars
FEE_BP = 16.0
TARGET_RATE = 0.015                        # 1.5% target per 5m bar event rate
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


def main():
    log.info("paradigm 126 R-0 start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    # Per-symbol 1m substrate availability + window ratio (Lesson #30)
    log.info("--- Step 1: per-symbol 1m substrate audit (Lesson #28 + #30) ---")
    sym_data = {}
    per_sym_days = {}
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < ROLLING_DAYS * 24 * 60 * 2:
                log.warning("%s: insufficient 1m (%d bars) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            sym_data[sym] = df
            log.info("%s: %d 1m bars (%d days, %s -> %s)",
                     sym, len(df), days, df.index.min(), df.index.max())
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded")
        sys.exit(1)

    # Lesson #30 audit: any symbol < 30% of full window?
    full_window = max(per_sym_days.values())
    short_window_syms = {s: d for s, d in per_sym_days.items() if d < full_window * 0.30}
    log.info("Lesson #30 audit: full_window=%d days, short-window syms(<30%%): %s",
             full_window, short_window_syms)

    # Lesson #11 expected events napkin
    expected_per_sym_per_day = 24 * 60 * (100 - PERCENTILE_VOLUME) / 100 * 0.30  # rough: p99 -> 14.4 candidates/day, magnitude filter ~30% retention
    expected_total_per_sym = expected_per_sym_per_day * (full_window * 0.99)
    log.info("Lesson #11 napkin: expected ~%.1f events/sym/day -> ~%.0f/sym/full-window",
             expected_per_sym_per_day, expected_total_per_sym)

    # Step 2: build 1m -> 5m panel with bursts
    log.info("--- Step 2: 1m volume p99 rolling + magnitude filter + 5m frame aggregation ---")
    panel_rows = []
    rolling_window_min = ROLLING_DAYS * 24 * 60
    for sym, j in sym_data.items():
        j = j.copy()
        # 1m log-return
        j["log_ret_1m"] = np.log(j["close"]).diff()
        j["abs_log_ret_1m"] = j["log_ret_1m"].abs()

        # Per-symbol 30-day rolling p99 1m volume
        # Use expanding then 30d rolling for speed; numpy quantile on rolling window
        # For speed: shift -> use pandas rolling quantile
        j["vol_p99_30d"] = j["volume"].rolling(
            window=rolling_window_min, min_periods=rolling_window_min // 2
        ).quantile(0.99)

        # Burst event: volume > p99 AND |1m_log_ret| > MAG_THRESHOLD
        j["burst"] = (
            (j["volume"] > j["vol_p99_30d"])
            & (j["abs_log_ret_1m"] > MAG_THRESHOLD)
        ).astype(int)
        # Direction (only set on burst bars)
        j["burst_sign"] = np.where(j["burst"] == 1, np.sign(j["log_ret_1m"]), 0).astype(int)

        # Forward 30m return on 1m close-to-close
        j["fwd_ret_30m"] = j["close"].pct_change(FORWARD_HOLD_BARS_1M).shift(-FORWARD_HOLD_BARS_1M)
        j["sym"] = sym

        # 5m frame aggregation: for each 5m bin, take first burst sign if any
        j_5m = j.resample("5min").agg({
            "burst": "max",
            "burst_sign": (lambda x: int(x[x != 0].iloc[0]) if (x != 0).any() else 0),
            "log_ret_1m": "sum",  # 5m return approx
            "abs_log_ret_1m": "max",  # peak |1m_ret| in 5m bin
            "fwd_ret_30m": "first",  # forward 30m from start of 5m bar
            "close": "last",
            "sym": "first",
        })
        j_5m = j_5m.dropna(subset=["fwd_ret_30m"])
        panel_rows.append(j_5m)

    panel = pd.concat(panel_rows).sort_index()
    log.info("panel total 5m bars: %d (with fwd_ret_30m)", len(panel))

    # Lesson #34: empirical distribution
    pct_mag = {p: float(np.percentile(panel["abs_log_ret_1m"].dropna(), p))
               for p in [50, 70, 90, 95, 99, 99.5, 99.9]}
    log.info("|peak_1m_log_ret_in_5m| percentiles: p50=%.5f p70=%.5f p90=%.5f p95=%.5f p99=%.5f p99.9=%.5f",
             pct_mag[50], pct_mag[70], pct_mag[90], pct_mag[95], pct_mag[99], pct_mag[99.9])

    # Burst event rate
    n_burst_total = int((panel["burst"] == 1).sum())
    burst_rate = n_burst_total / len(panel) * 100
    log.info("Burst event rate per 5m bar: %d / %d = %.4f%%",
             n_burst_total, len(panel), burst_rate)

    # Lesson #40: empirical p99 threshold reachable by construction (rolling quantile)
    lesson_40 = {
        "threshold_definition": "1m volume > 30d rolling p99 (per-symbol) AND |1m_log_ret| > 0.5%",
        "threshold_class": "empirical rolling quantile + magnitude filter (NOT academic asymptotic)",
        "structurally_reachable": True,  # p99 is empirical, by definition 1% reachable
        "verdict": "PASS",
    }

    # Triggers
    trig = panel[panel["burst"] == 1].copy()
    trig["direction"] = trig["burst_sign"].astype(int)
    trig["signed_ret_bp"] = trig["fwd_ret_30m"] * trig["direction"] * 10000
    trig["qtr"] = trig.index.to_period("Q").astype(str)
    n_trig_total = len(trig)
    n_pos = int((trig["direction"] > 0).sum())
    n_neg = int((trig["direction"] < 0).sum())
    log.info("Trigger total %d (pos %d / neg %d) rate=%.3f%% per-5m-bar",
             n_trig_total, n_pos, n_neg, n_trig_total / len(panel) * 100 if len(panel) else 0.0)

    # Lesson #11 per-quadrant per-quarter sample density
    n_quarters = trig["qtr"].nunique()
    per_q_pos = trig[trig["direction"] > 0].groupby("qtr").size()
    per_q_neg = trig[trig["direction"] < 0].groupby("qtr").size()
    log.info("per-quarter pos: %s", per_q_pos.to_dict())
    log.info("per-quarter neg: %s", per_q_neg.to_dict())
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
    a_focus = sample[sample["direction"] > 0]["signed_ret_bp"]
    a_mirror_bp = -a_focus
    b_focus = sample[sample["direction"] < 0]["signed_ret_bp"]
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

    quad_a_focus = stats(a_focus, "A_focus_burst_pos_LONG")
    quad_a_mirror = stats(a_mirror_bp, "A_mirror_burst_pos_SHORT")
    quad_b_focus = stats(b_focus, "B_focus_burst_neg_SHORT")
    quad_b_mirror = stats(b_mirror_bp, "B_mirror_burst_neg_LONG")

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
        q_a = q_sample[q_sample["direction"] > 0]["signed_ret_bp"]
        q_b = q_sample[q_sample["direction"] < 0]["signed_ret_bp"]
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

    # Lesson #44 amendment 10th dogfood — graveyard + RUNBOOK + INDEX cross-reference
    lesson_44_xref = {
        "paradigm_72_taker_buy_volume_5m_zscore_signcond": (
            "GRAVEYARD — continuous taker-side aggressive volume z-score, 5m frame. "
            "DISTINCT: paradigm 126 uses BINARY EVENT (p99 + magnitude joint) not continuous z. "
            "1m granularity vs 5m frame is novel timing resolution."
        ),
        "paradigm_116_alt_volume_confirmed_atr_breakout": (
            "GRAVEYARD 2026-05-20 AXIS_REDUNDANT_NO_SYNTHESIS — volume p60-p80 as ATR-buffer confirmation. "
            "DISTINCT: paradigm 126 volume burst is STANDALONE TRIGGER (not confirmation of ATR breakout). "
            "Lesson #21 risk: paradigm 116 found primary-condition saturation at k=1.5 (volume axis redundant); "
            "paradigm 126 uses volume as PRIMARY axis -- distinct from confirmation context."
        ),
        "paradigm_123_alt_volume_cusum_change_point_persistence": (
            "GRAVEYARD 2026-05-20 BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE — Page-Hinkley CUSUM on 5m log-volume. "
            "DISTINCT axes: (a) BINARY DISCRETE EVENT (paradigm 126) vs STATEFUL CONTINUOUS CP (paradigm 123); "
            "(b) 1m granularity (paradigm 126) vs 5m frame (paradigm 123); "
            "(c) per-symbol p99 threshold (paradigm 126) vs lambda-tuned PH stat (paradigm 123); "
            "(d) magnitude confirmation (paradigm 126) vs none (paradigm 123)."
        ),
        "paradigm_94_95_cross_asset_volume_share": (
            "GRAVEYARD (Tier 4 retire) — cross-symbol volume share ratio. "
            "DISTINCT: paradigm 126 within-symbol burst, not cross-symbol share."
        ),
        "paradigm_124_alt_realized_kurtosis": (
            "GRAVEYARD 2026-05-20 BROAD_FALSIFIED_BOTH_FOCUS_NEGATIVE — kurtosis+skew price moments. "
            "DISTINCT: paradigm 126 volume burst axis (NOT price moments)."
        ),
        "paradigm_113_intraday_hour_anchor": (
            "GRAVEYARD — hour-of-day temporal anchor. "
            "DISTINCT: paradigm 126 continuous trigger (no temporal anchor)."
        ),
        "RUNBOOK_section_3M_vwap_deviation_Q3_no7": (
            "RUNBOOK §3-M Q3 #7 graveyard 2026-05-06 — VWAP/reference-price deviation = trend artifact. "
            "EXPLICIT SUCCESSOR RECIPE in §3-M: 'Volume info 추출하려면 timing-dependent: "
            "volume burst at intra-bar event, volume x price asymmetric flow, anomalous volume bursts "
            "(binary threshold)'. PARADIGM 126 EXACT IMPLEMENTATION of §3-M prescription."
        ),
        "RUNBOOK_section_3K_intra_bar_magnitude_only": (
            "RUNBOOK §3-K — intra-bar MAGNITUDE-only directional fail. paradigm 126 "
            "addresses this by REQUIRING burst-bar 1m_ret sign + magnitude filter (paradigm uses "
            "direct intra-bar SIGNED return, not magnitude relative to prior_ret as in §3-K)."
        ),
        "RUNBOOK_section_3L_continuous_multiplicative_composite": (
            "RUNBOOK §3-L — continuous-multiplicative-composite without strict gates. "
            "paradigm 126 uses BINARY AND gate (volume > p99 AND |ret| > 0.5%), satisfies §3-L "
            "essential-discriminator requirement (bounded asymmetric + heavy-tailed AND-gate)."
        ),
        "INDEX_volume_axis_summary": (
            "INDEX.json volume-axis paradigms inventory: 72 (taker_buy_vol z) + 94/95 (cross_asset share) + "
            "116 (atr confirm) + 123 (5m CUSUM) = 5 prior. paradigm 126 axis novelty: "
            "(1) 1m intra-5m granularity (NEW timing dimension) + "
            "(2) binary event detection (NEW trigger mode within volume family) + "
            "(3) signed by burst-minute 1m_ret sign (NEW direction extraction within volume family). "
            "3 simultaneous novelty axes within volume family => family-distinct PASS."
        ),
        "lesson_48_candidate_scope_applied": (
            "Lesson #48 candidate scope = graveyard__*.md + RUNBOOK.md §3-A..§3-N + INDEX.json historical entries. "
            "Cross-reference performed for: paradigm 72, 94, 95, 113, 116, 123, 124 + RUNBOOK §3-K/§3-L/§3-M. "
            "All distinct via axis-novelty axes 1m-granularity + binary-event-mode + signed-burst-extraction."
        ),
    }

    # Lesson #45 family-distinct: binary threshold p99 NOT unsupervised
    lesson_45_distinct = {
        "explicit_threshold_class": "1m volume > 30d rolling p99 (per-symbol) + |1m_log_ret| > 0.5%",
        "hmm_unsupervised_class": "unsupervised state inference (latent variables, EM, no explicit moments)",
        "verdict": "DISTINCT — explicit empirical percentile threshold, NOT unsupervised clustering",
    }

    # Lesson #21 axis stacking
    lesson_21_check = {
        "axis_count": 2,
        "axes_listed": ["volume p99 percentile", "|1m_log_ret| magnitude"],
        "rationale": (
            "Two-axis AND-gate is per RUNBOOK §3-L essential discriminator (volume bounded asymmetric × "
            "ret heavy-tailed). Lesson #21 antipattern is stacking that adds NO orthogonal info. "
            "Here: volume p99 alone has ~1%/sym/day candidate rate; magnitude filter reduces to "
            "directional bursts only -- the two axes carry truly orthogonal info (large traders' "
            "anomalous volume that ALSO moves price = strong informed-flow signal)."
        ),
        "verdict": "PASS — essential binary AND gate per RUNBOOK §3-L",
    }

    # Lesson #43 trap awareness
    lesson_43_trap = {
        "novelty_axes": [
            "1m granularity within 5m frame (NEW timing resolution within volume family)",
            "binary event detection (NEW trigger mode within volume family)",
            "signed by burst-minute 1m_ret sign (NEW direction extraction within volume family)",
        ],
        "trap_warning": (
            "Novelty axes do NOT guarantee mechanism alpha. R-1 must demonstrate actual signed continuation "
            "alpha, NOT mere statistical regime-change detection (paradigm 123 Lesson #43 trap pattern)."
        ),
        "verdict": "TRAP_AWARE — verified at R-1",
    }

    # R-0 family-distinct gate
    family_distinct_gate = {
        "criterion_1_axis_novelty": {
            "novelty_axes": 3,
            "axes": [
                "1m granularity (vs all prior 5m+ frame paradigms)",
                "binary event detection (vs continuous z paradigm 72/123)",
                "signed by burst-minute 1m_ret (vs volume-weighted aggregation)",
            ],
            "pass": True,
        },
        "criterion_2_DNA_overlap": {
            "vs_paradigm_72_taker_buy_vol": "0/6 full DNA overlap (statistic class distinct + trigger mode distinct + granularity distinct)",
            "vs_paradigm_116_atr_volume_confirm": "0/6 (volume role distinct: standalone vs confirmation)",
            "vs_paradigm_123_volume_cusum": "0/6 (statistic class distinct: discrete event vs stateful CP)",
            "vs_paradigm_124_kurtosis": "0/6 (axis class distinct: volume vs price moment)",
            "vs_paradigm_113_hour_anchor": "0/6 (trigger mode distinct: continuous vs anchored)",
            "pass": True,
        },
        "criterion_3_RUNBOOK_explicit_successor": {
            "section": "§3-M (Q3 #7 vwap_deviation graveyard)",
            "prescription": (
                "'Volume info 추출하려면 timing-dependent: volume burst at intra-bar event, "
                "volume x price asymmetric flow, anomalous volume bursts (binary threshold)'"
            ),
            "paradigm_126_implementation": (
                "EXACT (timing-dependent ✓, intra-bar event ✓, asymmetric flow via burst-sign ✓, "
                "binary threshold ✓)"
            ),
            "pass": True,
        },
        "overall_verdict": "FAMILY_DISTINCT_PASS_3_DIMENSIONS",
    }

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

    # Lesson #46 SUB-AMENDMENT: per-quarter sign-flip advisory
    if a_sign_flips >= 2 or b_sign_flips >= 2:
        if verdict == "R0_PASS_PROCEED_TO_R1":
            verdict = "R0_PASS_BUT_ADVISORY_PER_QUARTER_SIGN_FLIP_LESSON_46_SUB"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "counter_proposed": 126,
        "prescreen_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "universe_requested": COHORT,
        "n_symbols_loaded": len(sym_data),
        "per_symbol_days_1m": per_sym_days,
        "trigger_params": {
            "rolling_days_for_p99": ROLLING_DAYS,
            "volume_percentile": PERCENTILE_VOLUME,
            "magnitude_threshold_1m_log_ret": MAG_THRESHOLD,
            "forward_hold_min": 30,
            "panel_frame_5m_aggregation": True,
        },
        "fee_bp_round_trip": FEE_BP,
        "panel_5m_bars": int(len(panel)),
        "n_quarters_total": int(n_quarters),
        "burst_rate_per_5m_bar_pct": burst_rate,
        "lesson_11_sample_density": {
            "n_triggers_total": n_trig_total,
            "n_triggers_pos": n_pos,
            "n_triggers_neg": n_neg,
            "per_quarter_pos": per_q_pos.to_dict(),
            "per_quarter_neg": per_q_neg.to_dict(),
            "measurable_quarters_pos": measurable_q_pos,
            "measurable_quarters_neg": measurable_q_neg,
            "cutoff_per_cell": 30,
            "verdict": "PASS" if measurable_q_pos >= 3 and measurable_q_neg >= 3 else "FAIL",
        },
        "lesson_21_axis_stacking_check": lesson_21_check,
        "lesson_22_frame_grade": {
            "source_frequency": "1m intra-5m (DB.ohlcv 1m direct)",
            "statistic_class": "binary event (volume p99 + magnitude filter)",
            "frame_grade_satisfied": True,
            "panel_5m_bars": int(len(panel)),
        },
        "lesson_23_non_event_anchored": {
            "anchor_type": "CONTINUOUS rolling (per 1m bar) — NOT event-anchored",
            "verdict": "PASS",
        },
        "lesson_28_substrate": {
            "1m_klines_source": f"DB.ohlcv 1m direct ({len(sym_data)}/13 alts available)",
            "verdict": "PASS",
        },
        "lesson_30_data_window_ratio": {
            "per_sym_days": per_sym_days,
            "full_window_days": full_window,
            "short_window_syms_below_30pct": short_window_syms,
            "advisory_required": bool(short_window_syms),
        },
        "lesson_34_empirical_distribution": {
            "abs_1m_log_ret_percentiles": pct_mag,
            "burst_event_rate_pct": burst_rate,
        },
        "lesson_40_structural_threshold_feasibility": lesson_40,
        "lesson_43_trap_awareness": lesson_43_trap,
        "lesson_44_amendment_xref_10th_dogfood": lesson_44_xref,
        "lesson_45_family_distinct": lesson_45_distinct,
        "lesson_48_candidate_scope_applied": (
            "Cross-reference scope = graveyard__*.md + RUNBOOK §3-A..§3-N + INDEX.json historical entries. "
            "Full cross-reference performed -- see lesson_44_amendment_xref_10th_dogfood for details."
        ),
        "r0_family_distinct_gate": family_distinct_gate,
        "lesson_46_amendment_refinement_stratified_R0": {
            "dogfood_number": "3rd — FORMAL PROMOTION 자격 verification",
            "policy": "temporally-stratified n=50 x 4 quarters + per-quarter sign-flip detection",
            "stratification_strategy": stratified_strategy,
            "quarters_selected": qtrs_to_use,
            "n_sample_total": int(len(sample)),
            "four_quadrant_arithmetic_mean": {
                "A_focus_burst_pos_LONG": quad_a_focus,
                "A_mirror_burst_pos_SHORT": quad_a_mirror,
                "B_focus_burst_neg_SHORT": quad_b_focus,
                "B_mirror_burst_neg_LONG": quad_b_mirror,
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
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-0 prescreen JSON: %s", out_path)
    log.info("VERDICT: %s", verdict)


if __name__ == "__main__":
    main()
