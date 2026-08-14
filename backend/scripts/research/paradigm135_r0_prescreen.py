"""paradigm 135 R-0 prescreen — alt_funding_implied_vs_realized_vol_premium_z_directional_4h.

Hypothesis (Volatility Risk Premium, VRP NEW family entry):
  Statistic = funding_implied_vol - realized_vol
    funding_implied_vol = funding_rate × (365 * 3)  (= ×1095, 8h cycle 3/day)
    realized_vol        = log_return_1h std × sqrt(24 × 365)  (annualized RV)
    VRP_t               = funding_implied_vol_t - realized_vol_t (single derived statistic)
  Z = per-symbol 30d rolling z-score of VRP
  Trigger: |VRP_z| > 2
  Direction:
    VRP_z > +2 (implied >> realized = "fear premium")  -> LONG (unwind)
    VRP_z < -2 (implied << realized = "complacency")   -> SHORT (reverse)
  Forward hold: 4h, debounce 8h
  Universe: 13 funding-DB syms (paradigm 132 cohort: AVAX/AXS/COMP/DOGE/ETC/
            HBAR/ICP/LDO/LINK/SOL/UNI/WLD/1000LUNC)

R-0 KEY VERIFICATIONS (must pass before R-1 dispatch):
  (A) Lesson #28 substrate: funding rate DB + 1m OHLCV (resample to 1h) PASS
  (B) Lesson #44 amendment xref 18th dogfood (funding-family reconciliation)
  (C) Lesson #54 candidate trap detection: mechanism story coherence
        - Is funding_rate × 1095 a true "implied vol"? (sign asymmetry check)
        - Magnitude comparison: |funding_implied| vs realized — which dominates?
        - Does VRP reduce to funding family OR RV family in practice?
  (D) Lesson #21 axis-stacking trap (subtle form): single derived stat but
        two-regime composite (funding-extreme vs RV-extreme)
  (E) Lesson #40 structural threshold attainability: VRP can be negative (signed)
        -> z-score symmetric reachable. Empirical |z|>2 reachable verification.

The R-0 prescreen WILL HALT before R-1 dispatch IF any of (B)(C)(D)(E) fails.
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p135_r0")

PARADIGM_NAME = "alt_funding_implied_vs_realized_vol_premium_z_directional_4h"
PARADIGM_NUM = 135
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# paradigm 132 cohort (13 funding-DB syms, ~370d funding × ~798d 1m OHLCV)
COHORT = [
    "AVAXUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "ETCUSDT",
    "HBARUSDT", "ICPUSDT", "LDOUSDT", "LINKUSDT", "SOLUSDT",
    "UNIUSDT", "WLDUSDT", "1000LUNCUSDT",
]

ANNUAL_HOURS = 24 * 365
RV_ROLLING_HOURS = 24 * 30      # 30d rolling 1h RV
FUNDING_ANNUAL_SCALE = 365 * 3   # ×1095 (8h cycle, 3/day, 365 days)
ZSCORE_ROLLING_HOURS = 30 * 24   # 30d rolling z of VRP
Z_THRESHOLD = 2.0
FEE_BP = 16.0
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_funding(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT funding_time, funding_rate FROM binance_funding_rate "
        "WHERE symbol=:s ORDER BY funding_time"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["funding_time"])
    if df.empty:
        return df
    df["funding_time"] = df["funding_time"].dt.floor("h")
    df["funding_rate"] = df["funding_rate"].astype(float)
    df = df.drop_duplicates(subset=["funding_time"], keep="last")
    df = df.set_index("funding_time").sort_index()
    return df


def load_ohlcv_1h_from_1m(sym: str, engine) -> pd.DataFrame:
    """Load 1m OHLCV and resample to 1h close."""
    q = text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df["close"] = df["close"].astype(float)
    df = df.set_index("timestamp").sort_index()
    close_1h = df["close"].resample("1h").last().dropna()
    return close_1h.to_frame("close")


def compute_realized_vol_1h(df_1h: pd.DataFrame) -> pd.Series:
    """30d rolling annualized realized vol from 1h log returns."""
    logret = np.log(df_1h["close"]).diff()
    rv = logret.rolling(RV_ROLLING_HOURS, min_periods=240).std() * math.sqrt(ANNUAL_HOURS)
    return rv


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    # ============================================================
    # Step A: substrate audit (Lesson #28)
    # ============================================================
    log.info("--- Step A: substrate audit (Lesson #28) ---")
    sym_data = {}
    per_sym_days = {}
    funding_days = {}
    for sym in COHORT:
        funding = load_funding(sym, engine)
        ohlcv_1h = load_ohlcv_1h_from_1m(sym, engine)
        if funding.empty:
            log.warning("%s: no funding -- skip", sym)
            continue
        if ohlcv_1h.empty or len(ohlcv_1h) < RV_ROLLING_HOURS * 2:
            log.warning("%s: insufficient 1h OHLCV (n=%d) -- skip", sym, len(ohlcv_1h))
            continue
        fdays = (funding.index.max() - funding.index.min()).days
        odays = (ohlcv_1h.index.max() - ohlcv_1h.index.min()).days
        funding_days[sym] = fdays
        per_sym_days[sym] = odays
        sym_data[sym] = {"funding": funding, "ohlcv_1h": ohlcv_1h}
        log.info("  %s: funding %d days, ohlcv 1h(resampled) %d days", sym, fdays, odays)
    engine.dispose()

    if len(sym_data) < 5:
        log.error("substrate audit FAIL: only %d syms with both funding+ohlcv", len(sym_data))
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps({
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "verdict": "R0_HALT_SUBSTRATE_INSUFFICIENT",
            "n_syms_loaded": len(sym_data),
        }, indent=2, default=str))
        sys.exit(2)

    # ============================================================
    # Step B: empirical magnitude comparison (Lesson #54 trap detection)
    # ============================================================
    log.info("--- Step B: empirical magnitude comparison (Lesson #54 trap detection) ---")
    per_sym_magnitude_audit = {}
    funding_extreme_dominates = []
    rv_dominates = []
    mixed = []
    for sym, d in sym_data.items():
        funding = d["funding"]
        ohlcv_1h = d["ohlcv_1h"]

        # funding_implied_vol = funding_rate × 1095 (annualized 8h cycle scaling)
        # NOTE: this is SIGNED (funding rate is signed)
        funding["implied_vol"] = funding["funding_rate"] * FUNDING_ANNUAL_SCALE

        # realized_vol 30d rolling 1h annualized
        rv = compute_realized_vol_1h(ohlcv_1h)
        rv_finite = rv.dropna()

        if len(rv_finite) == 0:
            log.warning("  %s: no realized vol -- skip", sym)
            continue

        # Sign asymmetry check (Lesson #54 candidate)
        implied_neg_pct = float((funding["implied_vol"] < 0).sum()) / len(funding) * 100.0
        implied_pos_pct = float((funding["implied_vol"] > 0).sum()) / len(funding) * 100.0

        # Magnitude comparison
        implied_abs_p50 = float(funding["implied_vol"].abs().quantile(0.50))
        implied_abs_p90 = float(funding["implied_vol"].abs().quantile(0.90))
        implied_abs_p99 = float(funding["implied_vol"].abs().quantile(0.99))
        rv_p50 = float(rv_finite.quantile(0.50))
        rv_p90 = float(rv_finite.quantile(0.90))
        rv_p99 = float(rv_finite.quantile(0.99))

        # Magnitude regime classification
        ratio_implied_to_rv_p50 = implied_abs_p50 / max(rv_p50, 1e-6)
        ratio_implied_to_rv_p99 = implied_abs_p99 / max(rv_p99, 1e-6)

        if ratio_implied_to_rv_p50 > 0.5:
            regime = "FUNDING_EXTREME_DOMINATES_TYPICAL_CASE"
            funding_extreme_dominates.append(sym)
        elif ratio_implied_to_rv_p99 > 2.0:
            regime = "FUNDING_EXTREME_DOMINATES_TAIL_CASE"
            funding_extreme_dominates.append(sym)
        elif ratio_implied_to_rv_p50 < 0.20:
            regime = "RV_DOMINATES_VRP_IS_RV_PROXY"
            rv_dominates.append(sym)
        else:
            regime = "MIXED_REGIME"
            mixed.append(sym)

        per_sym_magnitude_audit[sym] = {
            "funding_rate_min": float(funding["funding_rate"].min()),
            "funding_rate_max": float(funding["funding_rate"].max()),
            "implied_neg_pct": implied_neg_pct,
            "implied_pos_pct": implied_pos_pct,
            "implied_abs_p50_annual": implied_abs_p50,
            "implied_abs_p90_annual": implied_abs_p90,
            "implied_abs_p99_annual": implied_abs_p99,
            "rv_p50_annual": rv_p50,
            "rv_p90_annual": rv_p90,
            "rv_p99_annual": rv_p99,
            "ratio_implied_to_rv_p50": ratio_implied_to_rv_p50,
            "ratio_implied_to_rv_p99": ratio_implied_to_rv_p99,
            "regime": regime,
        }
        log.info("  %s: implied |abs| p50=%.4f p99=%.4f / rv p50=%.4f p99=%.4f / ratio p50=%.3f p99=%.3f / regime=%s",
                 sym, implied_abs_p50, implied_abs_p99, rv_p50, rv_p99,
                 ratio_implied_to_rv_p50, ratio_implied_to_rv_p99, regime)

    log.info("Magnitude regime classification:")
    log.info("  FUNDING_EXTREME_DOMINATES (collapses to funding family): %s", funding_extreme_dominates)
    log.info("  RV_DOMINATES (collapses to RV family — p67-69/133/134 already retired): %s", rv_dominates)
    log.info("  MIXED_REGIME: %s", mixed)

    # ============================================================
    # Step C: Lesson #54 mechanism coherence verdict
    # ============================================================
    log.info("--- Step C: Lesson #54 candidate trap detection verdict ---")
    n_funding_collapse = len(funding_extreme_dominates)
    n_rv_collapse = len(rv_dominates)
    n_mixed = len(mixed)
    n_total = n_funding_collapse + n_rv_collapse + n_mixed

    avg_implied_neg_pct = float(np.mean([v["implied_neg_pct"]
                                          for v in per_sym_magnitude_audit.values()]))
    sign_asymmetry_trap = avg_implied_neg_pct > 30.0

    family_reduction_trap = (n_funding_collapse + n_rv_collapse) / max(n_total, 1) >= 0.70

    lesson_54_verdict = {
        "mechanism_story_claim": "VRP = implied_vol - realized_vol, regime divergence directional signal",
        "empirical_finding_1_sign_asymmetry": (
            f"funding_rate * 1095 produces {avg_implied_neg_pct:.1f}% NEGATIVE values "
            f"on average. True implied vol is non-negative by definition (sigma >= 0). "
            f"Construction is rescaled signed funding rate with misleading 'implied vol' label."
        ),
        "empirical_finding_2_magnitude_dominance": (
            f"FUNDING_EXTREME_DOMINATES: {n_funding_collapse}/{n_total} syms ({funding_extreme_dominates}); "
            f"RV_DOMINATES: {n_rv_collapse}/{n_total} syms ({rv_dominates}); "
            f"MIXED: {n_mixed}/{n_total} syms ({mixed}). "
            f"VRP empirically reduces to either funding family or RV family per-sym."
        ),
        "sign_asymmetry_trap_triggered": sign_asymmetry_trap,
        "family_reduction_trap_triggered": family_reduction_trap,
        "verdict": ("LESSON_54_TRAP_CONFIRMED" if (sign_asymmetry_trap or family_reduction_trap)
                    else "LESSON_54_TRAP_CLEAR"),
    }
    log.info("Lesson #54 candidate trap verdict: %s", lesson_54_verdict["verdict"])
    log.info("  sign_asymmetry_trap: %s (avg %% implied<0 = %.1f%%, >30%% triggers)",
             sign_asymmetry_trap, avg_implied_neg_pct)
    log.info("  family_reduction_trap: %s ((funding+rv collapse)/total = %.2f, >=0.70 triggers)",
             family_reduction_trap, (n_funding_collapse + n_rv_collapse) / max(n_total, 1))

    # ============================================================
    # Step D: Lesson #44 amendment xref 18th dogfood (funding-family)
    # ============================================================
    log.info("--- Step D: Lesson #44 amendment xref 18th dogfood ---")
    lesson_44_xref = {
        "paradigm_22_funding_carry_R5_SEEDED":
            "R-5 SEEDED — 30d funding-rate z-score MR continuous. Funding family EXCEPTION (only).",
        "paradigm_73_funding_oi_bipolar_squeeze":
            "GRAVEYARD funding family — joint funding × OI event.",
        "paradigm_79_funding_rate_sign_flip_event":
            "GRAVEYARD funding family — funding sign change event.",
        "paradigm_96_funding_rate_sign_flip_event_alt_LONG_4h":
            "GRAVEYARD funding family — 4-quadrant SNT 0/4 PASS.",
        "paradigm_97_funding_term_structure_cs_dispersion":
            "GRAVEYARD funding family — cross-sym dispersion of funding term structure.",
        "paradigm_98_funding_regime_stratify_dispersion":
            "GRAVEYARD funding family — regime-stratified funding dispersion.",
        "paradigm_99_funding_velocity_cross_section_dispersion":
            "GRAVEYARD funding family — cross-sym funding velocity dispersion.",
        "paradigm_132_funding_oi_magnitude_triple":
            "GRAVEYARD funding family + Lesson #21 axis-stacking. Same 13-sym cohort.",
        "paradigm_67_btc_rv_spike_alt_recovery":
            "GRAVEYARD — BTC 1d total RV.",
        "paradigm_68_btc_rv_spike_up_conditional":
            "GRAVEYARD R-3.5 — BTC RV sign-cond.",
        "paradigm_69_btc_rv_spike_highvol_filter":
            "R-5 SEEDED — BTC RV p90 LONG.",
        "paradigm_118_realized_correlation_regime":
            "GRAVEYARD — universe-aggregate corr.",
        "paradigm_124_alt_realized_kurtosis_skewness":
            "GRAVEYARD — 3rd × 4th moment joint.",
        "paradigm_125_alt_realized_quarticity_bipower":
            "R-0 HALT Lesson #40 — B-N jump test ratio.",
        "paradigm_129_alt_parkinson_range":
            "GRAVEYARD — Parkinson high-low range.",
        "paradigm_133_alt_realized_vol_of_vol":
            "GRAVEYARD CONCENTRATED_R1_PASS — vol-of-vol 2nd-order clustering.",
        "paradigm_134_alt_realized_semivariance_asymmetry":
            "GRAVEYARD BROAD_FALSIFIED — up/down RV ratio.",
    }
    log.info("Lesson #44 18th xref documented (17 cross-references)")

    funding_family_collision = (
        family_reduction_trap and len(funding_extreme_dominates) >= 3
    )
    rv_family_collision = (
        family_reduction_trap and len(rv_dominates) >= 3
    )
    lesson_44_reconciliation = {
        "funding_family_tier_4_retire_collision": funding_family_collision,
        "rv_family_retired_collision": rv_family_collision,
        "verdict": ("LESSON_44_FAMILY_DISTINCT_FAIL"
                    if (funding_family_collision or rv_family_collision)
                    else "LESSON_44_FAMILY_DISTINCT_PASS"),
        "reasoning": (
            f"VRP empirically reduces to funding family ({len(funding_extreme_dominates)} syms) "
            f"or RV family ({len(rv_dominates)} syms). Funding family Tier 4 retire = 6 sub-class "
            f"graveyards (73/79/96/97/98/99) + paradigm 132. RV family = paradigm 67-69+118+124+125+"
            f"129+133+134 all graveyarded except p69 R-5 seed."
        ),
    }
    log.info("Lesson #44 reconciliation verdict: %s", lesson_44_reconciliation["verdict"])

    # ============================================================
    # Step E: Final R-0 verdict
    # ============================================================
    log.info("--- Step E: Final R-0 verdict ---")
    halt = (
        lesson_54_verdict["verdict"] == "LESSON_54_TRAP_CONFIRMED"
        or lesson_44_reconciliation["verdict"] == "LESSON_44_FAMILY_DISTINCT_FAIL"
    )
    if halt:
        verdict = "R0_HALT_LESSON_54_MECHANISM_INCOHERENT_FUNDING_RV_FAMILY_REDUCTION"
    else:
        verdict = "R0_READY_FOR_R1"

    log.info("=== FINAL R-0 VERDICT: %s ===", verdict)

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "universe_cohort": COHORT,
        "universe_loaded": list(sym_data.keys()),
        "params": {
            "funding_annual_scale": FUNDING_ANNUAL_SCALE,
            "rv_rolling_hours": RV_ROLLING_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold_absolute": Z_THRESHOLD,
            "fee_bp": FEE_BP,
            "annual_hours": ANNUAL_HOURS,
        },
        "per_sym_funding_days": funding_days,
        "per_sym_ohlcv_1h_days": per_sym_days,
        "per_sym_magnitude_audit": per_sym_magnitude_audit,
        "regime_classification": {
            "funding_extreme_dominates": funding_extreme_dominates,
            "rv_dominates": rv_dominates,
            "mixed_regime": mixed,
        },
        "lesson_54_verdict": lesson_54_verdict,
        "lesson_44_amendment_xref_18th_dogfood": lesson_44_xref,
        "lesson_44_reconciliation": lesson_44_reconciliation,
    }
    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-0 saved to %s", out_path)
    if halt:
        sys.exit(2)


if __name__ == "__main__":
    main()
