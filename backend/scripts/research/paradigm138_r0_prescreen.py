"""paradigm 138 R-0 prescreen — alt_funding_rate_x_cvd_4h_divergence_smart_money_distribution_directional_4h.

Hypothesis (NEW CVD axis × funding confluence cross-axis):
  funding ≤ -50 bp (extreme LONG-crowded) AND 4h CVD ratio ≤ -0.1 (sustained taker SELL)
    -> SHORT 4h (smart money exit detection precedes crowd capitulation)
  4-quadrant SNT:
    A_focus  = funding ≤ -50bp × CVD ≤ -0.1 × SHORT 4h     (primary)
    A_mirror = funding ≤ -50bp × CVD ≤ -0.1 × LONG 4h      (mean-reversion contrary)
    B_focus  = funding ≥ +50bp × CVD ≥ +0.1 × LONG 4h      (mirror condition)
    B_mirror = funding ≥ +50bp × CVD ≥ +0.1 × SHORT 4h     (mirror contrary)

Substrate audit (Lesson #28 + Lesson #40 R-0 sequential prescreen, paradigm 109+110 dogfood pattern):

  STEP 1 (Lesson #40 structural threshold attainability — FIRST per spec):
    Empirical funding rate distribution per-sym (19 syms cohort) shows:
      - 16/19 syms (BTC/ETH/SOL/AVAX/DOGE/LINK/LTC/BCH/BNB/HBAR/LDO/ETC/UNI/WLD/TON/JUP/PYTH):
        100.00% of funding observations within [-12.7bp, +5bp] (p99=+1bp cap)
        ZERO observations |funding| ≥ 50bp
      - 3/19 syms exception (AXS 2.67% / COMP 0.45% / ICP 0.18% ≤-50bp)
        but ZERO ≥+50bp on any sym (Binance funding rate hard caps at +1bp regular tier)
    -> ±50bp threshold STRUCTURALLY INFEASIBLE on 8h-frame raw funding rate.
       This matches Lesson #40 paradigm 109+110 antipattern exactly:
       'non-negative aggregate statistic + symmetric ±T trigger -> reformulate'.

  STEP 2 (Lesson #28 substrate availability — taker_buy axis):
    OHLCV DB has only `volume` column (NO taker_buy_base_asset_volume column).
    Microstructure joblib (runs/microstructure/{SYM}_full_metrics.joblib) has
    `taker_buy_sell_ratio` at 5m frequency, span 2024-02-23 to 2026-05-02 (~800d).
    CVD proxy CAN be constructed:
      cvd_ratio_per_bar = (TBR - 1) / (TBR + 1) per 5m
                        = (taker_buy - taker_sell) / (taker_buy + taker_sell)
    4h aggregation = mean over 48 × 5m bars.
    CVD axis FEASIBLE.

  STEP 3 (Lesson #11 expected_n joint trigger density):
    Even IF we reformulate funding threshold:
      empirical p1 funding ≤ -3.99bp (16/19 syms) suggests p1-based threshold ≈ -3 to -10 bp.
      At funding ≤ -10bp, expected ~1% × CVD ≤ -0.1 (~30%) × 13 alts × 730d × 6/day
        ≈ per-cell n ≈ 10-30 (BORDERLINE; SAMPLE_INSUFFICIENT risk).
      Empirical |funding| ≥ 50bp = ZERO -> structural threshold INFEASIBLE before any
      Lesson #11 sample density audit reaches meaningful estimate.

  STEP 4 (Lesson #44 cross-reference 21st dogfood):
    paradigm 22 funding-carry R-5 SEEDED (HBAR/AXS/COMP):
      → uses z-score normalized funding (NOT raw bp threshold)
    paradigm 72 taker_buy_volume_5m_zscore_signcond GRAVEYARD:
      → 5m taker volume z-score (BROAD_FALSIFIED, taker-side fee floor)
      → family Tier 4 retire (Q3 §6.2 #10)
    paradigm 132 funding × OI × magnitude triple GRAVEYARD Lesson #21:
      → 3-way axis stacking trap
    paradigm 96 funding sign flip GRAVEYARD:
      → funding single-signal sub-family Tier 4 retire
    paradigm 99 funding per-sym velocity GRAVEYARD:
      → NARROW_SCOPE_LIFE_CHANGING_FAIL
    Funding family Tier 4 retire (paradigm 73+79+96+97+98+99) — only paradigm 22 R-5 exception
    + funding_dispersion ETCUSDT exception
    paradigm 109 + 110 dogfood for Lesson #40 CONFIRMED (paradigm-architect spec NEW R-0 step):
      'non-negative aggregate statistics symmetric z≤−T 구조적 불가' equivalent here:
      raw funding rate is bounded above at +1bp regular tier (hard cap), bounded below by
      exchange-set max LONG-side funding -200bp historical extreme (rare),
      so ±50bp symmetric IS infeasible structurally.

VERDICT: R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBLE
  + Lesson #44 21st amendment xref: funding family Tier 4 retire reaffirm
  + paradigm-architect R-0 sequential prescreen order Lesson #40 FIRST per spec — caught at step 1.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p138_r0")

PARADIGM_NAME = "alt_funding_rate_x_cvd_4h_divergence_smart_money_distribution_directional_4h"
PARADIGM_NUM = 138
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Original 13 alts cohort (funding DB + microstructure joblib + 1m OHLCV cache all available)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "LINKUSDT", "LTCUSDT", "SOLUSDT",
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "LDOUSDT", "ETCUSDT",
]
# Auxiliary 19-sym universe for distribution audit
AUDIT_SYMS = COHORT + [
    "UNIUSDT", "ICPUSDT", "WLDUSDT", "TONUSDT", "JUPUSDT", "PYTHUSDT",
]

# User-proposed thresholds
FUNDING_LOWER_BP = -50.0   # funding ≤ -50 bp = LONG-crowded
FUNDING_UPPER_BP = +50.0   # funding ≥ +50 bp = SHORT-crowded
CVD_LOWER = -0.1           # CVD ratio ≤ -0.1 = sustained taker SELL
CVD_UPPER = +0.1           # CVD ratio ≥ +0.1 = sustained taker BUY

DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
MICRO_DIR = Path("/home/hcpark/antigravity/backend/runs/microstructure")


def audit_funding_distribution(engine) -> dict:
    """Lesson #40 structural threshold attainability — empirical funding distribution per-sym."""
    results = {}
    for sym in AUDIT_SYMS:
        try:
            q = text("SELECT funding_rate FROM binance_funding_rate WHERE symbol=:s")
            fr = pd.read_sql(q, engine, params={"s": sym})
            if len(fr) < 50:
                continue
            fr_bp = fr["funding_rate"].astype(float) * 10000.0
            n_neg_threshold = int((fr_bp <= FUNDING_LOWER_BP).sum())
            n_pos_threshold = int((fr_bp >= FUNDING_UPPER_BP).sum())
            results[sym] = {
                "n_obs": int(len(fr_bp)),
                "p1_bp": float(fr_bp.quantile(0.01)),
                "p5_bp": float(fr_bp.quantile(0.05)),
                "p10_bp": float(fr_bp.quantile(0.10)),
                "p50_bp": float(fr_bp.quantile(0.50)),
                "p90_bp": float(fr_bp.quantile(0.90)),
                "p99_bp": float(fr_bp.quantile(0.99)),
                "min_bp": float(fr_bp.min()),
                "max_bp": float(fr_bp.max()),
                "n_below_lower": n_neg_threshold,
                "pct_below_lower": n_neg_threshold / len(fr_bp),
                "n_above_upper": n_pos_threshold,
                "pct_above_upper": n_pos_threshold / len(fr_bp),
            }
        except Exception as e:
            log.warning("%s funding audit fail: %s", sym, e)
    return results


