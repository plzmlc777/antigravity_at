"""paradigm 200 R-0 prescreen — alt_per_sym_30d_volatility_risk_premium_funding_implied_vs_realized_vol_z_spike_directional_4h_bilateral.

200th paradigm milestone. Volatility Risk Premium (VRP) cross-substrate fusion axis attempt.

paradigm 200 differs from paradigm 135 in formula details:
  - paradigm 135: funding_implied_vol = funding_rate * 1095 (SIGNED)
                  realized_vol       = log_return_1h.std() * sqrt(24*365) (1h frame)
  - paradigm 200: ann_funding_vol    = abs(funding_rate) * 3 * 365 * 100 (UNSIGNED, scaled %)
                  ann_realized_vol   = sqrt(252) * daily_return_std * 100 (daily frame, scaled %)
                  VRP                = ann_funding_vol - ann_realized_vol
                  z = 90d rolling z of VRP
                  trigger |z| >= 2 bilateral 4-quadrant SNT

Key R-0 audit: Is paradigm 200 still vulnerable to Lesson #54 family-reduction trap?
  - paradigm 200 uses abs() so sign asymmetry trap is auto-resolved (PASS).
  - BUT magnitude dominance trap (RV_DOMINATES / FUNDING_EXTREME_TAIL):
    if |funding|*1095*100 << daily_RV*sqrt(252)*100 typically per-sym, VRP_z ~ -RV_z (RV family).
    if |funding|*1095*100 >> daily_RV*sqrt(252)*100 in tail, VRP_z ~ |funding|_z (funding family).
  - Empirical magnitude comparison on paradigm 198 expanded 20-sym cohort.

Universe: paradigm 198 cohort 20 alts (joblib cache available).
But intersect with funding DB availability. Substrate audit first.
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
log = logging.getLogger("p200_r0")

PARADIGM_NAME = (
    "alt_per_sym_30d_volatility_risk_premium_funding_implied_vs_realized_vol_z_spike_directional_4h_bilateral"
)
PARADIGM_NUM = 200
OUT_DIR = Path(
    f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}"
)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# paradigm 198 expanded 20-sym cohort
COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "DOTUSDT", "ETCUSDT", "ETHUSDT", "FILUSDT", "JUPUSDT", "LDOUSDT",
    "LINKUSDT", "LTCUSDT", "NEARUSDT", "PYTHUSDT", "SOLUSDT", "UNIUSDT",
    "WIFUSDT", "WLDUSDT", "XRPUSDT",
]

# paradigm 200 specification (from dispatch hypothesis)
# ann_funding_vol = abs(funding_rate) * 3 * 365 * 100  (8h cycle × 3/day × 365 × 100)
FUNDING_ANNUAL_SCALE = 3 * 365 * 100   # ×109500 to %
# ann_realized_vol = sqrt(252) * daily_return_std * 100
RV_DAILY_TO_ANNUAL = math.sqrt(252)
RV_ROLLING_DAYS = 30          # 30d rolling daily-return std
Z_ROLLING_DAYS = 90           # 90d rolling z-score of VRP
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


def load_ohlcv_4h_joblib(sym: str) -> pd.DataFrame:
    """Load 4h OHLCV joblib cache (paradigm 198 expanded cohort)."""
    import joblib
    p = Path(f"/home/hcpark/antigravity/backend/runs/ohlcv_cache_12col/{sym}_4h.joblib")
    if not p.exists():
        return pd.DataFrame()
    df = joblib.load(p)
    # standard col: timestamp, close
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
        df = df.set_index("timestamp")
    df = df.sort_index()
    return df


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("paradigm name: %s", PARADIGM_NAME)
    engine = create_engine(DB_DSN)

    # ============================================================
    # Step 0: Lesson #61 slug grep audit (DONE manually outside script)
    # paradigm 135 prior R-0 HALT confirmed mechanism-identical attempt.
    # paradigm 200 must verify formula difference resolves trap or NOT.
    # ============================================================
    log.info("--- Step 0: Lesson #61 slug grep audit ---")
    log.info("  paradigm 135 prior R-0 HALT: alt_funding_implied_vs_realized_vol_premium_z_directional_4h")
    log.info("  paradigm 200 formula delta:")
    log.info("    - abs(funding_rate) instead of signed funding_rate -> sign asymmetry trap auto-resolved")
    log.info("    - daily frame RV instead of 1h frame RV -> magnitude dominance unknown")
    log.info("    - 90d z window instead of 30d -> z-score window 3x larger")
    log.info("    - bilateral 4-quadrant SNT instead of signed direction -> Lesson #19 compliant")
    log.info("  Empirical magnitude comparison required.")

    # ============================================================
    # Step A: substrate audit (Lesson #28)
    # ============================================================
    log.info("--- Step A: substrate audit (Lesson #28) ---")
    sym_data = {}
    funding_days = {}
    ohlcv_days = {}
    skipped = {}
    for sym in COHORT:
        funding = load_funding(sym, engine)
        if funding.empty:
            log.warning("  %s: NO FUNDING IN DB -- skip", sym)
            skipped[sym] = "no_funding"
            continue
        ohlcv_4h = load_ohlcv_4h_joblib(sym)
        if ohlcv_4h.empty or "close" not in ohlcv_4h.columns:
            log.warning("  %s: no 4h OHLCV joblib -- skip", sym)
            skipped[sym] = "no_ohlcv_joblib"
            continue
        fdays = (funding.index.max() - funding.index.min()).days
        odays = (ohlcv_4h.index.max() - ohlcv_4h.index.min()).days
        funding_days[sym] = fdays
        ohlcv_days[sym] = odays
        sym_data[sym] = {"funding": funding, "ohlcv_4h": ohlcv_4h}
        log.info("  %s: funding %d days, ohlcv4h %d days", sym, fdays, odays)
    engine.dispose()

    if len(sym_data) < 5:
        log.error("substrate audit FAIL: only %d syms with funding+ohlcv", len(sym_data))
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps({
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "verdict": "R0_HALT_SUBSTRATE_INSUFFICIENT",
            "n_syms_loaded": len(sym_data),
            "skipped": skipped,
        }, indent=2, default=str))
        sys.exit(2)

    # ============================================================
    # Step B: empirical magnitude comparison (Lesson #54 trap detection)
    # paradigm 200 formula:
    #   ann_funding_vol = abs(funding_rate) * 109500  (scaled to %)
    #   ann_realized_vol = sqrt(252) * daily_return_std * 100
    # ============================================================
    log.info("--- Step B: empirical magnitude comparison (paradigm 200 formula) ---")
    per_sym_magnitude_audit = {}
    funding_dominates = []
    rv_dominates = []
    mixed = []
    for sym, d in sym_data.items():
        funding = d["funding"]
        ohlcv_4h = d["ohlcv_4h"]

        # paradigm 200 ann_funding_vol = abs(funding_rate) * 3 * 365 * 100
        ann_funding_vol = (funding["funding_rate"].abs() * FUNDING_ANNUAL_SCALE)

        # paradigm 200 ann_realized_vol = sqrt(252) * daily_return_std * 100
        # Compute daily close from 4h cache.
        close_daily = ohlcv_4h["close"].resample("1D").last().dropna()
        daily_ret = close_daily.pct_change()
        # 30d rolling daily std, annualized to %
        rv_daily = daily_ret.rolling(RV_ROLLING_DAYS, min_periods=15).std()
        ann_realized_vol = rv_daily * RV_DAILY_TO_ANNUAL * 100.0
        ann_realized_vol = ann_realized_vol.dropna()

        if len(ann_realized_vol) == 0:
            log.warning("  %s: no RV computed -- skip", sym)
            continue

        # Magnitude comparison
        impl_p50 = float(ann_funding_vol.quantile(0.50))
        impl_p90 = float(ann_funding_vol.quantile(0.90))
        impl_p99 = float(ann_funding_vol.quantile(0.99))
        rv_p50 = float(ann_realized_vol.quantile(0.50))
        rv_p90 = float(ann_realized_vol.quantile(0.90))
        rv_p99 = float(ann_realized_vol.quantile(0.99))

        ratio_p50 = impl_p50 / max(rv_p50, 1e-6)
        ratio_p99 = impl_p99 / max(rv_p99, 1e-6)

        # Lesson #54 regime classification (paradigm 200 thresholds)
        # NOTE: with abs() and ×100 scaling, magnitudes are directly comparable as %.
        if ratio_p50 > 0.5 and ratio_p99 > 0.5:
            regime = "FUNDING_DOMINATES_TYPICAL_CASE"
            funding_dominates.append(sym)
        elif ratio_p99 > 2.0:
            regime = "FUNDING_DOMINATES_TAIL_CASE"
            funding_dominates.append(sym)
        elif ratio_p50 < 0.20:
            regime = "RV_DOMINATES_VRP_IS_NEG_RV_PROXY"
            rv_dominates.append(sym)
        else:
            regime = "MIXED_REGIME"
            mixed.append(sym)

        per_sym_magnitude_audit[sym] = {
            "funding_rate_min": float(funding["funding_rate"].min()),
            "funding_rate_max": float(funding["funding_rate"].max()),
            "ann_funding_vol_p50_pct": impl_p50,
            "ann_funding_vol_p90_pct": impl_p90,
            "ann_funding_vol_p99_pct": impl_p99,
            "ann_realized_vol_p50_pct": rv_p50,
            "ann_realized_vol_p90_pct": rv_p90,
            "ann_realized_vol_p99_pct": rv_p99,
            "ratio_funding_to_rv_p50": ratio_p50,
            "ratio_funding_to_rv_p99": ratio_p99,
            "regime": regime,
        }
        log.info(
            "  %s: ann_fund p50=%.2f%% p99=%.2f%% / ann_rv p50=%.2f%% p99=%.2f%% / ratio p50=%.3f p99=%.3f / regime=%s",
            sym, impl_p50, impl_p99, rv_p50, rv_p99, ratio_p50, ratio_p99, regime,
        )

    log.info("Magnitude regime classification:")
    log.info("  FUNDING_DOMINATES: %s", funding_dominates)
    log.info("  RV_DOMINATES (-> VRP_z ~ -RV_z, paradigm reduces to RV family): %s", rv_dominates)
    log.info("  MIXED_REGIME: %s", mixed)

    # ============================================================
    # Step C: Lesson #54 mechanism coherence verdict (paradigm 200)
    # ============================================================
    log.info("--- Step C: Lesson #54 trap detection verdict ---")
    n_funding = len(funding_dominates)
    n_rv = len(rv_dominates)
    n_mixed = len(mixed)
    n_total = n_funding + n_rv + n_mixed

    # paradigm 200 abs() removes sign asymmetry. So sign_asymmetry_trap auto-resolved.
    sign_asymmetry_trap = False
    sign_asymmetry_note = "AUTO_RESOLVED_BY_ABS_FUNDING_RATE"

    # Family reduction trap: still active.
    family_reduction_ratio = (n_funding + n_rv) / max(n_total, 1)
    family_reduction_trap = family_reduction_ratio >= 0.70

    lesson_54_verdict = {
        "mechanism_story_claim": "VRP = ann_funding_vol - ann_realized_vol (bilateral z spike directional)",
        "abs_funding_resolves_sign_asymmetry": True,
        "sign_asymmetry_trap_triggered": sign_asymmetry_trap,
        "sign_asymmetry_note": sign_asymmetry_note,
        "family_reduction_trap_triggered": family_reduction_trap,
        "family_reduction_ratio": family_reduction_ratio,
        "regime_breakdown": {
            "funding_dominates_n": n_funding,
            "rv_dominates_n": n_rv,
            "mixed_n": n_mixed,
            "total_n": n_total,
        },
        "interpretation": (
            "paradigm 200 abs() RESOLVES sign asymmetry trap (paradigm 135 1st trap closed). "
            f"BUT family-reduction trap depends on per-sym magnitude regime. "
            f"FUNDING dominates {n_funding}/{n_total} ({funding_dominates}); "
            f"RV dominates {n_rv}/{n_total} ({rv_dominates}); "
            f"MIXED {n_mixed}/{n_total} ({mixed}). "
            f"Ratio = {family_reduction_ratio:.2f}, trap_threshold = 0.70."
        ),
        "verdict": (
            "LESSON_54_TRAP_CONFIRMED_FAMILY_REDUCTION"
            if family_reduction_trap
            else "LESSON_54_TRAP_CLEAR_MIXED_REGIME_DOMINANT"
        ),
    }
    log.info("Lesson #54 verdict: %s", lesson_54_verdict["verdict"])
    log.info("  sign_asymmetry_trap: %s (abs() resolves it)", sign_asymmetry_trap)
    log.info("  family_reduction_trap: %s (ratio=%.2f >= 0.70)", family_reduction_trap, family_reduction_ratio)

    # ============================================================
    # Step D: Lesson #44 family-distinct reconciliation
    # ============================================================
    log.info("--- Step D: Lesson #44 family-distinct reconciliation ---")
    funding_family_collision = (family_reduction_trap and n_funding >= 3)
    rv_family_collision = (family_reduction_trap and n_rv >= 3)
    lesson_44_reconciliation = {
        "funding_family_tier_4_retire_collision": funding_family_collision,
        "rv_family_tier_4_retire_collision": rv_family_collision,
        "verdict": (
            "LESSON_44_FAMILY_DISTINCT_FAIL"
            if (funding_family_collision or rv_family_collision)
            else "LESSON_44_FAMILY_DISTINCT_PASS_MIXED_REGIME"
        ),
        "reasoning": (
            f"paradigm 200 abs() formula. Funding dominates {n_funding}/{n_total}, RV dominates {n_rv}/{n_total}, "
            f"MIXED {n_mixed}/{n_total}. Funding family Tier 4 retire 8 paradigms (73/79/96/97/98/99/132/197) "
            f"+ paradigm 22 R-5 exception. RV family paradigm 67-69/118/124/125/129/133/134 graveyarded "
            f"except p69 R-5 seed."
        ),
    }
    log.info("Lesson #44 reconciliation verdict: %s", lesson_44_reconciliation["verdict"])

    # ============================================================
    # Step E: Final R-0 verdict
    # ============================================================
    log.info("--- Step E: Final R-0 verdict ---")
    halt = (
        lesson_54_verdict["verdict"] == "LESSON_54_TRAP_CONFIRMED_FAMILY_REDUCTION"
        or lesson_44_reconciliation["verdict"] == "LESSON_44_FAMILY_DISTINCT_FAIL"
    )
    if halt:
        verdict = "R0_HALT_LESSON_54_FAMILY_REDUCTION_PARADIGM135_REINFORCEMENT"
    else:
        verdict = "R0_READY_FOR_R1_MIXED_REGIME_DOMINANT"

    log.info("=== FINAL R-0 VERDICT: %s ===", verdict)

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "universe_cohort_requested": COHORT,
        "universe_loaded": list(sym_data.keys()),
        "universe_skipped": skipped,
        "params": {
            "funding_annual_scale_to_pct": FUNDING_ANNUAL_SCALE,
            "rv_rolling_days": RV_ROLLING_DAYS,
            "rv_daily_to_annual_sqrt252": RV_DAILY_TO_ANNUAL,
            "z_rolling_days": Z_ROLLING_DAYS,
            "z_threshold_absolute": Z_THRESHOLD,
            "fee_bp": FEE_BP,
        },
        "per_sym_funding_days": funding_days,
        "per_sym_ohlcv_4h_days": ohlcv_days,
        "per_sym_magnitude_audit": per_sym_magnitude_audit,
        "regime_classification": {
            "funding_dominates": funding_dominates,
            "rv_dominates": rv_dominates,
            "mixed_regime": mixed,
        },
        "lesson_61_slug_grep_audit": {
            "duplicate_slug_found": "alt_funding_implied_vs_realized_vol_premium_z_directional_4h",
            "duplicate_slug_paradigm": 135,
            "duplicate_slug_phase": "R-0_HALT",
            "duplicate_slug_verdict": "R0_HALT_LESSON_54_MECHANISM_INCOHERENT_FUNDING_RV_FAMILY_REDUCTION",
            "formula_delta": [
                "paradigm 200 uses abs(funding_rate) -> sign asymmetry trap auto-resolved",
                "paradigm 200 uses daily-frame RV (sqrt(252)*daily_std*100) instead of 1h-frame RV",
                "paradigm 200 uses 90d z-window instead of 30d",
                "paradigm 200 uses bilateral 4-quadrant SNT instead of signed direction",
            ],
            "delta_resolves_paradigm_135_halt": "PARTIAL (sign asym yes, family reduction empirical)",
        },
        "lesson_54_verdict": lesson_54_verdict,
        "lesson_44_reconciliation": lesson_44_reconciliation,
    }
    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-0 saved to %s", out_path)
    if halt:
        sys.exit(2)


if __name__ == "__main__":
    main()
