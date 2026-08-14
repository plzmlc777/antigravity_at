"""paradigm 133 R-0 prescreen — alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h.

Hypothesis (NEW statistic class — 2nd-order realized volatility):
  Statistic class: realized vol-of-vol (std of std), 2nd-order vol clustering
    Step 1: per-symbol 1h RV = sqrt(sum of squared 5m log-returns within 1h, ann.scale-free)
            = sqrt(sum over 12 bars of (log(c_t / c_{t-5m}))^2)
    Step 2: 24h rolling RV-of-RV = std(prior 24 hourly RV values)
    Step 3: per-symbol 30d rolling z-score of RV-of-RV
  Trigger: RV-of-RV z > +2 (volatility clustering regime change imminent)
  Direction: sign(4h log-return at trigger 4h-bar) — regime change carries directional info
  Forward hold: 4h (next 4h bar close-to-close return)
  Debounce: 8h between consecutive triggers per-symbol
  Universe: 12 alts (cohort reuse minus ADA per Lesson #30)

Family-distinct claim (Lesson #44 amendment 16th dogfood):
  - paradigm 67/68 (btc_rv_spike_alt_recovery/cond): 1d close-to-close RV, BTC-driven
      → DISTINCT: 2nd-order (std of RV) NOT 1st-order RV, per-symbol NOT BTC-driven, 1h NOT 1d.
  - paradigm 69 (btc_rv_spike_highvol_filter_alt_long): R-5 SEEDED, BTC RV close-to-close
      → DISTINCT: 2nd-order per-symbol vol-of-vol (NOT BTC RV level, NOT close-to-close return RV).
  - paradigm 81 (rolling_beta_regime): rolling beta vs BTC
      → DISTINCT: 2nd-order intrinsic vol clustering, no benchmark beta.
  - paradigm 84 (book_depth_cusum): Page-Hinkley stateful CP on book depth
      → DISTINCT: 2nd-order vol-of-vol stateless z, NOT stateful CP, NOT book depth.
  - paradigm 118 (realized_correlation_regime universe): universe-aggregate realized corr matrix
      → DISTINCT: per-symbol 2nd-order vol-of-vol, NOT cross-correlation, NOT universe aggregate.
  - paradigm 121 (hmm_realized_vol_state): HMM unsupervised on RV
      → DISTINCT: explicit z-threshold (Lesson #45), NOT HMM, 2nd-order NOT 1st-order RV.
  - paradigm 123 (alt_volume_cusum): Page-Hinkley CP on volume
      → DISTINCT: stateless z, vol-of-vol stat NOT volume.
  - paradigm 124 (alt_realized_kurtosis_x_skewness): 4th moment × 3rd moment joint
      → DISTINCT: 2nd-order temporal clustering (std of std), NOT higher-order moment.
  - paradigm 125 (alt_realized_quarticity_bipower): B-N test ratio, R-0 halt Lesson #40
      → DISTINCT: percentile-rank reformulation applied (z on raw stat checked Lesson #40).
  - paradigm 129 (alt_parkinson_range_vol_expansion): Parkinson range estimator (1st-order)
      → DISTINCT: 2nd-order temporal clustering of RV, NOT intra-bar range.
  - paradigm 130 (alt_atr_normalized_range_breakout): ATR + range breakout composite
      → DISTINCT: pure 2nd-order vol stat, NOT range breakout level, NOT ATR composite.
  - paradigm 131 (alt_volume_burst_intra5m_signed): 5m volume burst directional
      → DISTINCT: 4h frame + vol-of-vol stat, NOT 5m volume burst.
  - paradigm 132 (funding × OI × magnitude triple confirm): 3-way axis stacking
      → DISTINCT: single trigger axis (Lesson #21 avoidance), NOT funding/OI joint.

NOTE on Lesson #40 (structural threshold attainability):
  RV-of-RV = std of 24 hourly RVs is a non-negative aggregate.
  Symmetric z<-2 trigger would be structurally infeasible (CLAMPED, see paradigm 109+110).
  RESOLUTION: We only use z > +2 (one-sided). No symmetric negative threshold.
  z > +2 is empirically attainable when RV-of-RV spikes (vol regime shift),
  which IS the mechanism we want to detect.
  R-0 will measure empirical RV-of-RV z distribution to verify z>2 reachable.

Lessons applied:
  #11 sample density            — per-symbol per-quadrant per-quarter >=30
  #16 Concentration Gate        — deferred to R-1
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch
  #21 axis stacking avoidance   — single statistic axis (vol-of-vol), NO conjunction
  #22 frame-grade               — 1h base + 24h rolling RV-of-RV (24 obs/window),
                                  30d z-score (720 obs), 4h hold; stateless quantile
  #23 non-event-anchored        — continuous rolling, no temporal cycle anchor
  #28 substrate availability    — 1m OHLCV per-symbol → 5m aggregation → 1h RV
  #30 data_window_ratio         — ADA excluded (143d << 30%); other 12 syms 750+d PASS
  #34 empirical distribution    — RV-of-RV p50/p70/p90/p99/max sampled
  #39 sub-class detection       — A_focus pos×LONG / B_focus neg×SHORT / A_mirror / B_mirror
  #40 structural threshold       — z > +2 one-sided only (non-negative stat); empirical
                                   z.max() must reach +2 (R-0 verifies)
  #41 amendment dual-mode       — per-trade edge >= +2% advisory at R-1
  #43 trap awareness            — 2nd-order novelty needs mechanism alpha proof
  #44 amendment xref 16th dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit z-threshold (NOT HMM unsupervised)
  #46 AMENDMENT REFINEMENT       — temporally-stratified n=50x4q R-0 + per-quarter sign flip
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX + skill cross-reference
  #50 first-burst-sign N/A       — 4h frame (not 5m+)
  #52 a/b detection (candidate)  — both LONG quadrants positive + 0 syms ci_pos universal
                                   pattern detection at R-1
  #53 candidate detection (NEW) — hypothesis dir vs mirror dir comparison at R-1

Family avoidance verified (Lesson #45):
  - HMM unsupervised: AVOIDED (explicit z-threshold on RV-of-RV)
  - OI velocity directional: AVOIDED (price-based vol stat)
  - Stateful CP: AVOIDED (stateless rolling z)
  - Higher-order moment (kurtosis/skewness): AVOIDED (2nd-order temporal clustering)
  - Funding single-signal: AVOIDED (no funding)
  - Volume share: AVOIDED (no volume)
  - Magnitude-confluence: AVOIDED (single trigger axis)
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure single-domain: AVOIDED (1h base / 4h hold)
  - Universe-aggregate scalar: AVOIDED (per-symbol)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA smoothed deviation: AVOIDED (RV-based, no smoothing)
  - paradigm 126/127/128 1m volume burst family: AVOIDED (4h frame + 2nd-order vol stat)
  - Realized correlation matrix family (paradigm 118): AVOIDED (per-sym, no cross-corr)
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
log = logging.getLogger("p133_r0")

PARADIGM_NAME = "alt_realized_vol_of_vol_2nd_order_clustering_regime_directional_4h"
PARADIGM_NUM = 133
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 12 alts (ADA excluded per Lesson #30 short-window)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Trigger params
RV_WINDOW_5M_PER_1H = 12         # 12 × 5m bars per 1h for 1st-order RV
RVOV_ROLLING_HOURS = 24           # 24h rolling std-of-RV for vol-of-vol
ZSCORE_ROLLING_HOURS = 30 * 24    # 30 days × 24h = 720 hours for z-score baseline
Z_THRESHOLD = 2.0                  # z > +2 (one-sided, non-neg stat → Lesson #40)
FORWARD_HOLD_4H_BARS = 1           # 4h forward hold
DEBOUNCE_HOURS = 8                 # 8h between consecutive triggers per-symbol
FEE_BP = 16.0                      # 16bp round-trip
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"


def load_ohlcv_1m(sym: str, engine) -> pd.DataFrame:
    """Load 1m OHLCV, return as DataFrame with timestamp index."""
    q = text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    return df


def compute_rv_1h(df_1m: pd.DataFrame) -> pd.Series:
    """1h Realized Volatility = sqrt(sum of (log return per 5m)^2 within 1h).

    Aggregate 1m → 5m close → 5m log returns → group into 1h bins → RV.
    """
    # 5m close
    close_5m = df_1m["close"].resample("5min").last().dropna()
    # 5m log returns
    log_ret_5m = np.log(close_5m / close_5m.shift(1))
    # Square
    sq_ret_5m = log_ret_5m ** 2
    # Sum into 1h bins (12 obs per 1h)
    sum_sq_1h = sq_ret_5m.resample("1h").sum(min_count=8)  # require >= 8 of 12 5m bars
    # RV
    rv_1h = np.sqrt(sum_sq_1h)
    return rv_1h.dropna()


def compute_rvov_z(rv_1h: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Compute 24h rolling RV-of-RV and 30d rolling z-score."""
    # 24h rolling std of RV (vol-of-vol)
    rvov = rv_1h.rolling(window=RVOV_ROLLING_HOURS, min_periods=18).std()
    # 30d rolling z-score (mean + std over prior 720 hours)
    rvov_mean = rvov.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    rvov_std = rvov.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    z = (rvov - rvov_mean) / rvov_std
    return rvov, z


