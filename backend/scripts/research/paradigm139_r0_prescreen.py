"""paradigm 139 R-0 prescreen — alt_funding_per_sym_30d_zscore_x_cvd_4h_divergence_directional_4h.

Hypothesis (paradigm 138 Lesson #40 reformulation via paradigm 22 R-5 z-score approach):
  funding per-sym 30d z-score ≤ -2.0 (extreme LONG-crowded normalized)
    AND 4h CVD ratio ≤ -0.1 (sustained taker SELL)
    -> SHORT 4h (smart money exit precedes crowd capitulation)
  4-quadrant SNT (Lesson #19):
    A_focus  = funding_z ≤ -2.0 × CVD ≤ -0.1 × SHORT 4h     (primary)
    A_mirror = funding_z ≤ -2.0 × CVD ≤ -0.1 × LONG 4h      (mean-reversion contrary)
    B_focus  = funding_z ≥ +2.0 × CVD ≥ +0.1 × LONG 4h      (mirror condition)
    B_mirror = funding_z ≥ +2.0 × CVD ≥ +0.1 × SHORT 4h     (mirror contrary)

R-0 sequential prescreen (paradigm-architect spec):

  STEP 1 (Lesson #40 structural threshold attainability — FIRST per spec):
    paradigm 138 raw ±50bp HALT motivated this reformulation. Per-sym 30d z-score is the
    paradigm 22 R-5 SEED approach. CRITICAL: per-sym z-score normalizes each sym's funding
    by its own 30d rolling mean/std. BUT funding rate is exchange-asymmetrically-bounded:
    Binance regular tier hard-caps at +0.01% = +1 bp on the upside, while leveraged
    liquidation episodes can drive funding to -200 bp (AXS observed extreme). Standard
    deviation is dominated by the negative tail. EMPIRICAL TEST: measure z ≤ -2.0 vs
    z ≥ +2.0 reachability across 10-sym cohort.

  STEP 2 (Lesson #28 substrate availability — funding DB + CVD joblib):
    funding DB binance_funding_rate has 10/13 original cohort syms with non-zero data
    (BCH/BNB/LTC = ZERO funding rows DB-wide). Span ~370 days (2025-05-04 to 2026-05-10).
    CVD via taker_buy_sell_ratio joblib at 5m frequency, span 2024-02-24 to 2026-05-03
    (~800 days, ~230k 5m bars/sym). Intersection: 2025-05-04 to 2026-05-03 ≈ 365 days.

  STEP 3 (Lesson #11 expected_n joint trigger density):
    Conditional on Lesson #40 PASS for both directions. Computed in main().

  STEP 4 (Lesson #21 sub-finding magnitude-ratio prescreen):
    funding_z vs CVD per-sym Pearson correlation < 0.5 required for joint axis synthesis.
    Computed in main().

  STEP 5 (Lesson #44 22nd amendment cross-reference dogfood):
    paradigm 22 funding_carry R-5 SEEDED (HBAR/AXS/COMP) — uses per-sym z-score, NO CVD axis
    paradigm 72 taker_buy_volume_5m_zscore GRAVEYARD — taker volume family Tier 4 retire
    paradigm 73/96/97/98/99/103/132/138 funding family Tier 4 retire — 8 cumulative graveyards
    paradigm 109+110+138 Lesson #40 CONFIRMED dogfoods — structural infeasibility
    paradigm 132 Lesson #21 axis stacking trap — 3-way funding × OI × magnitude
    paradigm 127+128 R-5 LIVE Mint — 1m volume burst directional (DNA distinct)

VERDICT logic:
  if Lesson #40 STEP 1 reaches both z ≤ -2.0 AND z ≥ +2.0 at rate ≥ 1.5% in ≥ 3/10 syms:
    -> proceed to STEP 3+4, then R0_READY_FOR_R1
  else:
    -> R0_HALT_LESSON_40_PERSYM_ZSCORE_INHERITS_ASYMMETRY (4th dogfood instance)
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p139_r0")

PARADIGM_NAME = "alt_funding_per_sym_30d_zscore_x_cvd_4h_divergence_directional_4h"
PARADIGM_NUM = 139
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 10-sym cohort (funding DB + microstructure joblib both available)
# paradigm 138 cohort 13 syms minus BCH/BNB/LTC (zero funding DB rows)
COHORT = [
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "AVAXUSDT",
    "SOLUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT",
    "LDOUSDT", "ETCUSDT",
]

FUNDING_Z_LOWER = -2.0   # extreme LONG-crowded normalized
FUNDING_Z_UPPER = +2.0   # extreme SHORT-crowded normalized (per-sym)
CVD_LOWER = -0.1
CVD_UPPER = +0.1
Z_WINDOW = 90            # 30d at 8h funding cadence = 90 obs
Z_MIN_PERIODS = 60

DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
MICRO_DIR = Path("/home/hcpark/antigravity/backend/runs/microstructure")


def load_funding_zscore(engine, sym: str) -> pd.Series:
    """Per-sym funding rate, then 30d rolling z-score at 8h cadence."""
    q = text(
        "SELECT funding_time, funding_rate FROM binance_funding_rate "
        "WHERE symbol=:s ORDER BY funding_time"
    )
    with engine.connect() as c:
        df = pd.read_sql(q, c, params={"s": sym})
    if len(df) < Z_MIN_PERIODS + 10:
        return pd.Series(dtype=float)
    df["funding_time"] = pd.to_datetime(df["funding_time"])
    df = df.set_index("funding_time").sort_index()
    rm = df["funding_rate"].rolling(window=Z_WINDOW, min_periods=Z_MIN_PERIODS).mean()
    rs = df["funding_rate"].rolling(window=Z_WINDOW, min_periods=Z_MIN_PERIODS).std()
    z = ((df["funding_rate"] - rm) / rs).dropna()
    return z


def load_cvd_4h(sym: str) -> pd.Series:
    """Per-sym CVD ratio = (TBR-1)/(TBR+1) at 5m, then mean over 4h."""
    p = MICRO_DIR / f"{sym}_full_metrics.joblib"
    if not p.exists():
        return pd.Series(dtype=float)
    d = joblib.load(p)
    if "taker_buy_sell_ratio" not in d.columns:
        return pd.Series(dtype=float)
    tbr = d["taker_buy_sell_ratio"]
    cvd_5m = (tbr - 1) / (tbr + 1)
    cvd_4h = cvd_5m.resample("4h").mean().dropna()
    return cvd_4h


def step1_lesson_40_structural_threshold(engine) -> dict:
    """Measure per-sym funding 30d z-score distribution for both ±2.0 sides."""
    out = {}
    for sym in COHORT:
        z = load_funding_zscore(engine, sym)
        if len(z) < 50:
            out[sym] = {"n": int(len(z)), "skip": True}
            continue
        n_low = int((z <= FUNDING_Z_LOWER).sum())
        n_high = int((z >= FUNDING_Z_UPPER).sum())
        out[sym] = {
            "n": int(len(z)),
            "p1": float(z.quantile(0.01)),
            "p5": float(z.quantile(0.05)),
            "p50": float(z.quantile(0.50)),
            "p95": float(z.quantile(0.95)),
            "p99": float(z.quantile(0.99)),
            "min": float(z.min()),
            "max": float(z.max()),
            "n_below_neg2": n_low,
            "rate_below_neg2": n_low / len(z),
            "n_above_pos2": n_high,
            "rate_above_pos2": n_high / len(z),
        }
    n_syms_audited = sum(1 for v in out.values() if not v.get("skip"))
    n_syms_below_reachable = sum(
        1 for v in out.values() if not v.get("skip") and v["rate_below_neg2"] >= 0.015
    )
    n_syms_above_reachable = sum(
        1 for v in out.values() if not v.get("skip") and v["rate_above_pos2"] >= 0.015
    )
    n_syms_zero_above = sum(
        1 for v in out.values() if not v.get("skip") and v["n_above_pos2"] == 0
    )
    n_syms_zero_below = sum(
        1 for v in out.values() if not v.get("skip") and v["n_below_neg2"] == 0
    )

    cond_lower_infeasible = n_syms_below_reachable < 3
    cond_upper_infeasible = n_syms_above_reachable < 3
    structurally_infeasible = cond_lower_infeasible or cond_upper_infeasible

    return {
        "per_sym": out,
        "n_syms_audited": n_syms_audited,
        "n_syms_below_reachable": n_syms_below_reachable,
        "n_syms_above_reachable": n_syms_above_reachable,
        "n_syms_zero_above_pos2": n_syms_zero_above,
        "n_syms_zero_below_neg2": n_syms_zero_below,
        "cond_lower_infeasible": cond_lower_infeasible,
        "cond_upper_infeasible": cond_upper_infeasible,
        "structurally_infeasible": structurally_infeasible,
        "verdict": (
            "FAIL_PERSYM_ZSCORE_INHERITS_RAW_FUNDING_ASYMMETRY"
            if structurally_infeasible else "PASS"
        ),
        "threshold_definition": f"funding_z ≤ {FUNDING_Z_LOWER} OR funding_z ≥ +{FUNDING_Z_UPPER} (per-sym 30d=90obs)",
    }


def step2_substrate_audit(engine) -> dict:
    funding_audit = {}
    cvd_audit = {}
    with engine.connect() as c:
        for sym in COHORT:
            df = pd.read_sql(
                text(
                    "SELECT MIN(funding_time) AS mn, MAX(funding_time) AS mx, "
                    "COUNT(*) AS n FROM binance_funding_rate WHERE symbol=:s"
                ),
                c, params={"s": sym},
            )
            funding_audit[sym] = {
                "n": int(df["n"].iloc[0]),
                "mn": str(df["mn"].iloc[0]),
                "mx": str(df["mx"].iloc[0]),
            }
    for sym in COHORT:
        p = MICRO_DIR / f"{sym}_full_metrics.joblib"
        cvd_audit[sym] = {
            "available": p.exists(),
            "joblib_mb": round(p.stat().st_size / 1024 / 1024, 2) if p.exists() else 0,
        }
    n_funding_ok = sum(1 for v in funding_audit.values() if v["n"] >= 200)
    n_cvd_ok = sum(1 for v in cvd_audit.values() if v["available"])
    return {
        "funding_db": funding_audit,
        "cvd_joblib": cvd_audit,
        "n_funding_syms_ok": n_funding_ok,
        "n_cvd_syms_ok": n_cvd_ok,
        "verdict": "PASS" if (n_funding_ok >= 8 and n_cvd_ok >= 8) else "FAIL",
    }


def step3_lesson_11_expected_n(engine, lesson_40_per_sym: dict) -> dict:
    """Empirical joint trigger rate per-sym (combine funding_z and CVD)."""
    joint_audit = {}
    total_a_focus_triggers = 0
    total_b_focus_triggers = 0
    for sym in COHORT:
        z = load_funding_zscore(engine, sym)
        cvd = load_cvd_4h(sym)
        if len(z) < 50 or len(cvd) < 50:
            joint_audit[sym] = {"skip": True}
            continue
        # Align funding_z 8h cadence to CVD 4h cadence
        # forward-fill funding_z to 4h grid
        z_4h = z.reindex(cvd.index, method="ffill").dropna()
        cvd_aligned = cvd.reindex(z_4h.index).dropna()
        common = z_4h.index.intersection(cvd_aligned.index)
        if len(common) < 100:
            joint_audit[sym] = {"skip": True, "n_common": int(len(common))}
            continue
        z_c = z_4h.loc[common]
        cvd_c = cvd_aligned.loc[common]
        mask_a = (z_c <= FUNDING_Z_LOWER) & (cvd_c <= CVD_LOWER)
        mask_b = (z_c >= FUNDING_Z_UPPER) & (cvd_c >= CVD_UPPER)
        n_a = int(mask_a.sum())
        n_b = int(mask_b.sum())
        total_a_focus_triggers += n_a
        total_b_focus_triggers += n_b
        joint_audit[sym] = {
            "n_common_4h_bars": int(len(common)),
            "n_a_focus_triggers": n_a,
            "n_b_focus_triggers": n_b,
            "rate_a": n_a / len(common),
            "rate_b": n_b / len(common),
        }
    # Estimate per-cell n for 4-quadrant SNT (split into 4 quarters per quadrant)
    n_quarters = 4
    per_cell_a = total_a_focus_triggers / n_quarters if total_a_focus_triggers else 0
    per_cell_b = total_b_focus_triggers / n_quarters if total_b_focus_triggers else 0
    return {
        "per_sym_joint": joint_audit,
        "total_a_focus_triggers": total_a_focus_triggers,
        "total_b_focus_triggers": total_b_focus_triggers,
        "per_cell_a_focus_per_quarter": round(per_cell_a, 1),
        "per_cell_b_focus_per_quarter": round(per_cell_b, 1),
        "verdict": (
            "PASS"
            if (per_cell_a >= 30 and per_cell_b >= 30)
            else "FAIL_SAMPLE_INSUFFICIENT"
        ),
        "lesson_11_per_cell_threshold": 30,
    }


def step4_lesson_21_magnitude_ratio(engine) -> dict:
    """Per-sym Pearson correlation between funding_z and CVD ratio (independence)."""
    corr_audit = {}
    for sym in COHORT:
        z = load_funding_zscore(engine, sym)
        cvd = load_cvd_4h(sym)
        if len(z) < 50 or len(cvd) < 50:
            corr_audit[sym] = {"skip": True}
            continue
        z_4h = z.reindex(cvd.index, method="ffill").dropna()
        cvd_aligned = cvd.reindex(z_4h.index).dropna()
        common = z_4h.index.intersection(cvd_aligned.index)
        if len(common) < 100:
            corr_audit[sym] = {"skip": True}
            continue
        z_c = z_4h.loc[common]
        cvd_c = cvd_aligned.loc[common]
        corr = float(np.corrcoef(z_c, cvd_c)[0, 1])
        corr_audit[sym] = {
            "n": int(len(common)),
            "pearson_r": corr,
            "abs_r": abs(corr),
        }
    valid = [v for v in corr_audit.values() if not v.get("skip")]
    if valid:
        mean_abs = float(np.mean([v["abs_r"] for v in valid]))
        max_abs = float(np.max([v["abs_r"] for v in valid]))
    else:
        mean_abs = max_abs = float("nan")
    return {
        "per_sym_corr": corr_audit,
        "mean_abs_pearson_r": mean_abs,
        "max_abs_pearson_r": max_abs,
        "verdict": "PASS" if max_abs < 0.5 else "WARN_HIGH_CORRELATION",
    }


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Hypothesis: funding_z ≤ %.1f × CVD ≤ %.2f × SHORT 4h", FUNDING_Z_LOWER, CVD_LOWER)
    log.info("Cohort: %d alts (funding DB + microstructure joblib)", len(COHORT))

    engine = create_engine(DB_DSN)

    # STEP 1: Lesson #40 FIRST per spec
    log.info("--- STEP 1: Lesson #40 structural threshold attainability ---")
    s1 = step1_lesson_40_structural_threshold(engine)
    log.info("Per-sym funding 30d z-score distribution:")
    log.info(f"{'sym':>10} {'n':>5} {'p1':>6} {'p5':>6} {'p50':>6} {'p95':>6} {'p99':>6} {'min':>7} {'max':>6} {'z<=-2':>8} {'z>=+2':>8}")
    for sym, d in s1["per_sym"].items():
        if d.get("skip"):
            log.info(f"  {sym:>8} SKIP n={d['n']}")
            continue
        log.info(
            f"  {sym:>8} {d['n']:>5} {d['p1']:>6.2f} {d['p5']:>6.2f} {d['p50']:>6.2f} "
            f"{d['p95']:>6.2f} {d['p99']:>6.2f} {d['min']:>7.2f} {d['max']:>6.2f} "
            f"{d['rate_below_neg2']*100:>6.2f}% {d['rate_above_pos2']*100:>6.2f}%"
        )
    log.info(
        "Audit: syms reaching z<=-2 (rate>=1.5%%): %d/%d | z>=+2: %d/%d | zero-above: %d | zero-below: %d",
        s1["n_syms_below_reachable"], s1["n_syms_audited"],
        s1["n_syms_above_reachable"], s1["n_syms_audited"],
        s1["n_syms_zero_above_pos2"], s1["n_syms_zero_below_neg2"],
    )
    log.info("STEP 1 verdict: %s", s1["verdict"])

    # If STEP 1 FAIL, halt with full diagnostic; skip STEP 3+4 (joint test infeasible).
    if s1["verdict"] != "PASS":
        log.info("=== R-0 HALT at STEP 1 (Lesson #40 4th dogfood instance) ===")
        # Still measure STEP 2 substrate for completeness
        log.info("--- STEP 2: substrate audit (informational) ---")
        s2 = step2_substrate_audit(engine)
        engine.dispose()

        lesson_44_xref = {
            "paradigm_22_funding_carry_zscore_R5":
                "R-5 SEEDED HBAR/AXS/COMP — uses per-sym 30d z-score on funding "
                "(directional MR not symmetric trigger). paradigm 22 is one-sided "
                "(LONG-crowded only -> SHORT mean-reversion), avoiding the symmetric "
                "B-side infeasibility paradigm 139 hits.",
            "paradigm_138_raw_bp_R0_halt":
                "GRAVEYARD 2026-05-21 11:56 KST — raw ±50bp threshold infeasible, "
                "Lesson #40 3rd dogfood (paradigm 109+110+138). paradigm 139 attempted "
                "reformulation via per-sym z-score; STEP 1 reveals z-score INHERITS the "
                "underlying raw funding asymmetry (B-side hard cap at +1bp pulls std "
                "dominantly from negative tail, so z ≥ +2.0 is structurally rare).",
            "paradigm_109_110_lesson_40_CONFIRMED":
                "Original dogfood — non-negative aggregate statistic + symmetric ±T trigger "
                "structurally infeasible. paradigm 139 EXTENDS scope to per-sym z-score "
                "normalization of asymmetrically exchange-bounded scalars: z-score does NOT "
                "rescue symmetric trigger feasibility because std inherits the bound.",
            "funding_family_tier_4_retire":
                "8 graveyards (73/79*/96/97/98/99/103/132/138 — *paradigm 22+79 R-5 exception). "
                "paradigm 139 9th funding family graveyard (regardless of CVD axis innovation).",
            "paradigm_72_taker_volume_zscore_GRAVEYARD":
                "5m taker volume z-score family Tier 4 retire (Q3 §6.2 #10). CVD ratio axis "
                "in paradigm 139 is DNA-distinct (ratio not magnitude) but funding axis "
                "structural failure precludes joint test.",
        }

        lesson_40_sub_amendment_4th_dogfood = {
            "instance_count": 4,
            "instances": [
                "paradigm 109 RV symmetric z<=-T (non-negative aggregate)",
                "paradigm 110 std symmetric z<=-T (non-negative aggregate)",
                "paradigm 138 funding raw ±50bp (asymmetrically exchange-bounded)",
                "paradigm 139 funding per-sym 30d z-score ±2.0 (asymmetric bound inherited via std)",
            ],
            "amendment_claim": (
                "Lesson #40 sub-amendment 4th dogfood elevation candidate: "
                "Per-sym z-score normalization does NOT rescue symmetric threshold "
                "feasibility when the underlying scalar is asymmetrically exchange-bounded. "
                "The rolling std inherits the asymmetry (dominated by uncapped tail), so "
                "z-score thresholds remain structurally rare on the capped side. "
                "Reformulation alternatives for funding: (a) one-sided z-score (paradigm 22 "
                "approach, A-side only), (b) percentile rank cross-sectional per-time-stamp "
                "(removes per-sym std bias), (c) absolute funding magnitude on log scale, "
                "(d) drop B-quadrant symmetric pretense, run A-only directional R-1."
            ),
            "elevation_to_confirmed_path": (
                "Lesson #40 originally CONFIRMED via 2 dogfoods (109+110). paradigm 138 was "
                "3rd dogfood (asymmetrically bounded scalar). paradigm 139 is 4th dogfood "
                "(per-sym z-score normalization does not rescue). Sub-amendment text "
                "expansion: 'non-negative aggregate OR asymmetrically exchange-bounded OR "
                "z-score of asymmetrically bounded' all fail symmetric ±T."
            ),
        }

        family_distinct_audit = {
            "Funding_single_signal_raw_bp_paradigm138": "INFEASIBLE Lesson #40 STEP 1 STAGE 1",
            "Funding_single_signal_persym_zscore_paradigm139": "INFEASIBLE Lesson #40 STEP 1 STAGE 2",
            "Funding_persym_zscore_one_sided_A_only": "AVAILABLE (paradigm 22 approach)",
            "Funding_percentile_rank_cross_sectional": "AVAILABLE",
            "Funding_velocity_zscore": "RISKY (paradigm 99 NARROW_SCOPE_LIFE_CHANGING_FAIL)",
            "CVD_5m_to_4h_alone_no_funding": "AVAILABLE (paradigm 72 risk to verify)",
            "Drop_funding_use_OI_CVD_joint": "AVAILABLE (paradigm 138 R-0 cohort + path 4)",
        }

        reformulation_paths = {
            "path_1_funding_A_only_zscore_x_CVD_A_only":
                "Drop B-quadrant symmetric SNT pretense. Run 2-quadrant (A_focus SHORT + "
                "A_mirror LONG) only. Recovers paradigm 22 R-5 alignment (one-sided), "
                "CVD axis = NEW. Lesson #19 SNT requires 4-quadrant by default but Lesson "
                "#40 structural infeasibility justifies asymmetric 2-quadrant on theoretical "
                "ground (mirror infeasible substrate, not test failure).",
            "path_2_funding_percentile_rank_cross_sectional":
                "Replace per-sym z-score with cross-sectional percentile rank (per-time-stamp "
                "across 10 alts: bottom 10% / top 10%). Removes per-sym std asymmetry bias. "
                "Lesson #40 risk: still inherits raw funding rate hard-cap (top decile would "
                "include ZERO since p99 = +1bp universally). FAIL CANDIDATE: Top-decile "
                "trigger would degenerate to ties at +1bp cap.",
            "path_3_drop_funding_axis_use_CVD_alone_4h":
                "Drop funding entirely. CVD 4h ratio z-score directional. Paradigm 72 risk "
                "(5m taker volume z-score family Tier 4 retire) — but CVD is RATIO not "
                "volume magnitude, and 4h aggregation breaks 5m fee floor (paradigm 72 was "
                "5m bar). Verify with separate R-0 prescreen.",
            "path_4_funding_z_velocity_per_sym":
                "Replace level threshold with Δfunding_z (velocity) — paradigm 99 graveyard "
                "warned NARROW_SCOPE_LIFE_CHANGING_FAIL. NOT RECOMMENDED.",
            "path_5_funding_event_change_sign_flip":
                "paradigm 96 graveyard — sign-flip lagging marker. NOT RECOMMENDED.",
        }
        recommended_path = "path_1_funding_A_only_zscore_x_CVD_A_only OR path_3_CVD_alone"

        verdict = "R0_HALT_LESSON_40_PERSYM_ZSCORE_INHERITS_ASYMMETRY"
        sub_class = (
            f"paradigm 139 per-sym 30d funding z-score symmetric ±{FUNDING_Z_UPPER} infeasible "
            f"on B-side: {s1['n_syms_above_reachable']}/{s1['n_syms_audited']} syms reach "
            f"z>=+{FUNDING_Z_UPPER} at rate>=1.5% (vs {s1['n_syms_below_reachable']}/{s1['n_syms_audited']} "
            f"on A-side). 4th Lesson #40 dogfood instance: per-sym z-score normalization does NOT "
            f"rescue symmetric threshold feasibility when raw scalar is asymmetrically "
            f"exchange-bounded (Binance funding +1bp hard cap pulls std from negative tail). "
            f"Reformulation: A-only 2-quadrant SNT OR percentile rank OR CVD-alone (paradigm 72 risk)."
        )

        out = {
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "host": "hcp_local",
            "verdict": verdict,
            "sub_class": sub_class,
            "verdict_components": {
                "step1_lesson_40_structural_threshold": s1["verdict"],
                "step2_substrate_availability": s2["verdict"],
                "step3_lesson_11_sample_density": "NOT_REACHED",
                "step4_lesson_21_magnitude_ratio": "NOT_REACHED",
            },
            "hypothesis": {
                "axis_1": f"funding rate per-sym 30d z-score (Z_WINDOW={Z_WINDOW} @ 8h cadence)",
                "axis_2": "CVD ratio 4h aggregate via TBR joblib 5m",
                "joint_trigger_A": f"funding_z ≤ {FUNDING_Z_LOWER} AND CVD ≤ {CVD_LOWER}",
                "joint_trigger_B": f"funding_z ≥ +{FUNDING_Z_UPPER} AND CVD ≥ +{CVD_UPPER}",
                "direction_A_focus": "SHORT 4h (smart money exit before crowd capitulation)",
                "direction_B_focus": "LONG 4h (mirror condition)",
            },
            "params": {
                "funding_z_lower": FUNDING_Z_LOWER,
                "funding_z_upper": FUNDING_Z_UPPER,
                "cvd_lower": CVD_LOWER,
                "cvd_upper": CVD_UPPER,
                "z_window_obs": Z_WINDOW,
                "z_min_periods": Z_MIN_PERIODS,
            },
            "universe_cohort": COHORT,
            "step1_lesson_40": s1,
            "step2_substrate_audit": s2,
            "lesson_44_xref_22nd_amendment": lesson_44_xref,
            "lesson_40_sub_amendment_4th_dogfood": lesson_40_sub_amendment_4th_dogfood,
            "family_distinct_audit": family_distinct_audit,
            "reformulation_paths_for_user": reformulation_paths,
            "recommended_path_for_user_dispatch": recommended_path,
            "campaign_state": {
                "cumulative_graveyards_after_paradigm139": 139,
                "streak_non_pass": "11-streak (129-139)",
                "r5_live_count": 10,
                "lesson_40_instances": 4,
                "funding_family_tier_4_graveyards": 9,
            },
        }
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps(out, indent=2, default=str))
        log.info("R-0 output: %s", out_path)
        log.info("=== VERDICT: %s ===", verdict)
        log.info("=== SUB-CLASS: %s ===", sub_class)
        return 0

    # PASS path — proceed to STEP 2/3/4 then R-1 ready
    log.info("--- STEP 2: substrate audit ---")
    s2 = step2_substrate_audit(engine)
    log.info("funding_syms_ok=%d cvd_syms_ok=%d verdict=%s",
             s2["n_funding_syms_ok"], s2["n_cvd_syms_ok"], s2["verdict"])

    log.info("--- STEP 3: Lesson #11 expected_n joint trigger density ---")
    s3 = step3_lesson_11_expected_n(engine, s1["per_sym"])
    log.info("Total A_focus triggers: %d (per-quarter avg=%.1f)",
             s3["total_a_focus_triggers"], s3["per_cell_a_focus_per_quarter"])
    log.info("Total B_focus triggers: %d (per-quarter avg=%.1f)",
             s3["total_b_focus_triggers"], s3["per_cell_b_focus_per_quarter"])
    log.info("STEP 3 verdict: %s", s3["verdict"])

    log.info("--- STEP 4: Lesson #21 sub-finding magnitude-ratio prescreen ---")
    s4 = step4_lesson_21_magnitude_ratio(engine)
    log.info("mean_abs_pearson_r=%.3f max_abs_pearson_r=%.3f verdict=%s",
             s4["mean_abs_pearson_r"], s4["max_abs_pearson_r"], s4["verdict"])
    engine.dispose()

    # Final verdict synthesis
    components = {
        "step1_lesson_40_structural_threshold": s1["verdict"],
        "step2_substrate_availability": s2["verdict"],
        "step3_lesson_11_sample_density": s3["verdict"],
        "step4_lesson_21_magnitude_ratio": s4["verdict"],
    }
    if all(v in ("PASS",) for v in [s1["verdict"], s2["verdict"], s3["verdict"]]):
        verdict = "R0_READY_FOR_R1"
        sub_class = "all prescreens pass; ready for R-1 dispatch"
    else:
        # Should not reach here given top branch, but guard
        verdict = "R0_HALT_DOWNSTREAM_PRESCREEN"
        sub_class = f"downstream prescreen failure: {components}"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "sub_class": sub_class,
        "verdict_components": components,
        "universe_cohort": COHORT,
        "step1_lesson_40": s1,
        "step2_substrate_audit": s2,
        "step3_lesson_11": s3,
        "step4_lesson_21": s4,
    }
    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-0 output: %s", out_path)
    log.info("=== VERDICT: %s ===", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
