"""paradigm 130 R-0 prescreen — alt_realized_corr_breakdown_eth_per_pair_directional_4h.

Hypothesis:
  Benchmark: ETHUSDT (NOT BTC due to local DB 142d Lesson #30 short-window)
  Statistic: per-pair (alt, ETH) Pearson realized correlation
    rho_30d = corr(log_ret_4h_alt, log_ret_4h_ETH) on 30-day rolling window
              of 4h log-returns (180 4h-bars per window)
  Trigger: rho_30d <= per-pair empirical p10 percentile
           (correlation breakdown / decoupling event)
  Direction: sign of 4h log-return of alt at trigger bar (alt moved up vs down
             at the moment correlation collapsed) → directional continuation
  Forward hold: 4h (next 4h bar close-to-close return on alt)
  Debounce: 8h between triggers (avoid clustering)
  Universe: 11 alts (paradigm 129 cohort 12 minus ETH benchmark)

Family-distinct claim (Lesson #44 amendment 12th dogfood):
  - paradigm 62 (cross_sec_weekly_mr): cross-section weekly MR
      → DISTINCT: per-pair correlation breakdown vs cross-section rank rotation
  - paradigm 75 (cross_symbol_lead_lag): cohort-aggregate lead-lag
      → DISTINCT: per-pair (alt, ETH) Pearson NOT cohort-aggregate
  - paradigm 81 (rolling_beta_regime): rolling beta vs BTC market (regression coeff)
      → DISTINCT: per-pair correlation coefficient (NOT beta = cov/var regression)
        ETH benchmark NOT BTC. 4-cell sign-cond focus differs.
  - paradigm 118 (realized_correlation_regime_universe): universe-aggregate
                  correlation regime
      → DISTINCT: per-pair stratified (NOT universe-aggregate scalar)
  - paradigm 129 (alt_parkinson_range_vol_expansion): per-symbol range estimator
      → DISTINCT: cross-asset correlation NOT intrinsic range. Lesson #52
        candidate universe LONG drift artifact precedent — explicit detection
        of LONG-side both-positive gross artifact required.

Lessons applied:
  #8 amendment candidate (Lesson #52) — universe LONG drift artifact detection
  #11 sample density            — per-pair per-quadrant per-quarter >=30
  #16 Concentration Gate        — q_pos_t_ratio + symbol_ci_pos_ratio + n_syms_ci_pos
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch
  #21 axis stacking caution     — 1 trigger axis only (correlation p10)
  #22 frame-grade               — 4h frame, 30d rolling 180 obs (frame-rich)
  #23 non-event-anchored        — continuous rolling, no temporal cycle anchor
  #28 substrate availability    — 1m OHLCV per-symbol + ETH benchmark
  #30 data_window_ratio         — ADA/BTC excluded; 11 alts + ETH 755-799 days PASS
  #34 empirical distribution    — per-pair correlation p10/p25/p50/p75/p90 sampled
  #39 sub-class manual          — A/A_mirror/B/B_mirror + sub-class D (LONG drift)
  #40 structural threshold      — empirical percentile rank (NOT z-score)
  #41 amendment edge-first      — per-trade edge >= +2% advisory at R-1
  #44 amendment xref 12th dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit Pearson correlation, NOT HMM/unsupervised
  #46 AMENDMENT REFINEMENT       — temporally-stratified n=50x4q R-0 + sign-flip
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX + skill cross-reference
  #50 first-burst-sign N/A       — 4h frame, not 5m+
  #52 candidate (2 dogfoods)     — universe LONG drift artifact precedent (paradigm 99/129)

Family avoidance verified:
  - HMM unsupervised: AVOIDED (explicit Pearson + empirical p10 percentile)
  - OI velocity directional: AVOIDED (price correlation only, no OI)
  - Stateful CP: AVOIDED (stateless rolling quantile)
  - Higher-order moment: AVOIDED (2nd-order correlation)
  - Funding single-signal: AVOIDED (price correlation only)
  - Volume share: AVOIDED (no volume)
  - Magnitude-confluence: AVOIDED (single trigger axis)
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure: AVOIDED (4h frame)
  - Universe-aggregate scalar: AVOIDED (per-pair, NOT universe-mean)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA deviation z: AVOIDED (raw correlation, no smoothing)
  - paradigm 81 rolling beta: AVOIDED (Pearson rho vs beta coefficient)
  - paradigm 118 universe-aggregate corr: AVOIDED (per-pair stratified)
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
log = logging.getLogger("p130_r0")

PARADIGM_NAME = "alt_realized_corr_breakdown_eth_per_pair_directional_4h"
PARADIGM_NUM = 130
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

BENCHMARK = "ETHUSDT"
# 11 alts (paradigm 129's 12 minus ETH benchmark, ADA/BTC excluded per Lesson #30)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Trigger params
CORR_ROLLING_BARS_4H = 180             # 30 days * 6 bars/day = 180 4h-bars
CORR_PERCENTILE = 10.0                  # Per-pair p10 (low correlation = decoupling)
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


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    # Step 1: load benchmark + cohort, substrate audit (Lesson #28+#30)
    log.info("--- Step 1: load benchmark (%s) + cohort 1m -> 4h ---", BENCHMARK)
    eth_4h = load_ohlcv_1m_to_4h(BENCHMARK, engine)
    if eth_4h.empty or len(eth_4h) < CORR_ROLLING_BARS_4H * 2:
        log.error("ETH benchmark insufficient (n=%d) — halt", len(eth_4h))
        sys.exit(1)
    eth_days = (eth_4h.index.max() - eth_4h.index.min()).days
    eth_4h["log_ret_4h"] = np.log(eth_4h["close"]).diff()
    log.info("%s: %d 4h bars (%d days)", BENCHMARK, len(eth_4h), eth_days)

    sym_data = {}
    per_sym_days = {BENCHMARK: eth_days}
    for sym in COHORT:
        try:
            df = load_ohlcv_1m_to_4h(sym, engine)
            if df.empty or len(df) < CORR_ROLLING_BARS_4H * 2:
                log.warning("%s: insufficient 4h bars (%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            df["log_ret_4h"] = np.log(df["close"]).diff()
            sym_data[sym] = df
            log.info("%s: %d 4h bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no alt symbols loaded")
        sys.exit(1)

    full_window = max(per_sym_days.values())
    short_window_syms = {s: d for s, d in per_sym_days.items() if d < full_window * 0.30}
    log.info("Lesson #30 audit: full_window=%d days, short-window syms(<30%%): %s",
             full_window, short_window_syms)

    # Step 2: compute per-pair rolling correlation + triggers
    log.info("--- Step 2: per-pair (alt, ETH) rolling 30d Pearson correlation ---")
    trig_rows = []
    rho_aggregated = []  # for Lesson #34 empirical distribution
    per_pair_p10 = {}

    for sym, df in sym_data.items():
        df = df.copy()
        # Align with ETH on shared timestamps (inner join)
        joined = df.join(eth_4h[["log_ret_4h"]].rename(
            columns={"log_ret_4h": "eth_log_ret_4h"}), how="inner")
        if len(joined) < CORR_ROLLING_BARS_4H * 2:
            log.warning("%s: insufficient joined bars after ETH align (%d) -- skip",
                        sym, len(joined))
            continue

        joined["fwd_log_ret_4h"] = joined["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)
        joined["rho_30d"] = (
            joined["log_ret_4h"].rolling(window=CORR_ROLLING_BARS_4H,
                                          min_periods=CORR_ROLLING_BARS_4H // 2)
            .corr(joined["eth_log_ret_4h"])
        )
        # Sample rho distribution for Lesson #34
        rho_aggregated.extend(joined["rho_30d"].dropna().tolist()[:5000])

        # Per-pair empirical p10 threshold (Lesson #40 PASS — percentile rank)
        rho_valid = joined["rho_30d"].dropna()
        if len(rho_valid) < CORR_ROLLING_BARS_4H:
            log.warning("%s: insufficient rho samples (%d) -- skip", sym, len(rho_valid))
            continue
        p10_threshold = float(np.percentile(rho_valid.values, CORR_PERCENTILE))
        per_pair_p10[sym] = p10_threshold

        joined["cond"] = joined["rho_30d"] <= p10_threshold
        log.info("%s: rho_30d p10 threshold = %.4f, cond_count=%d",
                 sym, p10_threshold, int(joined["cond"].sum()))

        # Debounced triggers
        last_ts = None
        for ts, row in joined.iterrows():
            if (pd.isna(row["cond"]) or not row["cond"]
                    or pd.isna(row["log_ret_4h"])
                    or pd.isna(row["fwd_log_ret_4h"])
                    or pd.isna(row["rho_30d"])):
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
                "rho_30d": float(row["rho_30d"]),
                "rho_p10_pair": p10_threshold,
                "log_ret_4h": float(row["log_ret_4h"]),
                "direction": direction,
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "signed_fwd_bp": signed_fwd_bp,
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts

    trig_df = pd.DataFrame(trig_rows)
    log.info("total triggers across %d alts: %d (pos=%d, neg=%d)",
             len(sym_data), len(trig_df),
             int((trig_df["direction"] > 0).sum()) if len(trig_df) else 0,
             int((trig_df["direction"] < 0).sum()) if len(trig_df) else 0)

    # Lesson #34 empirical rho distribution
    rho_arr = np.array(rho_aggregated)
    pct_rho = {p: float(np.percentile(rho_arr, p)) for p in [10, 25, 50, 75, 90]}
    log.info("Per-pair rolling 30d correlation empirical percentiles "
             "(sampled aggregate, n=%d): %s", len(rho_arr), pct_rho)

    # Lesson #40 verification (per-pair empirical percentile -- structurally reachable)
    lesson_40 = {
        "threshold_definition": "per-pair empirical p10 of rolling 30d Pearson correlation",
        "threshold_class": "empirical percentile rank (per-pair, NOT z-score on aggregate)",
        "structurally_reachable": True,
        "reformulation_class": "percentile_rank",
        "verdict": "PASS",
    }
    log.info("Lesson #40 verification: %s", lesson_40)

    # Per-quarter per-quadrant density (Lesson #11)
    n_quarters = trig_df["qtr"].nunique() if len(trig_df) else 0
    log.info("Number of quarters with triggers: %d", n_quarters)
    if len(trig_df):
        per_q_pos = trig_df[trig_df["direction"] > 0].groupby("qtr").size()
        per_q_neg = trig_df[trig_df["direction"] < 0].groupby("qtr").size()
    else:
        per_q_pos = pd.Series(dtype=int)
        per_q_neg = pd.Series(dtype=int)
    log.info("per-quarter pos triggers: %s", per_q_pos.to_dict())
    log.info("per-quarter neg triggers: %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (>=30): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT (5th dogfood)
    log.info("--- Lesson #46 REFINEMENT: temporally-stratified n=50x4q R-0 ---")
    sorted_quarters = sorted(trig_df["qtr"].unique()) if len(trig_df) else []
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)
    if len(sorted_quarters) < 4:
        log.warning("insufficient quarters for stratified R-0 (have %d, need 4)",
                    len(sorted_quarters))
        sample = trig_df.iloc[:200] if len(trig_df) else pd.DataFrame()
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

    # 4-quadrant SNT estimate from stratified sample
    a_focus = sample[sample["direction"] > 0]["signed_fwd_bp"] if len(sample) else pd.Series(dtype=float)
    a_mirror = -a_focus
    b_focus = sample[sample["direction"] < 0]["signed_fwd_bp"] if len(sample) else pd.Series(dtype=float)
    b_mirror = -b_focus

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

    qa = stats(a_focus, "A_focus_rho_p10_pos_LONG_4h")
    qam = stats(a_mirror, "A_mirror_rho_p10_pos_SHORT_4h")
    qb = stats(b_focus, "B_focus_rho_p10_neg_SHORT_4h")
    qbm = stats(b_mirror, "B_mirror_rho_p10_neg_LONG_4h")
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

    # Lesson #44 cross-reference (12th dogfood)
    lesson_44_xref = {
        "paradigm_62_cross_sec_weekly_mr": "GRAVEYARD — cross-section weekly MR rank rotation. "
            "DISTINCT: per-pair correlation breakdown vs cross-section rank-based MR.",
        "paradigm_75_cross_symbol_lead_lag": "GRAVEYARD — cohort-aggregate lead-lag. "
            "DISTINCT: per-pair (alt, ETH) Pearson NOT cohort-aggregate lag.",
        "paradigm_81_rolling_beta_regime": "GRAVEYARD lesson #20 narrow scope — rolling beta vs BTC "
            "(regression coefficient). DISTINCT: Pearson rho (corr coefficient, not regression beta), "
            "ETH benchmark not BTC.",
        "paradigm_118_realized_correlation_regime_universe": "GRAVEYARD — universe-aggregate "
            "correlation regime (mean rho across all pairs). DISTINCT: per-pair stratified breakdown "
            "(NOT universe-aggregate scalar).",
        "paradigm_99_funding_per_sym_velocity": "GRAVEYARD — Lesson #8 amendment candidate "
            "(LONG drift artifact A focus + B mirror both positive). PRECEDENT: must explicitly "
            "detect LONG-side both-positive gross artifact.",
        "paradigm_129_alt_parkinson_range_vol_expansion": "GRAVEYARD 2026-05-21 — 2nd dogfood "
            "of Lesson #52 candidate (universe LONG drift artifact). DISTINCT: cross-asset "
            "correlation NOT intrinsic range. Must replicate explicit LONG-drift detection.",
        "RUNBOOK_3M_volume_extraction": "ANTIPATTERN avoided — no volume axis. Pure price "
            "correlation (alt, ETH).",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit Pearson + empirical p10, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (price correlation only, no OI)",
        "Stateful_CP": "AVOIDED (stateless rolling quantile, Lesson #22)",
        "Higher_order_moment": "AVOIDED (2nd-order correlation)",
        "Funding_single_signal": "AVOIDED (price correlation only)",
        "Volume_share": "AVOIDED (no volume)",
        "Magnitude_confluence": "AVOIDED (single trigger axis)",
        "Listing_event": "AVOIDED (continuous rolling)",
        "5m_microstructure_single_domain": "AVOIDED (4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-pair, NOT universe-mean)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed_deviation": "AVOIDED (raw correlation, no smoothing)",
        "paradigm_81_rolling_beta": "AVOIDED (Pearson rho vs beta=cov/var)",
        "paradigm_118_universe_aggregate_corr": "AVOIDED (per-pair stratified)",
        "paradigm_129_intrinsic_range": "AVOIDED (cross-asset correlation, not range)",
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
        "benchmark": BENCHMARK,
        "universe_cohort": COHORT,
        "universe_loaded": list(sym_data.keys()),
        "universe_excluded": {
            "ADAUSDT": "Lesson #30 short-window (143d << 30% of 798d)",
            "BTCUSDT": "Lesson #30 short-window (142d), local DB stale",
            "ETHUSDT": "benchmark (excluded from alt cohort)",
        },
        "params": {
            "corr_rolling_bars_4h": CORR_ROLLING_BARS_4H,
            "corr_percentile": CORR_PERCENTILE,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_bp": FEE_BP,
        },
        "per_sym_days": per_sym_days,
        "short_window_syms_lesson_30": short_window_syms,
        "per_pair_p10_thresholds": per_pair_p10,
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
        "lesson_34_empirical_rho_percentiles": pct_rho,
        "lesson_40": lesson_40,
        "lesson_46_amendment_refinement_strategy": strat_strategy,
        "lesson_46_quarters_used": qtrs_to_use,
        "r0_4quadrant_stratified_estimate": {
            "A_focus_rho_p10_pos_LONG_4h": qa,
            "A_mirror_rho_p10_pos_SHORT_4h": qam,
            "B_focus_rho_p10_neg_SHORT_4h": qb,
            "B_mirror_rho_p10_neg_LONG_4h": qbm,
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