def aggregate_to_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """4h bar OHLC with close."""
    bar4h = df_1m["close"].resample("4h").last().dropna().to_frame("close")
    bar4h["log_ret_4h"] = np.log(bar4h["close"]).diff()
    return bar4h


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    log.info("--- Step 1: per-symbol 1m → 1h RV → 24h vol-of-vol → 30d z ---")
    sym_data = {}
    per_sym_days = {}
    rvov_z_aggregate = []
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < 30 * 24 * 60 * 2:  # need at least 60d 1m bars
                log.warning("%s: insufficient 1m data (n=%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days

            rv_1h = compute_rv_1h(df)
            if len(rv_1h) < ZSCORE_ROLLING_HOURS + RVOV_ROLLING_HOURS:
                log.warning("%s: insufficient 1h RV (n=%d) -- skip", sym, len(rv_1h))
                continue

            rvov, z = compute_rvov_z(rv_1h)
            bar4h = aggregate_to_4h(df)

            # Sample z empirical distribution
            z_finite = z.dropna().values
            rvov_z_aggregate.extend(z_finite.tolist()[:5000])

            sym_data[sym] = {
                "df_1m": df,
                "rv_1h": rv_1h,
                "rvov": rvov,
                "z": z,
                "bar4h": bar4h,
            }
            log.info("%s: %d days, %d 1h RV, %d 4h bars, z range [%.2f, %.2f] valid=%d",
                     sym, days, len(rv_1h), len(bar4h),
                     float(np.nanmin(z_finite)) if len(z_finite) else float("nan"),
                     float(np.nanmax(z_finite)) if len(z_finite) else float("nan"),
                     len(z_finite))
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    engine.dispose()

    if not sym_data:
        log.error("no symbols loaded")
        sys.exit(1)

    full_window = max(per_sym_days.values())
    short_window_syms = {s: d for s, d in per_sym_days.items() if d < full_window * 0.30}
    log.info("Lesson #30 audit: full_window=%d days, short-window syms(<30%%): %s",
             full_window, short_window_syms)

    # Lesson #34 empirical RV-of-RV z distribution
    z_arr = np.array(rvov_z_aggregate)
    z_arr_finite = z_arr[np.isfinite(z_arr)]
    pct_z = {p: float(np.percentile(z_arr_finite, p))
             for p in [1, 5, 10, 50, 70, 90, 95, 99]}
    z_max = float(np.max(z_arr_finite)) if len(z_arr_finite) else float("nan")
    z_min = float(np.min(z_arr_finite)) if len(z_arr_finite) else float("nan")
    log.info("RV-of-RV z empirical percentiles (n=%d): %s", len(z_arr_finite), pct_z)
    log.info("RV-of-RV z min=%.2f max=%.2f", z_min, z_max)

    # Lesson #40 structural threshold verification
    z_max_reachable = z_max >= Z_THRESHOLD
    n_z_above_thresh = int((z_arr_finite > Z_THRESHOLD).sum())
    pct_above_thresh = n_z_above_thresh / len(z_arr_finite) if len(z_arr_finite) else 0.0
    lesson_40 = {
        "threshold_definition": f"z > +{Z_THRESHOLD} on per-symbol 30d-rolling z of "
                                f"24h-rolling RV-of-RV",
        "stat_class": "non_negative_aggregate_std_of_std",
        "symmetric_negative_use": False,
        "reformulation": "one_sided_z_only_no_negative_threshold_attempted",
        "empirical_z_max": z_max,
        "z_max_reachable": z_max_reachable,
        "n_above_threshold": n_z_above_thresh,
        "pct_above_threshold": pct_above_thresh,
        "verdict": "PASS" if z_max_reachable else "FAIL_STRUCTURAL_THRESHOLD_INFEASIBLE",
    }
    log.info("Lesson #40 verification: %s", lesson_40)

    if not z_max_reachable:
        log.error("z threshold structurally infeasible — HALT")
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps({
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "verdict": "R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBLE",
            "lesson_40": lesson_40,
        }, indent=2, default=str))
        sys.exit(2)

    # Step 2: build triggers per-symbol (debounced) + 4h direction + fwd_4h
    log.info("--- Step 2: build triggers (z > +%.1f, debounce %dh, fwd 4h) ---",
             Z_THRESHOLD, DEBOUNCE_HOURS)
    trig_rows = []
    for sym, d in sym_data.items():
        z = d["z"]
        bar4h = d["bar4h"]

        # Map z (1h freq) onto 4h grid: for each 4h close, take the z value at the 4h close hour
        # (i.e., max z within the prior 4h, or value at the 4h boundary)
        # Use: z resampled to 4h via max (regime signal)
        z_4h = z.resample("4h").max().dropna()
        # Align with bar4h
        z_4h_aligned = z_4h.reindex(bar4h.index, method="ffill")
        bar4h = bar4h.copy()
        bar4h["z_rvov"] = z_4h_aligned
        bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)

        # Trigger: z > Z_THRESHOLD + valid direction + valid fwd
        last_ts = None
        for ts, row in bar4h.iterrows():
            if (pd.isna(row["z_rvov"]) or row["z_rvov"] <= Z_THRESHOLD
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
                "z_rvov": float(row["z_rvov"]),
                "log_ret_4h": float(row["log_ret_4h"]),
                "direction": direction,
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "signed_fwd_bp": signed_fwd_bp,
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts

    trig_df = pd.DataFrame(trig_rows)
    if trig_df.empty:
        log.error("zero triggers — abort")
        sys.exit(1)
    log.info("total triggers across %d syms: %d (pos=%d, neg=%d)",
             len(sym_data), len(trig_df),
             int((trig_df["direction"] > 0).sum()),
             int((trig_df["direction"] < 0).sum()))

    # Per-quarter density (Lesson #11)
    n_quarters = trig_df["qtr"].nunique()
    per_q_pos = trig_df[trig_df["direction"] > 0].groupby("qtr").size()
    per_q_neg = trig_df[trig_df["direction"] < 0].groupby("qtr").size()
    log.info("per-quarter pos: %s", per_q_pos.to_dict())
    log.info("per-quarter neg: %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (>=30): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT
    log.info("--- Lesson #46 REFINEMENT: temporally-stratified n=50x4q R-0 ---")
    sorted_quarters = sorted(trig_df["qtr"].unique())
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)
    if len(sorted_quarters) < 4:
        log.warning("insufficient quarters for stratified R-0 (have %d, need 4)",
                    len(sorted_quarters))
        sample = trig_df.iloc[:200]
        strat_strategy = f"fallback_chronological_n200_have{len(sorted_quarters)}q"
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

    # 4-quadrant estimate
    a_focus = sample[sample["direction"] > 0]["signed_fwd_bp"]
    a_mirror = -a_focus
    b_focus = sample[sample["direction"] < 0]["signed_fwd_bp"]
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

    qa = stats(a_focus, "A_focus_z2_pos_LONG_4h")
    qam = stats(a_mirror, "A_mirror_z2_pos_SHORT_4h")
    qb = stats(b_focus, "B_focus_z2_neg_SHORT_4h")
    qbm = stats(b_mirror, "B_mirror_z2_neg_LONG_4h")
    log.info("R-0 4-quadrant stratified estimate (strategy=%s):", strat_strategy)
    for q in [qa, qam, qb, qbm]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter sign-flip detection (Lesson #46 sub-amendment)
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

    # Lesson #44 cross-reference (16th dogfood)
    lesson_44_xref = {
        "paradigm_67_btc_rv_spike_alt_recovery":
            "GRAVEYARD — 1d close-to-close RV BTC-driven. DISTINCT: 2nd-order per-sym vol-of-vol, NOT 1st-order RV.",
        "paradigm_68_btc_rv_spike_up_conditional":
            "GRAVEYARD R-3.5 — BTC RV sign-cond. DISTINCT: 2nd-order per-sym, no BTC dep, no sign-cond filter.",
        "paradigm_69_btc_rv_spike_highvol_filter":
            "R-5 SEEDED — BTC RV p90 LONG. DISTINCT: per-sym 2nd-order vol-of-vol (NOT BTC RV level), 4h NOT 240m.",
        "paradigm_81_rolling_beta_regime":
            "GRAVEYARD — rolling beta vs BTC. DISTINCT: intrinsic 2nd-order vol clustering, no beta.",
        "paradigm_84_book_depth_cusum":
            "SAMPLE_INSUFFICIENT — Page-Hinkley stateful CP. DISTINCT: stateless z, RV-based NOT book depth.",
        "paradigm_118_realized_correlation_regime":
            "GRAVEYARD — universe-aggregate corr matrix. DISTINCT: per-sym 2nd-order, NOT cross-corr/universe.",
        "paradigm_121_hmm_realized_vol_state":
            "GRAVEYARD Lesson #45 — HMM unsup decomp on RV. DISTINCT: explicit z-threshold (Lesson #45 compliant), 2nd-order NOT 1st-order.",
        "paradigm_123_alt_volume_cusum_change_point":
            "GRAVEYARD Lesson #19 SNT — stateful CP on volume. DISTINCT: stateless z, RV-based NOT volume.",
        "paradigm_124_alt_realized_kurtosis_skewness":
            "GRAVEYARD — higher-order moment joint. DISTINCT: 2nd-order temporal clustering (std of std), NOT higher-order moment.",
        "paradigm_125_alt_realized_quarticity_bipower":
            "R-0 HALT Lesson #40 — B-N test ratio. DISTINCT: 2nd-order vol-of-vol stat (Lesson #40 verified one-sided z + reachable).",
        "paradigm_129_alt_parkinson_range":
            "GRAVEYARD — Parkinson 1st-order range. DISTINCT: 2nd-order temporal clustering of RV, NOT intra-bar range.",
        "paradigm_130_alt_atr_normalized_range_breakout":
            "GRAVEYARD — ATR + breakout level composite. DISTINCT: pure 2nd-order vol stat, NOT range breakout/ATR.",
        "paradigm_131_alt_volume_burst_intra5m_signed":
            "GRAVEYARD — 5m volume burst directional. DISTINCT: 4h frame + 2nd-order vol stat (NOT 5m, NOT volume).",
        "paradigm_132_funding_oi_magnitude_triple":
            "GRAVEYARD Lesson #21 — 3-way axis stacking. DISTINCT: single trigger axis (Lesson #21 compliant).",
        "paradigm_126_127_128_volume_burst_family":
            "R-5 SEEDED 127+128 — 1m volume burst. DISTINCT: 4h frame + 2nd-order vol stat, NOT 1m volume.",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit z-threshold on RV-of-RV, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (price-based vol stat, no OI)",
        "Stateful_CP_Page_Hinkley": "AVOIDED (stateless rolling z, Lesson #22)",
        "Higher_order_moment_kurtosis_skewness": "AVOIDED (2nd-order temporal clustering, NOT 3rd/4th moment)",
        "Funding_single_signal": "AVOIDED (no funding)",
        "Volume_share": "AVOIDED (no volume)",
        "Magnitude_confluence": "AVOIDED (single trigger axis, Lesson #21)",
        "Listing_event": "AVOIDED (continuous rolling)",
        "5m_microstructure_single_domain": "AVOIDED (1h base + 4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-symbol)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed_deviation": "AVOIDED (RV-based, no smoothing)",
        "paradigm_118_realized_corr_matrix": "AVOIDED (per-sym 2nd-order, NOT cross-corr)",
        "paradigm_129_Parkinson_range": "AVOIDED (2nd-order temporal clustering, NOT intra-bar range)",
        "Funding_family_3way_stack": "AVOIDED (single axis, NOT joint conjunction)",
    }

    # Verdict
    n_total = len(trig_df)
    n_per_sym_min = int(trig_df.groupby("sym").size().min()) if len(trig_df) else 0
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
        "universe_excluded": {"ADAUSDT": "Lesson #30 short-window (143d << 30%)"},
        "params": {
            "rv_window_5m_per_1h": RV_WINDOW_5M_PER_1H,
            "rvov_rolling_hours": RVOV_ROLLING_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold": Z_THRESHOLD,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_bp": FEE_BP,
        },
        "per_sym_days": per_sym_days,
        "short_window_syms_lesson_30": short_window_syms,
        "n_triggers_total": int(n_total),
        "n_triggers_pos": int((trig_df["direction"] > 0).sum()),
        "n_triggers_neg": int((trig_df["direction"] < 0).sum()),
        "n_per_sym_min": n_per_sym_min,
        "per_quarter_pos": per_q_pos.to_dict(),
        "per_quarter_neg": per_q_neg.to_dict(),
        "measurable_quarters_pos": int(measurable_q_pos),
        "measurable_quarters_neg": int(measurable_q_neg),
        "n_quarters": int(n_quarters),
        "lesson_11_density_pass": (measurable_q_pos >= 3 and measurable_q_neg >= 3),
        "lesson_34_empirical_z_percentiles": pct_z,
        "lesson_34_z_min": z_min,
        "lesson_34_z_max": z_max,
        "lesson_40": lesson_40,
        "lesson_46_amendment_refinement_strategy": strat_strategy,
        "lesson_46_quarters_used": qtrs_to_use,
        "r0_4quadrant_stratified_estimate": {
            "A_focus_z2_pos_LONG_4h": qa,
            "A_mirror_z2_pos_SHORT_4h": qam,
            "B_focus_z2_neg_SHORT_4h": qb,
            "B_mirror_z2_neg_LONG_4h": qbm,
        },
        "per_quarter_r0_detail": per_qtr_r0,
        "lesson_46_sign_flips": {"A_focus_flips": a_flips, "A_signs": a_signs,
                                 "B_focus_flips": b_flips, "B_signs": b_signs},
        "lesson_44_xref_16th_dogfood": lesson_44_xref,
        "family_avoidance_verification": family_avoidance,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("VERDICT: %s", verdict)
    log.info("R-0 saved to %s", out_path)


if __name__ == "__main__":
    main()