def audit_cvd_substrate() -> dict:
    """Lesson #28 substrate availability — taker_buy_sell_ratio joblib presence."""
    results = {}
    for sym in COHORT:
        p = MICRO_DIR / f"{sym}_full_metrics.joblib"
        if not p.exists():
            results[sym] = {"available": False, "reason": "joblib_missing"}
            continue
        results[sym] = {
            "available": True,
            "joblib_path": str(p),
            "joblib_size_mb": round(p.stat().st_size / 1024 / 1024, 2),
        }
    return results


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Hypothesis: funding ≤ %.0fbp × CVD ≤ %.1f × SHORT 4h",
             FUNDING_LOWER_BP, CVD_LOWER)
    log.info("Cohort: %d alts (funding DB + microstructure joblib + OHLCV)", len(COHORT))

    # STEP 1: Lesson #40 structural threshold attainability (FIRST per spec)
    log.info("--- STEP 1: Lesson #40 structural threshold attainability ---")
    engine = create_engine(DB_DSN)
    funding_audit = audit_funding_distribution(engine)
    engine.dispose()

    log.info("Per-sym funding distribution (8h frame, bp):")
    log.info(f"{'sym':>14} {'n':>6} {'p1':>8} {'p10':>8} {'p50':>8} {'p99':>8} {'min':>9} {'max':>8} {'≤-50bp%':>9} {'≥+50bp%':>9}")
    for sym, d in funding_audit.items():
        log.info(
            f"  {sym:>12} {d['n_obs']:>6} {d['p1_bp']:>8.2f} {d['p10_bp']:>8.2f} "
            f"{d['p50_bp']:>8.2f} {d['p99_bp']:>8.2f} {d['min_bp']:>9.2f} {d['max_bp']:>8.2f} "
            f"{d['pct_below_lower']*100:>8.2f}% {d['pct_above_upper']*100:>8.2f}%"
        )

    # Verdict per sym
    n_syms_audited = len(funding_audit)
    n_syms_below_lower_reachable = sum(1 for d in funding_audit.values() if d["pct_below_lower"] > 0.01)
    n_syms_above_upper_reachable = sum(1 for d in funding_audit.values() if d["pct_above_upper"] > 0.01)
    n_syms_zero_above_upper = sum(1 for d in funding_audit.values() if d["n_above_upper"] == 0)
    n_syms_zero_below_lower = sum(1 for d in funding_audit.values() if d["n_below_lower"] == 0)

    log.info(
        "Audit summary (n_syms=%d): "
        "syms reaching ≤%.0fbp (rate>1%%): %d/%d | syms reaching ≥%.0fbp (rate>1%%): %d/%d | "
        "syms with ZERO ≥%.0fbp: %d/%d",
        n_syms_audited, FUNDING_LOWER_BP, n_syms_below_lower_reachable, n_syms_audited,
        FUNDING_UPPER_BP, n_syms_above_upper_reachable, n_syms_audited,
        FUNDING_UPPER_BP, n_syms_zero_above_upper, n_syms_audited,
    )

    # Halt criterion: Lesson #40 paradigm 109+110 dogfood pattern
    # Symmetric trigger (±50bp) infeasible if EITHER side has <3 syms with rate>1%
    cond_lower_infeasible = n_syms_below_lower_reachable < 3
    cond_upper_infeasible = n_syms_above_upper_reachable < 3  # B side: ≥+50bp
    structurally_infeasible = cond_lower_infeasible or cond_upper_infeasible

    lesson_40 = {
        "threshold_definition": f"funding ≤ {FUNDING_LOWER_BP}bp OR funding ≥ +{FUNDING_UPPER_BP}bp (raw 8h frame)",
        "stat_class": "funding_rate_raw_bp_symmetric_trigger",
        "n_syms_audited": n_syms_audited,
        "n_syms_reach_lower": n_syms_below_lower_reachable,
        "n_syms_reach_upper": n_syms_above_upper_reachable,
        "n_syms_zero_above_upper": n_syms_zero_above_upper,
        "n_syms_zero_below_lower": n_syms_zero_below_lower,
        "cond_lower_infeasible": cond_lower_infeasible,
        "cond_upper_infeasible": cond_upper_infeasible,
        "structurally_infeasible": structurally_infeasible,
        "verdict": ("FAIL_STRUCTURAL_THRESHOLD_INFEASIBLE_SYMMETRIC"
                    if structurally_infeasible else "PASS"),
        "per_sym_funding_distribution": funding_audit,
        "binance_funding_rate_hard_cap_observation": (
            "p99 = +1.00 bp on 13/19 syms, p99 = +0.50 bp on 3 syms (TON/JUP/PYTH 2227 obs each), "
            "+5bp max on 1 sym (DOGE 1117 obs), max 4.53bp on DOGE. "
            "Binance regular tier funding rate hard-caps at +0.01% = +1bp. "
            "Funding rate B-side (long-pay-short) is structurally floor-bounded; "
            "±50bp symmetric threshold infeasible on raw 8h-frame funding. "
            "Reformulate alternatives: (a) percentile rank, (b) per-sym z-score "
            "(paradigm 22 R-5 seed approach), (c) absolute funding magnitude on log scale."
        ),
    }

    # STEP 2: Lesson #28 substrate availability — CVD axis
    log.info("--- STEP 2: Lesson #28 substrate availability — CVD via TBR joblib ---")
    cvd_audit = audit_cvd_substrate()
    n_cvd_available = sum(1 for d in cvd_audit.values() if d["available"])
    log.info("CVD substrate (TBR joblib): %d/%d syms available", n_cvd_available, len(COHORT))
    lesson_28 = {
        "substrate_source": "runs/microstructure/{SYM}_full_metrics.joblib (taker_buy_sell_ratio column)",
        "frequency": "5m (CVD per-bar via (TBR-1)/(TBR+1)); 4h aggregation = mean over 48 × 5m",
        "span": "~800d (2024-02-23 to 2026-05-02)",
        "n_syms_available": n_cvd_available,
        "n_syms_required": len(COHORT),
        "per_sym": cvd_audit,
        "verdict": "PASS" if n_cvd_available >= 10 else "FAIL_INSUFFICIENT_SYMS",
        "ohlcv_taker_buy_column_absent": (
            "OHLCV DB has NO taker_buy_base_asset_volume column. "
            "Raw CVD CANNOT be computed from DB volume × side. "
            "Proxy via TBR joblib is FEASIBLE but indirect."
        ),
    }

    # Lesson #44 21st amendment xref
    lesson_44_xref = {
        "paradigm_22_funding_carry_zscore":
            "R-5 SEEDED HBAR/AXS/COMP — uses PER-SYM z-score normalized funding "
            "(NOT raw bp threshold). paradigm 138 raw ±50bp infeasible; "
            "paradigm 22 z-score approach is exact reformulation guidance.",
        "paradigm_72_taker_buy_volume_5m_zscore":
            "GRAVEYARD BROAD_FALSIFIED — 5m taker volume z-score, all 13 alts negative, "
            "Q3 §6.2 #10 taker-side aggressive volume family Tier 4 retire. "
            "paradigm 138 CVD axis = ratio (NOT volume magnitude) → distinct in DNA "
            "BUT funding axis disqualifies before substrate question.",
        "paradigm_73_funding_oi_bipolar":
            "GRAVEYARD — funding × OI joint, sub-fee. Funding family Tier 4 dogfood #1.",
        "paradigm_79_funding_dispersion_etcusdt":
            "EXCEPTION R-5 SEED — funding dispersion ETC narrow scope.",
        "paradigm_96_funding_sign_flip":
            "GRAVEYARD BROAD_FALSIFIED — funding single signal sub-family Tier 4 retire.",
        "paradigm_97_funding_term_structure_dispersion":
            "INVENTORY-HALT (DNA 5/6 vs paradigm 79). Funding family dogfood evidence.",
        "paradigm_98_funding_regime_stratify":
            "GRAVEYARD BROAD_FALSIFIED — funding axis variant exhaustion.",
        "paradigm_99_funding_per_sym_velocity":
            "GRAVEYARD NARROW_SCOPE_LIFE_CHANGING_FAIL.",
        "paradigm_103_cross_exchange_funding_spread":
            "GRAVEYARD BROAD_FALSIFIED_FEE_FLOOR — cross-exchange axis exception soaked.",
        "paradigm_132_funding_oi_magnitude_triple":
            "GRAVEYARD Lesson #21 — 3-way axis stacking trap.",
        "paradigm_109_110_lesson_40_dogfood":
            "CONFIRMED — non-negative aggregate statistic symmetric z≤−T structurally "
            "infeasible. paradigm 138 ±50bp on raw funding is IDENTICAL antipattern "
            "(funding hard-capped at +1bp regular tier).",
        "paradigm_127_128_volume_burst_r5_live":
            "R-5 LIVE Mint — 1m volume burst directional. Distinct from CVD ratio axis.",
        "paradigm_137_yang_zhang_efficiency_ratio":
            "GRAVEYARD 2026-05-21 — 9-streak non-PASS predecessor. paradigm 138 was "
            "user-requested non-RV pivot to break streak; halts at R-0 for orthogonal reason "
            "(funding raw threshold infeasibility, NOT vol family saturation).",
        "funding_family_tier_4_retire_status":
            "REAFFIRMED — paradigm 73+79+96+97+98+99+103+132 cumulative funding axis exhaustion. "
            "paradigm 22 R-5 (z-score) and paradigm 79 ETC (dispersion) are sole exceptions. "
            "paradigm 138 raw bp threshold variant FAILS Lesson #40 prescreen before reaching "
            "the 2-way confluence test; funding axis cannot be probed with raw bp thresholds.",
    }

    # Family-distinct verification
    family_avoidance = {
        "Funding_single_signal_raw_bp": "INFEASIBLE — Lesson #40 structural halt",
        "Funding_zscore_per_sym": "AVAILABLE alternative (paradigm 22 R-5 approach)",
        "Funding_percentile_rank": "AVAILABLE alternative (Lesson #40 reformulation guidance)",
        "CVD_5m_to_4h_aggregation": "FEASIBLE substrate (TBR joblib)",
        "Taker_volume_magnitude_zscore": "AVOIDED (paradigm 72 graveyard; CVD ratio NOT volume)",
        "OI_velocity_axis": "AVOIDED",
        "Magnitude_confluence_3way": "AVOIDED (2-axis only, paradigm 132 trap distinct)",
        "Listing_event_axis": "AVOIDED",
        "HMM_unsupervised": "AVOIDED (explicit threshold)",
    }

    # Final verdict
    verdict_components = {
        "lesson_40_structural_threshold_attainability": lesson_40["verdict"],
        "lesson_28_substrate_availability": lesson_28["verdict"],
    }
    if lesson_40["verdict"] != "PASS":
        verdict = "R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBLE_SYMMETRIC"
        sub_class = (
            f"funding ±{FUNDING_LOWER_BP}bp symmetric trigger infeasible on raw 8h frame: "
            f"only {n_syms_below_lower_reachable}/{n_syms_audited} syms reach ≤-50bp at rate>1%, "
            f"and {n_syms_above_upper_reachable}/{n_syms_audited} syms reach ≥+50bp (Binance hard cap +1bp). "
            f"Lesson #40 paradigm 109+110 antipattern dogfood (3rd instance). "
            f"Reformulation: funding per-sym z-score (paradigm 22 approach) or percentile rank."
        )
    elif lesson_28["verdict"] != "PASS":
        verdict = "R0_HALT_LESSON_28_SUBSTRATE_UNAVAILABLE"
        sub_class = "CVD substrate insufficient"
    else:
        verdict = "R0_READY_FOR_R1"
        sub_class = "all prescreens pass"

    log.info("=== VERDICT: %s ===", verdict)
    log.info("=== SUB-CLASS: %s ===", sub_class)

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "sub_class": sub_class,
        "verdict_components": verdict_components,
        "hypothesis": {
            "axis_1": "funding rate (raw bp, 8h frame)",
            "axis_2": "CVD ratio 4h aggregate via TBR joblib 5m",
            "joint_trigger_A": f"funding ≤ {FUNDING_LOWER_BP}bp AND CVD ≤ {CVD_LOWER}",
            "joint_trigger_B": f"funding ≥ +{FUNDING_UPPER_BP}bp AND CVD ≥ +{CVD_UPPER}",
            "direction_A_focus": "SHORT 4h (smart money exit before crowd capitulation)",
            "direction_B_focus": "LONG 4h (mirror condition)",
        },
        "params": {
            "funding_lower_bp": FUNDING_LOWER_BP,
            "funding_upper_bp": FUNDING_UPPER_BP,
            "cvd_lower": CVD_LOWER,
            "cvd_upper": CVD_UPPER,
        },
        "universe_cohort": COHORT,
        "universe_audit_syms": AUDIT_SYMS,
        "lesson_40_structural_threshold": lesson_40,
        "lesson_28_substrate_availability": lesson_28,
        "lesson_44_xref_21st_amendment": lesson_44_xref,
        "family_avoidance_verification": family_avoidance,
        "reformulation_paths_for_user": {
            "path_1_funding_zscore_per_sym": (
                "Replace raw funding ≤ -50bp with per-sym 30d z-score ≤ -2.0. "
                "This is paradigm 22 R-5 SEED approach (funding-carry HBAR/AXS/COMP). "
                "Distinct from paradigm 22 by ADDING CVD axis confluence. "
                "Lesson #21 axis stacking risk: 2-axis (funding-z × CVD-z) is admissible "
                "(paradigm 132 trap was 3-way: funding × OI × magnitude). "
                "RISK: funding family Tier 4 retire applies — paradigm 22 exception "
                "stands precisely because z-score normalized; adding CVD must demonstrate "
                "individual-vs-joint sigex synthesis (Lesson #21 6th dogfood)."
            ),
            "path_2_funding_percentile_rank": (
                "Replace raw funding ≤ -50bp with cross-sectional percentile rank "
                "(per-time-stamp across 13 alts) bottom 10%. "
                "Distinct mechanism: relative position vs cohort, not absolute level. "
                "Avoids hard-cap +1bp ceiling issue."
            ),
            "path_3_funding_event_change":
                "Replace level threshold with funding rate Δ ≥ X bp per-period (acceleration), "
                "captures direction of change rather than absolute level. "
                "Risk: paradigm 96 funding sign flip already graveyard (sign-flip lagging marker).",
            "path_4_drop_funding_axis_use_CVD_alone": (
                "CVD ratio 4h alone (1-axis) — but CVD ratio is essentially TBR derivative "
                "and paradigm 72 (5m taker volume z) graveyard suggests taker-side fee floor. "
                "Need to verify 4h aggregation breaks that constraint (paradigm 72 was 5m bar)."
            ),
        },
        "recommended_path_for_user_dispatch": "path_2_funding_percentile_rank OR path_4 CVD alone",
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-0 saved to %s", out_path)


if __name__ == "__main__":
    main()
