"""paradigm 140 R-0 prescreen — alt_funding_per_sym_30d_zscore_NEG_ONLY_x_cvd_4h_negative_2quadrant_SNT_directional_4h.

paradigm 139 Lesson #40 4th dogfood structural fix (path 1: drop B-quadrant per
substrate infeasibility, recover paradigm 22 R-5 one-sided z-score approach,
add CVD axis joint).

Hypothesis (one-sided A only + 2-quadrant SNT exception):
  funding per-sym 30d z-score ≤ -2.0 (extreme LONG-crowded, paradigm 22 R-5 alignment)
    AND 4h CVD ratio ≤ -0.1 (sustained taker SELL, smart-money distribution proxy)
    -> SHORT 4h (continuation thesis: crowded long + smart selling → cascade DOWN)
  vs paradigm 22 R-5 SEEDED (mean-reversion LONG, single-axis funding):
    paradigm 140 = SHORT continuation joint (funding_z + CVD) — family-DISTINCT direction.

2-quadrant SNT (Lesson #19 exception, justified by paradigm 139 R-0 Lesson #40
sub-class C 4th dogfood: B-side trigger funding_z ≥ +2.0 substrate infeasible):
  A_focus  = funding_z ≤ -2.0 × CVD ≤ -0.1 × SHORT 4h     (primary)
  A_mirror = funding_z ≤ -2.0 × CVD ≤ -0.1 × LONG 4h      (mean-reversion contrary)

R-0 sequential prescreen (paradigm-architect spec, all gates):

  STEP 1 (Lesson #40 structural threshold attainability — FIRST per spec):
    A-side ONLY (B-side intentionally dropped per paradigm 139 inheritance).
    Verify funding_z ≤ -2.0 reachable at rate ≥ 1.5% in ≥ 3/10 syms.
    Re-confirm paradigm 139 STEP 1 A-side result.

  STEP 2 (Lesson #28 substrate availability):
    funding DB + CVD joblib both available for 10/10 cohort syms.

  STEP 3 (CVD distribution audit — paradigm 139 risk inheritance):
    A-side CVD ≤ -0.1 empirical rate per-sym. <2% halt risk (paradigm 139 pre-empt).

  STEP 4 (Lesson #11 expected_n joint trigger density):
    funding_z ≤ -2.0 × CVD ≤ -0.1 joint per-cell n ≥ 30 across 4 quarters.

  STEP 5 (Lesson #21 sub-finding magnitude-ratio prescreen, 6th dogfood candidate):
    funding_z vs CVD per-sym Pearson correlation < 0.5 (axis independence).

  STEP 6 (Lesson #44 23rd amendment cross-reference dogfood):
    paradigm 22 R-5 (direction-distinct: paradigm 22 LONG MR / paradigm 140 SHORT continuation)
    paradigm 132 R-1 GRAVEYARD (Lesson #21 5th dogfood, 3-way axis stacking trap)
    paradigm 138/139 (Lesson #40 sub-class C 3rd/4th dogfood, paradigm 140 reformulation path)
    paradigm 72 (taker volume 5m family Tier 4 retire — CVD ratio at 4h DNA-distinct)

VERDICT logic:
  if all 5 steps PASS: R0_READY_FOR_R1_2QUADRANT_SNT_EXCEPTION_JUSTIFIED
  else: R0_HALT_<failure_step>
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
log = logging.getLogger("p140_r0")

PARADIGM_NAME = "alt_funding_per_sym_30d_zscore_NEG_ONLY_x_cvd_4h_negative_2quadrant_SNT_directional_4h"
PARADIGM_NUM = 140
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 10-sym cohort — paradigm 138/139 funding-DB-available subset
COHORT = [
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "AVAXUSDT",
    "SOLUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT",
    "LDOUSDT", "ETCUSDT",
]

FUNDING_Z_LOWER = -2.0       # A-side only (B-side dropped per paradigm 139)
CVD_LOWER = -0.1             # A-side only (sustained taker SELL)
Z_WINDOW = 90                # 30d at 8h funding cadence
Z_MIN_PERIODS = 60

DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
MICRO_DIR = Path("/home/hcpark/antigravity/backend/runs/microstructure")


def load_funding_zscore(engine, sym: str) -> pd.Series:
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


def step1_funding_z_a_side_only(engine) -> dict:
    out = {}
    for sym in COHORT:
        z = load_funding_zscore(engine, sym)
        if len(z) < 50:
            out[sym] = {"n": int(len(z)), "skip": True}
            continue
        n_low = int((z <= FUNDING_Z_LOWER).sum())
        out[sym] = {
            "n": int(len(z)),
            "p1": float(z.quantile(0.01)),
            "p5": float(z.quantile(0.05)),
            "p50": float(z.quantile(0.50)),
            "min": float(z.min()),
            "n_below_neg2": n_low,
            "rate_below_neg2": n_low / len(z),
        }
    n_aud = sum(1 for v in out.values() if not v.get("skip"))
    n_reachable = sum(
        1 for v in out.values() if not v.get("skip") and v["rate_below_neg2"] >= 0.015
    )
    return {
        "per_sym": out,
        "n_syms_audited": n_aud,
        "n_syms_below_reachable": n_reachable,
        "verdict": "PASS" if n_reachable >= 3 else "FAIL_A_SIDE_INFEASIBLE",
        "threshold": f"funding_z ≤ {FUNDING_Z_LOWER} A-side only (B-side dropped per paradigm 139)",
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
        cvd_audit[sym] = {"available": p.exists()}
    n_f_ok = sum(1 for v in funding_audit.values() if v["n"] >= 200)
    n_c_ok = sum(1 for v in cvd_audit.values() if v["available"])
    return {
        "funding_db": funding_audit,
        "cvd_joblib": cvd_audit,
        "n_funding_syms_ok": n_f_ok,
        "n_cvd_syms_ok": n_c_ok,
        "verdict": "PASS" if (n_f_ok >= 8 and n_c_ok >= 8) else "FAIL",
    }


def step3_cvd_distribution_audit() -> dict:
    """Per-sym CVD distribution + A-side rate ≥ 2%."""
    out = {}
    for sym in COHORT:
        cvd = load_cvd_4h(sym)
        if len(cvd) < 100:
            out[sym] = {"skip": True}
            continue
        n_low = int((cvd <= CVD_LOWER).sum())
        out[sym] = {
            "n": int(len(cvd)),
            "p1": float(cvd.quantile(0.01)),
            "p5": float(cvd.quantile(0.05)),
            "p50": float(cvd.quantile(0.50)),
            "min": float(cvd.min()),
            "n_below_cvd_lower": n_low,
            "rate_below_cvd_lower": n_low / len(cvd),
        }
    n_aud = sum(1 for v in out.values() if not v.get("skip"))
    n_reachable = sum(
        1 for v in out.values() if not v.get("skip") and v["rate_below_cvd_lower"] >= 0.02
    )
    return {
        "per_sym": out,
        "n_syms_audited": n_aud,
        "n_syms_cvd_reachable": n_reachable,
        "verdict": "PASS" if n_reachable >= 3 else "FAIL_CVD_A_SIDE_INFEASIBLE",
        "threshold": f"CVD ≤ {CVD_LOWER} A-side reachable at ≥ 2% per-sym",
    }


def step4_lesson_11_joint_density(engine) -> dict:
    joint_audit = {}
    total_a = 0
    for sym in COHORT:
        z = load_funding_zscore(engine, sym)
        cvd = load_cvd_4h(sym)
        if len(z) < 50 or len(cvd) < 50:
            joint_audit[sym] = {"skip": True}
            continue
        z_4h = z.reindex(cvd.index, method="ffill").dropna()
        cvd_aligned = cvd.reindex(z_4h.index).dropna()
        common = z_4h.index.intersection(cvd_aligned.index)
        if len(common) < 100:
            joint_audit[sym] = {"skip": True, "n_common": int(len(common))}
            continue
        z_c = z_4h.loc[common]
        cvd_c = cvd_aligned.loc[common]
        mask_a = (z_c <= FUNDING_Z_LOWER) & (cvd_c <= CVD_LOWER)
        n_a = int(mask_a.sum())
        total_a += n_a
        joint_audit[sym] = {
            "n_common_4h_bars": int(len(common)),
            "n_a_joint": n_a,
            "rate_a": n_a / len(common),
        }
    n_quarters = 4
    per_cell = total_a / n_quarters if total_a else 0
    return {
        "per_sym_joint": joint_audit,
        "total_a_joint_triggers": total_a,
        "per_cell_a_per_quarter": round(per_cell, 1),
        "verdict": "PASS" if per_cell >= 30 else "FAIL_SAMPLE_INSUFFICIENT",
        "threshold": "per-cell n ≥ 30 across 4 quarters (Lesson #11)",
    }


def step5_lesson_21_correlation(engine) -> dict:
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
    log.info("Hypothesis: funding_z ≤ %.1f × CVD ≤ %.2f × SHORT 4h (2-quadrant SNT exception)",
             FUNDING_Z_LOWER, CVD_LOWER)
    engine = create_engine(DB_DSN)

    log.info("--- STEP 1: funding_z A-side only attainability ---")
    s1 = step1_funding_z_a_side_only(engine)
    log.info(f"{'sym':>10} {'n':>5} {'p1':>6} {'p5':>6} {'p50':>6} {'min':>7} {'z<=-2':>8}")
    for sym, d in s1["per_sym"].items():
        if d.get("skip"):
            log.info(f"  {sym:>8} SKIP n={d['n']}")
            continue
        log.info(
            f"  {sym:>8} {d['n']:>5} {d['p1']:>6.2f} {d['p5']:>6.2f} {d['p50']:>6.2f} "
            f"{d['min']:>7.2f} {d['rate_below_neg2']*100:>6.2f}%"
        )
    log.info("STEP 1 verdict: %s (n_reachable=%d/%d)",
             s1["verdict"], s1["n_syms_below_reachable"], s1["n_syms_audited"])

    log.info("--- STEP 2: substrate audit ---")
    s2 = step2_substrate_audit(engine)
    log.info("funding_syms_ok=%d cvd_syms_ok=%d verdict=%s",
             s2["n_funding_syms_ok"], s2["n_cvd_syms_ok"], s2["verdict"])

    log.info("--- STEP 3: CVD A-side distribution audit (paradigm 139 risk inheritance) ---")
    s3 = step3_cvd_distribution_audit()
    log.info(f"{'sym':>10} {'n':>5} {'p1':>6} {'p5':>6} {'p50':>6} {'min':>7} {'cvd<=-0.1':>10}")
    for sym, d in s3["per_sym"].items():
        if d.get("skip"):
            log.info(f"  {sym:>8} SKIP")
            continue
        log.info(
            f"  {sym:>8} {d['n']:>5} {d['p1']:>6.3f} {d['p5']:>6.3f} {d['p50']:>6.3f} "
            f"{d['min']:>7.3f} {d['rate_below_cvd_lower']*100:>8.2f}%"
        )
    log.info("STEP 3 verdict: %s (n_reachable=%d/%d)",
             s3["verdict"], s3["n_syms_cvd_reachable"], s3["n_syms_audited"])

    log.info("--- STEP 4: Lesson #11 joint trigger density ---")
    s4 = step4_lesson_11_joint_density(engine)
    log.info("Total joint A triggers: %d (per-quarter avg=%.1f)",
             s4["total_a_joint_triggers"], s4["per_cell_a_per_quarter"])
    log.info("STEP 4 verdict: %s", s4["verdict"])

    log.info("--- STEP 5: Lesson #21 magnitude-ratio prescreen ---")
    s5 = step5_lesson_21_correlation(engine)
    log.info("mean_abs_r=%.3f max_abs_r=%.3f verdict=%s",
             s5["mean_abs_pearson_r"], s5["max_abs_pearson_r"], s5["verdict"])
    engine.dispose()

    components = {
        "step1_funding_z_a_side": s1["verdict"],
        "step2_substrate": s2["verdict"],
        "step3_cvd_distribution": s3["verdict"],
        "step4_lesson_11_joint_density": s4["verdict"],
        "step5_lesson_21_correlation": s5["verdict"],
    }
    fatal_steps = ["step1_funding_z_a_side", "step2_substrate",
                   "step3_cvd_distribution", "step4_lesson_11_joint_density"]
    fatal_fail = any(components[s] != "PASS" for s in fatal_steps)

    lesson_44_xref = {
        "paradigm_22_funding_carry_R5_SEEDED":
            "HBAR/AXS/COMP R-5 LIVE. paradigm 22 = single-axis funding_z LONG MR. "
            "paradigm 140 = funding_z × CVD joint SHORT continuation. DIRECTION-DISTINCT.",
        "paradigm_72_taker_volume_5m_GRAVEYARD":
            "5m taker volume family Tier 4 retire. paradigm 140 CVD = 4h aggregated RATIO "
            "(not 5m volume magnitude). DNA-distinct dimension.",
        "paradigm_132_R1_GRAVEYARD_LESSON_21_5TH_DOGFOOD":
            "Triple joint axis stacking trap. paradigm 140 = 2-axis only (funding_z + CVD), "
            "less aggressive stacking. Lesson #21 6th dogfood: V1 funding_z alone × SHORT vs "
            "V2 CVD alone × SHORT vs V3 joint × SHORT — V3 must outperform max(V1,V2) × 1.2.",
        "paradigm_138_funding_raw_bp_R0_HALT":
            "Lesson #40 sub-class C 3rd dogfood. paradigm 140 inherits this halt by adopting "
            "per-sym z-score (paradigm 22 R-5 approach).",
        "paradigm_139_funding_persym_z_R0_HALT":
            "Lesson #40 sub-class C 4th dogfood. paradigm 140 direct reformulation via path 1: "
            "drop B-quadrant (substrate infeasible), recover A-only one-sided z-score.",
        "funding_family_tier_4_retire":
            "9 graveyards (73/79*/96/97/98/99/103/132/138/139). paradigm 22+79 R-5 exception. "
            "paradigm 140 = one-sided + joint CVD axis attempt within Tier 4 retire envelope.",
    }

    lesson_19_snt_exception_justification = {
        "default_requirement": "4-quadrant SNT (A_focus + A_mirror + B_focus + B_mirror)",
        "exception_invoked": "2-quadrant SNT (A_focus + A_mirror only)",
        "justification_basis": "paradigm 139 R-0 STEP 1 Lesson #40 4th dogfood CONFIRMED: "
                              "funding_z ≥ +2.0 substrate-infeasible (0/10 syms reach ≥ 1.5% rate, "
                              "p95-p99 universally < +2.0). B-quadrant test is measurement of "
                              "infeasibility, not test of mechanism. Lesson #40 sub-class C "
                              "(per-sym z-score of asymmetrically exchange-bounded scalar) is "
                              "STRUCTURAL barrier — Lesson #19 SNT presumes both sides measurable.",
        "precedent": "paradigm 22 R-5 SEEDED HBAR/AXS/COMP is itself one-sided directional "
                     "(funding-negative → LONG MR), same A-only structural design.",
        "lesson_19_amendment_candidate": "When Lesson #40 confirms substrate infeasibility for "
                                         "one quadrant, 2-quadrant SNT (focus + mirror on the "
                                         "feasible side) replaces 4-quadrant requirement.",
    }

    family_distinct_audit = {
        "paradigm_22_R5_direction": "LONG MR (mean-reversion on funding-neg)",
        "paradigm_140_direction": "SHORT continuation (joint with CVD smart-selling)",
        "direction_distinct": True,
        "axis_count_distinct": "paradigm 22 single-axis funding vs paradigm 140 2-axis joint",
        "mechanism_distinct": "MR vs continuation (opposite direction on same trigger sign)",
    }

    if fatal_fail:
        # Identify first failing fatal step
        for s in fatal_steps:
            if components[s] != "PASS":
                first_fail = s
                break
        verdict = f"R0_HALT_{first_fail.upper()}"
        sub_class = f"R-0 halt at {first_fail} = {components[first_fail]}"
    elif s5["verdict"] != "PASS":
        verdict = "R0_READY_FOR_R1_2QUADRANT_SNT_EXCEPTION_WITH_HIGH_CORR_WARNING"
        sub_class = (f"All fatal gates PASS; Lesson #21 correlation high "
                     f"(max_abs_r={s5['max_abs_pearson_r']:.3f}) — proceed with caution, "
                     f"V1/V2/V3 individual-vs-joint test will detect axis stacking trap")
    else:
        verdict = "R0_READY_FOR_R1_2QUADRANT_SNT_EXCEPTION_JUSTIFIED"
        sub_class = ("All 5 R-0 gates PASS. funding_z A-side reachable + CVD A-side reachable "
                     "+ joint density sufficient + correlation independent + substrate intact. "
                     "Lesson #19 SNT 2-quadrant exception justified by paradigm 139 inheritance. "
                     "Ready for R-1 dispatch.")

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "sub_class": sub_class,
        "verdict_components": components,
        "hypothesis": {
            "axis_1": f"funding rate per-sym 30d z-score ≤ {FUNDING_Z_LOWER} (A-side only)",
            "axis_2": f"CVD 4h aggregate ≤ {CVD_LOWER} (A-side only)",
            "joint_trigger_A": f"funding_z ≤ {FUNDING_Z_LOWER} AND CVD ≤ {CVD_LOWER}",
            "direction_A_focus": "SHORT 4h (smart distribution preceding cascade)",
            "direction_A_mirror": "LONG 4h (mean-reversion contrary)",
            "snt_structure": "2-quadrant (Lesson #19 exception, paradigm 139 inheritance)",
        },
        "params": {
            "funding_z_lower": FUNDING_Z_LOWER,
            "cvd_lower": CVD_LOWER,
            "z_window_obs": Z_WINDOW,
            "fee_per_trade": 0.0008,
        },
        "universe_cohort": COHORT,
        "step1_funding_z_a_side": s1,
        "step2_substrate": s2,
        "step3_cvd_distribution": s3,
        "step4_lesson_11_joint_density": s4,
        "step5_lesson_21_correlation": s5,
        "lesson_44_xref_23rd_amendment": lesson_44_xref,
        "lesson_19_snt_exception_justification": lesson_19_snt_exception_justification,
        "family_distinct_audit": family_distinct_audit,
        "campaign_state": {
            "cumulative_graveyards_before_paradigm140": 139,
            "streak_non_pass": "11-streak (129-139)",
            "r5_live_count": 10,
            "lesson_40_instances_pre_paradigm140": 4,
            "funding_family_tier_4_graveyards": 9,
        },
    }
    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-0 output: %s", out_path)
    log.info("=== VERDICT: %s ===", verdict)
    log.info("=== SUB-CLASS: %s ===", sub_class)
    return 0


if __name__ == "__main__":
    sys.exit(main())
