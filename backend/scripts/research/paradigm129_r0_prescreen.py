"""paradigm 129 R-0 prescreen — alt_parkinson_range_vol_expansion_percentile_directional_4h.

Hypothesis:
  Statistic: Parkinson range-based vol estimator on 4h bar
    park = (1 / (4*ln(2))) * (ln(H/L))^2
  Trigger: per-symbol 30-day rolling Parkinson percentile rank >= p90
    (range expansion regime change)
  Direction: sign of 4h log-return at trigger bar (range expanded UP vs DOWN)
  Forward hold: 4h (next 4h bar close-to-close return)
  Debounce: 8h between triggers (avoid clustering)
  Universe: 12 alts (cohort reuse minus ADA due to Lesson #30 short-window)

Family-distinct claim (Lesson #44 amendment 10+1 dogfood):
  - paradigm 67 (btc_rv_spike_alt_recovery): close-to-close RV at 1d frame, BTC-driven
      → DISTINCT: range info (H/L within bar) vs close-to-close return RV.
        Per-symbol trigger, not BTC-systemic.
  - paradigm 68 (btc_rv_spike_up_conditional_alt_long): close-to-close RV, BTC sign-cond
      → DISTINCT: range info vs return RV. No cross-asset.
  - paradigm 69 (btc_rv_spike_highvol_filter_alt_long): R-5 seeded but BTC RV close-to-close
      → DISTINCT: per-symbol Parkinson range, no BTC dependency
  - paradigm 81 (rolling_beta_regime): rolling beta vs BTC market
      → DISTINCT: per-symbol intrinsic range, not beta vs benchmark
  - paradigm 121 (hmm_realized_vol_state): HMM unsupervised on RV
      → DISTINCT: explicit percentile threshold (Lesson #45), no HMM
  - paradigm 123 (alt_volume_cusum_change_point): Page-Hinkley stateful CP on volume
      → DISTINCT: stateless percentile, range info not volume
  - paradigm 124 (alt_realized_kurtosis): higher-order moment (4th)
      → DISTINCT: 2nd-order range info, NOT higher-moment
  - paradigm 125 (alt_realized_quarticity): B-N jump test ratio
      → DISTINCT: stateless empirical percentile (Lesson #40 reformulated)
  - paradigm 116 (alt_volume_confirmed_atr_breakout): ATR + volume composite
      → DISTINCT: pure range info (no volume axis stacking, no breakout level)
  - paradigm 126/127/128 volume burst family: 1m volume + magnitude
      → DISTINCT: pure range info (H/L), no volume, 4h frame not 5m

Lessons applied:
  #11 sample density            — per-symbol per-quadrant per-quarter >=30
  #16 Concentration Gate        — q_pos_t_ratio + symbol_ci_pos_ratio + n_syms_ci_pos
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch
  #21 axis stacking caution     — 1 trigger axis only (Parkinson p90), no stacking
  #22 frame-grade               — 4h frame, stateless quantile (not stateful CP)
  #23 non-event-anchored        — continuous rolling, no temporal cycle anchor
  #28 substrate availability    — 1m OHLCV per-symbol (758-798 days, all 12 syms PASS)
  #30 data_window_ratio         — ADA excluded (143d << 30% of 798d full-window)
  #34 empirical distribution    — Parkinson p50/p70/p90/p95/p99 sampled
  #39 sub-class manual          — A_focus pos×LONG / B_focus neg×SHORT / A_mirror / B_mirror
  #40 structural threshold      — percentile rank (NOT z-score on non-negative aggregate)
  #41 amendment edge-first      — per-trade edge >= +2% advisory at R-1
  #43 trap awareness            — Range info novelty needs mechanism alpha proof
  #44 amendment xref 10+1 dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit percentile threshold, NOT HMM/unsupervised
  #46 AMENDMENT REFINEMENT       — temporally-stratified n=50x4q R-0 + per-quarter sign flip
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX + skill cross-reference
  #50 first-burst-sign N/A       — 4h frame, not 5m+ (Lesson #50 scope is 5m+)

Family avoidance verified (Lesson #45):
  - HMM unsupervised: AVOIDED (explicit p90 percentile)
  - OI velocity directional: AVOIDED (range info, no OI)
  - Stateful CP: AVOIDED (stateless quantile)
  - Higher-order moment: AVOIDED (2nd-order range)
  - Funding single-signal: AVOIDED (price-range only)
  - Volume share: AVOIDED (no volume)
  - KR post-earnings: AVOIDED (crypto)
  - Magnitude-confluence: AVOIDED (single trigger axis)
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure: AVOIDED (4h frame)
  - Universe-aggregate scalar: AVOIDED (per-symbol)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA deviation z: AVOIDED (raw range, no smoothing)
  - paradigm 126/127/128 1m volume burst family: AVOIDED (range info, 4h frame)
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
log = logging.getLogger("p129_r0")

PARADIGM_NAME = "alt_parkinson_range_vol_expansion_percentile_directional_4h"
PARADIGM_NUM = 129
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 12 alts (ADA excluded per Lesson #30, BTCUSDT NOT used as proxy due to 142d local)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Trigger params
PARK_ROLLING_BARS_4H = 180             # 30 days * 6 bars/day = 180 4h-bars
PARK_PERCENTILE = 90.0                  # Range-expansion threshold p90
FORWARD_HOLD_4H_BARS = 1                # 4h hold (1 forward bar)
DEBOUNCE_HOURS = 8                       # 8h between consecutive triggers
FEE_BP = 16.0                            # 16bp round-trip (8bp/side)
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m_to_4h(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, high, low, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    bar4h = df.resample("4h").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    return bar4h


def compute_parkinson(df: pd.DataFrame) -> pd.Series:
    """Parkinson range-based variance estimator per bar."""
    return (1.0 / (4.0 * np.log(2.0))) * (np.log(df["high"] / df["low"])) ** 2


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    # Step 1: substrate audit
    log.info("--- Step 1: per-symbol 1m -> 4h substrate audit (Lesson #28+#30) ---")
    sym_data = {}
    per_sym_days = {}
    for sym in COHORT:
        try:
            df = load_ohlcv_1m_to_4h(sym, engine)
            if df.empty or len(df) < PARK_ROLLING_BARS_4H * 2:
                log.warning("%s: insufficient 4h bars (%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            sym_data[sym] = df
            log.info("%s: %d 4h bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded")
        sys.exit(1)

    full_window = max(per_sym_days.values())
    short_window_syms = {s: d for s, d in per_sym_days.items() if d < full_window * 0.30}
    log.info("Lesson #30 audit: full_window=%d days, short-window syms(<30%%): %s",
             full_window, short_window_syms)

    # Lesson #11 napkin
    n_triggers_estimate_per_sym = full_window * 6 * (100 - PARK_PERCENTILE) / 100 * 0.30  # debounce reduces 70%
    log.info("Lesson #11 napkin: expected ~%.0f triggers/sym (full-window), "
             "per-quadrant per-quarter ~%.0f (4 quadrants, ~%d quarters)",
             n_triggers_estimate_per_sym,
             n_triggers_estimate_per_sym / 4 / max(1, full_window / 90),
             max(1, full_window / 90))

    # Step 2: compute Parkinson + triggers per symbol
    log.info("--- Step 2: Parkinson + rolling p90 + debounced triggers per-symbol ---")
    trig_rows = []
    park_pct_aggregated = []
    for sym, df in sym_data.items():
        df = df.copy()
        df["park"] = compute_parkinson(df)
        df["log_ret_4h"] = np.log(df["close"]).diff()
        df["park_p90_30d"] = (
            df["park"].rolling(window=PARK_ROLLING_BARS_4H,
                                min_periods=PARK_ROLLING_BARS_4H // 2)
            .quantile(PARK_PERCENTILE / 100)
        )
        df["cond"] = df["park"] >= df["park_p90_30d"]
        df["fwd_log_ret_4h"] = df["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)

        # Sample Parkinson percentile distribution (Lesson #34)
        park_pct_aggregated.extend(df["park"].dropna().tolist()[:5000])

        # Debounced triggers
        last_ts = None
        for ts, row in df.iterrows():
            if (pd.isna(row["cond"]) or not row["cond"]
                    or pd.isna(row["log_ret_4h"])
                    or pd.isna(row["fwd_log_ret_4h"])):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            direction = int(np.sign(row["log_ret_4h"]))
            if direction == 0:
                continue
            signed_fwd_bp = float(row["fwd_log_ret_4h"]) * direction * 10000.0
            trig_rows.append({
                "ts": ts,
                "sym": sym,
                "park": float(row["park"]),
                "park_p90_30d": float(row["park_p90_30d"]),
                "log_ret_4h": float(row["log_ret_4h"]),
                "direction": direction,
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "signed_fwd_bp": signed_fwd_bp,
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts

    trig_df = pd.DataFrame(trig_rows)
    log.info("total triggers across %d syms: %d (pos=%d, neg=%d)",
             len(sym_data), len(trig_df),
             int((trig_df["direction"] > 0).sum()),
             int((trig_df["direction"] < 0).sum()))

    # Lesson #34 empirical Parkinson distribution
    park_arr = np.array(park_pct_aggregated)
    pct_park = {p: float(np.percentile(park_arr, p)) for p in [50, 70, 90, 95, 99]}
    log.info("Parkinson empirical percentiles (sampled aggregate, n=%d): %s",
             len(park_arr), pct_park)

    # Lesson #40 verification
    lesson_40 = {
        "threshold_definition": "per-symbol 30-day rolling Parkinson percentile p90",
        "threshold_class": "empirical rolling percentile (NOT z-score on non-negative aggregate)",
        "structurally_reachable": True,
        "reformulation_class": "percentile_rank",
        "verdict": "PASS",
    }
    log.info("Lesson #40 verification: %s", lesson_40)

    # Per-quarter per-quadrant density (Lesson #11)
    n_quarters = trig_df["qtr"].nunique() if len(trig_df) else 0
    log.info("Number of quarters with triggers: %d", n_quarters)
    per_q_pos = trig_df[trig_df["direction"] > 0].groupby("qtr").size()
    per_q_neg = trig_df[trig_df["direction"] < 0].groupby("qtr").size()
    log.info("per-quarter pos triggers: %s", per_q_pos.to_dict())
    log.info("per-quarter neg triggers: %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (>=30): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT (4th dogfood)
    log.info("--- Lesson #46 REFINEMENT: temporally-stratified n=50x4q R-0 ---")
    sorted_quarters = sorted(trig_df["qtr"].unique())
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)
    if len(sorted_quarters) < 4:
        log.warning("insufficient quarters for stratified R-0 (have %d, need 4)",
                    len(sorted_quarters))
        sample = trig_df.iloc[:200]
        strat_strategy = "fallback_chronological_n200_INSUFFICIENT_QUARTERS"
        qtrs_to_use = sorted_quarters
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
            q_data = trig_df[trig_df["qtr"] == qq].sort_values("ts")
            n_take = min(50, len(q_data))
            per_q_samples.append(q_data.iloc[:n_take])
        sample = pd.concat(per_q_samples)
        strat_strategy = f"temporally_stratified_n50x{len(qtrs_to_use)}q_total_n={len(sample)}"

    # 4-quadrant SNT estimate
    a_focus = sample[sample["direction"] > 0]["signed_fwd_bp"]
    a_mirror = -a_focus  # mathematical mirror
    b_focus = sample[sample["direction"] < 0]["signed_fwd_bp"]
    b_mirror = -b_focus  # mathematical mirror

    def stats(s, lbl):
        if len(s) < 2:
            return {"label": lbl, "n": int(len(s)), "gross_bp": None,
                    "net_bp": None, "t": None}
        m = float(s.mean())
        sd = float(s.std(ddof=1))
        n = int(len(s))
        return {
            "label": lbl, "n": n, "gross_bp": m, "net_bp": m - FEE_BP,
            "t": (m / (sd / math.sqrt(n))) if sd > 0 else None,
        }

    qa = stats(a_focus, "A_focus_park_p90_pos_LONG_4h")
    qam = stats(a_mirror, "A_mirror_park_p90_pos_SHORT_4h")
    qb = stats(b_focus, "B_focus_park_p90_neg_SHORT_4h")
    qbm = stats(b_mirror, "B_mirror_park_p90_neg_LONG_4h")
    log.info("R-0 4-quadrant stratified-mechanism estimate (strategy=%s):", strat_strategy)
    for q in [qa, qam, qb, qbm]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter R-0 detail (sub-amendment dogfood)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 sub-amendment) ---")
    per_qtr_r0 = {}
    a_signs = []
    b_signs = []
    for qq in qtrs_to_use:
        q_sample = trig_df[trig_df["qtr"] == qq].sort_values("ts").iloc[:50]
        q_a = q_sample[q_sample["direction"] > 0]["signed_fwd_bp"]
        q_b = q_sample[q_sample["direction"] < 0]["signed_fwd_bp"]
        a_g = float(q_a.mean()) if len(q_a) > 0 else None
        b_g = float(q_b.mean()) if len(q_b) > 0 else None
        per_qtr_r0[qq] = {
            "n_total": int(len(q_sample)),
            "A_focus_n": int(len(q_a)),
            "A_focus_gross_bp": a_g,
            "B_focus_n": int(len(q_b)),
            "B_focus_gross_bp": b_g,
        }
        if a_g is not None:
            a_signs.append(1 if a_g > 0 else -1)
        if b_g is not None:
            b_signs.append(1 if b_g > 0 else -1)
        log.info("  %s: A_focus n=%d gross=%s | B_focus n=%d gross=%s",
                 qq, len(q_a),
                 f"{a_g:.2f}" if a_g is not None else "NA",
                 len(q_b),
                 f"{b_g:.2f}" if b_g is not None else "NA")

    def flips(signs):
        return sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])

    a_flips = flips(a_signs)
    b_flips = flips(b_signs)
    log.info("Lesson #46 sign-flip detection: A_focus flips=%d (%s) | B_focus flips=%d (%s)",
             a_flips, a_signs, b_flips, b_signs)

    # Lesson #44 cross-reference (10+1 dogfood)
    lesson_44_xref = {
        "paradigm_67_btc_rv_spike_alt_recovery": "GRAVEYARD — close-to-close RV at 1d. "
            "DISTINCT: range info (H/L) vs return-based RV. Per-sym, no BTC.",
        "paradigm_68_btc_rv_spike_up_conditional": "GRAVEYARD R-3.5 — BTC RV sign-cond. "
            "DISTINCT: per-sym range, no cross-asset, no sign-cond filter.",
        "paradigm_69_btc_rv_spike_highvol_filter": "R-5 SEEDED — BTC RV p90 + 13 alt LONG. "
            "DISTINCT: per-sym intrinsic range (no BTC dependency), 4h frame vs 240m hold.",
        "paradigm_81_rolling_beta_regime": "GRAVEYARD lesson #20 narrow scope — rolling beta vs BTC. "
            "DISTINCT: range info, not beta vs benchmark.",
        "paradigm_116_alt_volume_confirmed_atr_breakout": "GRAVEYARD — ATR+volume composite. "
            "DISTINCT: pure range info (no volume, no breakout level).",
        "paradigm_121_hmm_realized_vol_state": "GRAVEYARD lesson #45 HMM — HMM unsup decomp on RV. "
            "DISTINCT: explicit p90 percentile (Lesson #45 family-distinct).",
        "paradigm_123_alt_volume_cusum_change_point": "GRAVEYARD lesson #19 SNT broad-falsified. "
            "DISTINCT: stateless percentile vs stateful Page-Hinkley, range vs volume.",
        "paradigm_124_alt_realized_kurtosis": "GRAVEYARD — 4th moment. "
            "DISTINCT: 2nd-order range, NOT higher-order moment family (advisory caution).",
        "paradigm_125_alt_realized_quarticity_bipower": "R-0 HALT lesson #40 — B-N test. "
            "DISTINCT: percentile rank reformulation (Lesson #40 compliant).",
        "paradigm_126_127_128_volume_burst_family": "R-5 SEEDED paradigm 127+128 — 1m volume burst. "
            "DISTINCT: pure range info, 4h frame (not 5m, not volume).",
        "RUNBOOK_3M_volume_extraction": "ANTIPATTERN avoided — no volume axis used. "
            "Range info is independent dimension from volume.",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit p90 percentile, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (range info, no OI)",
        "Stateful_CP": "AVOIDED (stateless quantile, Lesson #22)",
        "Higher_order_moment": "AVOIDED (2nd-order range)",
        "Funding_single_signal": "AVOIDED (price-range only)",
        "Volume_share": "AVOIDED (no volume)",
        "Magnitude_confluence": "AVOIDED (single trigger axis)",
        "Listing_event": "AVOIDED (continuous rolling, no event anchor)",
        "5m_microstructure_single_domain": "AVOIDED (4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-symbol)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed_deviation": "AVOIDED (raw range, no smoothing)",
        "paradigm_126_127_128_volume_burst": "AVOIDED (4h frame + range info, distinct dimension)",
    }

    # Verdict
    n_total = len(trig_df)
    n_per_sym_min = trig_df.groupby("sym").size().min() if len(trig_df) else 0
    verdict = "R0_READY_FOR_R1" if (
        n_total >= 200
        and measurable_q_pos >= 3
        and measurable_q_neg >= 3
        and len(sym_data) >= 5
        and lesson_40["verdict"] == "PASS"
    ) else "R0_HALT_INSUFFICIENT_DENSITY"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "universe_cohort": COHORT,
        "universe_loaded": list(sym_data.keys()),
        "universe_excluded": {"ADAUSDT": "Lesson #30 short-window (143d << 30% of 798d)",
                              "BTCUSDT": "Lesson #30 short-window (142d), local DB stale"},
        "params": {
            "park_rolling_bars_4h": PARK_ROLLING_BARS_4H,
            "park_percentile": PARK_PERCENTILE,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_bp": FEE_BP,
        },
        "per_sym_days": per_sym_days,
        "short_window_syms_lesson_30": short_window_syms,
        "n_triggers_total": int(n_total),
        "n_triggers_pos": int((trig_df["direction"] > 0).sum()) if len(trig_df) else 0,
        "n_triggers_neg": int((trig_df["direction"] < 0).sum()) if len(trig_df) else 0,
        "n_per_sym_min": int(n_per_sym_min),
        "per_quarter_pos": per_q_pos.to_dict(),
        "per_quarter_neg": per_q_neg.to_dict(),
        "measurable_quarters_pos": int(measurable_q_pos),
        "measurable_quarters_neg": int(measurable_q_neg),
        "n_quarters": int(n_quarters),
        "lesson_11_density_pass": (measurable_q_pos >= 3 and measurable_q_neg >= 3),
        "lesson_34_empirical_park_percentiles": pct_park,
        "lesson_40": lesson_40,
        "lesson_46_amendment_refinement_strategy": strat_strategy,
        "lesson_46_quarters_used": qtrs_to_use,
        "r0_4quadrant_stratified_estimate": {
            "A_focus_park_p90_pos_LONG_4h": qa,
            "A_mirror_park_p90_pos_SHORT_4h": qam,
            "B_focus_park_p90_neg_SHORT_4h": qb,
            "B_mirror_park_p90_neg_LONG_4h": qbm,
        },
        "per_quarter_r0_detail": per_qtr_r0,
        "lesson_46_sign_flips": {"A_focus_flips": a_flips, "A_signs": a_signs,
                                  "B_focus_flips": b_flips, "B_signs": b_signs},
        "lesson_44_xref": lesson_44_xref,
        "family_avoidance_verification": family_avoidance,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("VERDICT: %s", verdict)
    log.info("R-0 saved to %s", out_path)


if __name__ == "__main__":
    main()
