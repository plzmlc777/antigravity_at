"""paradigm 134 R-0 prescreen — alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h.

Hypothesis (NEW asymmetric statistic class — Patton & Sheppard 2015):
  Realized semivariance asymmetry (RV_up / RV_down ratio)
    Step 1: per-symbol 5m log returns r_t = log(c_t / c_{t-5m})
    Step 2: 1h RV_up = sum over 12 5m bars of r_t^2 where r_t > 0
                       (positive semivariance, upside vol component)
    Step 3: 1h RV_down = sum over 12 5m bars of r_t^2 where r_t < 0
                         (negative semivariance, downside vol component)
    Step 4: 24h rolling RV_up_24h = sum(prior 24 hourly RV_up)
            24h rolling RV_down_24h = sum(prior 24 hourly RV_down)
    Step 5: ratio_t = RV_up_24h / RV_down_24h
            (smoothed by adding small epsilon if RV_down near zero)
    Step 6: per-symbol 30d rolling z-score of log(ratio)
            (log to symmetrize, makes z<-2 attainable for down-dominant regime)
  Trigger: |log_ratio_z| > 2 (asymmetric volatility regime)
  Direction: sign(log_ratio_z) carries DIRECTIONAL info
    - log_ratio_z > +2 (RV_up >> RV_down, up-vol dominant) -> LONG (upside momentum continuation)
    - log_ratio_z < -2 (RV_down >> RV_up, down-vol dominant) -> SHORT (downside momentum continuation)
  Forward hold: 4h
  Debounce: 8h
  Universe: 12 alts (cohort reuse minus ADA per Lesson #30)

CRITICAL distinction from paradigm 133:
  paradigm 133 vol-of-vol: magnitude-only (std of std), direction info SEPARATE
                            (had to use trigger-bar sign as proxy -> noisy)
  paradigm 134 semivariance asymmetry: log_ratio z SIGN itself carries direction
                                        (asymmetric structure naturally encodes direction)
  This is the key Patton-Sheppard insight: signed decomposition of RV.

Family-distinct claim (Lesson #44 amendment 17th dogfood):
  - paradigm 65/66 (skewness MR / momentum): 3rd moment cross-sec
      -> DISTINCT: semivariance RATIO (NOT 3rd central moment), per-sym NOT cross-sec.
  - paradigm 67/68/69 (BTC RV close-to-close): 1d total RV, BTC-driven
      -> DISTINCT: up/down signed decomposition (NOT total RV), per-sym NOT BTC.
  - paradigm 81 (rolling beta regime): rolling beta vs BTC
      -> DISTINCT: intrinsic semivariance asymmetry, no benchmark beta.
  - paradigm 84 (book_depth_cusum): Page-Hinkley CP
      -> DISTINCT: stateless ratio z, RV-based.
  - paradigm 118 (realized_correlation_regime): universe-aggregate corr
      -> DISTINCT: per-sym semivariance ratio, NOT cross-sym corr.
  - paradigm 121 (hmm_realized_vol_state): HMM unsup on RV
      -> DISTINCT: explicit z on signed ratio (Lesson #45 compliant), NOT HMM.
  - paradigm 124 (kurtosis × skewness joint): 3rd × 4th moment
      -> DISTINCT: 2nd-order signed decomposition (RV_up vs RV_down),
                   NOT higher-order moment. Asymmetric statistic class NEW.
  - paradigm 125 (quarticity bipower): B-N test ratio
      -> DISTINCT: semivariance ratio is signed direction-carrying, NOT jump test.
  - paradigm 129 (Parkinson range): high-low range estimator
      -> DISTINCT: signed up/down decomposition of return-based vol,
                   NOT high-low range (which loses sign info).
  - paradigm 130 (ATR breakout): ATR + range breakout level
      -> DISTINCT: pure semivariance ratio stat, NOT breakout level/ATR.
  - paradigm 131 (5m volume burst): volume directional
      -> DISTINCT: 1h base + 4h hold, return-based NOT volume.
  - paradigm 132 (funding × OI × magnitude): 3-way axis stacking
      -> DISTINCT: single trigger axis (Lesson #21 compliant).
  - paradigm 133 (vol-of-vol 2nd-order clustering): std of std, magnitude only
      -> DISTINCT: signed up/down semivariance ratio carries direction natively,
                   NOT temporal magnitude clustering. KEY ADVANTAGE: direction
                   embedded in the statistic itself (not separated as in p133).

NOTE on Lesson #40 (structural threshold attainability):
  RV_up and RV_down individually are non-negative aggregates.
  RATIO RV_up/RV_down can be any positive value (0, inf).
  LOG of ratio = log(RV_up) - log(RV_down) is symmetric around 0.
  Z-score of log(ratio) is SYMMETRIC (can reach both +2 and -2).
  RESOLUTION: log transformation per Lesson #40 reformulation guidance —
  non-negative ratio -> log -> symmetric z. Both directions feasible.
  R-0 will measure empirical log_ratio_z distribution to verify |z|>2 reachable.

Lessons applied:
  #11 sample density            — per-symbol per-quadrant per-quarter >=30
  #16 Concentration Gate        — deferred to R-1 (paradigm 133 strict 30% required)
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch
  #20 4-cond narrow scope       — life-changing 4-dim pre-empt qualification
  #21 axis stacking avoidance   — single statistic axis (semivariance ratio), NO conjunction
  #22 frame-grade               — 1h base + 24h rolling RV_up/RV_down (24 obs/window),
                                  30d log-ratio z-score (720 obs), 4h hold; stateless quantile
  #23 non-event-anchored        — continuous rolling, no temporal cycle anchor
  #28 substrate availability    — 1m OHLCV per-symbol -> 5m aggregation
  #30 data_window_ratio         — ADA excluded; other 12 syms 750+d PASS
  #34 empirical distribution    — log_ratio_z p1/p5/p10/p50/p90/p95/p99 sampled
  #39 sub-class detection       — A_focus z>+2 × LONG / B_focus z<-2 × SHORT / mirrors
  #40 structural threshold       — LOG transform on positive ratio, symmetric z feasible
  #41 amendment dual-mode       — per-trade edge >= +2% advisory at R-1 narrow-scope pre-empt
  #43 trap awareness            — semivariance novelty needs mechanism alpha proof at R-1
  #44 amendment xref 17th dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit z-threshold on log-ratio (NOT HMM unsupervised)
  #46 AMENDMENT REFINEMENT       — temporally-stratified n=50x4q R-0 + per-quarter sign flip
                                   (9th TRUE POSITIVE in paradigm 133; 10th dogfood now)
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX + skill cross-reference
  #50 first-burst-sign N/A       — 4h frame (not 5m+)
  #52 a/b detection (candidate)  — both LONG quadrants positive + 0 syms ci_pos universal
                                   pattern detection at R-1
  #53 candidate detection        — hypothesis dir vs mirror dir comparison at R-1

Family avoidance verified (Lesson #45):
  - HMM unsupervised: AVOIDED (explicit z-threshold on log-ratio)
  - OI velocity directional: AVOIDED (price-based)
  - Stateful CP: AVOIDED (stateless rolling z)
  - Higher-order moment (kurtosis/skewness/3rd moment): AVOIDED
        (2nd-order signed decomposition, NOT 3rd/4th central moment)
  - Funding single-signal: AVOIDED
  - Volume share: AVOIDED
  - Magnitude-confluence: AVOIDED (single axis)
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure single-domain: AVOIDED (1h base / 4h hold)
  - Universe-aggregate scalar: AVOIDED (per-symbol)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA smoothed deviation: AVOIDED (rolling sums, no smoothing)
  - paradigm 126/127/128 1m volume burst family: AVOIDED (4h frame + return-based)
  - paradigm 118 realized correlation matrix: AVOIDED (per-sym, no cross-corr)
  - paradigm 133 vol-of-vol (magnitude clustering): AVOIDED (signed asymmetric decomp)
  - paradigm 124 kurtosis×skewness joint: AVOIDED (2nd-order semivariance NOT 3rd/4th moment)
  - paradigm 129 Parkinson range: AVOIDED (signed semivariance NOT total range)
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
log = logging.getLogger("p134_r0")

PARADIGM_NAME = "alt_realized_semivariance_asymmetry_up_down_ratio_z_directional_4h"
PARADIGM_NUM = 134
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 12 alts (ADA excluded per Lesson #30 short-window, reuse paradigm 133 cohort)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Trigger params
RV_WINDOW_5M_PER_1H = 12         # 12 × 5m bars per 1h for RV components
SEMIVAR_ROLLING_HOURS = 24        # 24h rolling sum of hourly RV_up / RV_down
ZSCORE_ROLLING_HOURS = 30 * 24    # 30 days × 24h = 720 hours for z-score baseline
Z_THRESHOLD = 2.0                  # |z| > 2 (symmetric, log-ratio is symmetric → Lesson #40)
FORWARD_HOLD_4H_BARS = 1           # 4h forward hold
DEBOUNCE_HOURS = 8                 # 8h between consecutive triggers per-symbol
FEE_BP = 16.0                      # 16bp round-trip
EPS = 1e-12                        # epsilon to stabilize log when RV_down → 0
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


def compute_semivariance_components_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Compute 1h RV_up and RV_down from 5m log returns.

    RV_up_1h = sum over 12 × 5m bars of r_t^2 where r_t > 0
    RV_down_1h = sum over 12 × 5m bars of r_t^2 where r_t < 0
    """
    close_5m = df_1m["close"].resample("5min").last().dropna()
    log_ret_5m = np.log(close_5m / close_5m.shift(1))
    # Positive and negative semi-returns squared
    sq_up = (log_ret_5m.clip(lower=0)) ** 2
    sq_down = (log_ret_5m.clip(upper=0)) ** 2
    # 1h aggregation with min_count = 8 of 12 5m bars
    rv_up_1h = sq_up.resample("1h").sum(min_count=8)
    rv_down_1h = sq_down.resample("1h").sum(min_count=8)
    out = pd.DataFrame({"rv_up_1h": rv_up_1h, "rv_down_1h": rv_down_1h}).dropna()
    return out


def compute_log_ratio_z(semivar: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """24h rolling sum -> log ratio -> 30d rolling z-score."""
    rv_up_24h = semivar["rv_up_1h"].rolling(
        window=SEMIVAR_ROLLING_HOURS, min_periods=18).sum()
    rv_down_24h = semivar["rv_down_1h"].rolling(
        window=SEMIVAR_ROLLING_HOURS, min_periods=18).sum()
    # Log ratio (symmetric around 0)
    log_ratio = np.log((rv_up_24h + EPS) / (rv_down_24h + EPS))
    # 30d rolling z-score on log_ratio
    lr_mean = log_ratio.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    lr_std = log_ratio.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    z = (log_ratio - lr_mean) / lr_std
    return log_ratio, z


def aggregate_to_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """4h bar close + log return."""
    bar4h = df_1m["close"].resample("4h").last().dropna().to_frame("close")
    bar4h["log_ret_4h"] = np.log(bar4h["close"]).diff()
    return bar4h


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    log.info("--- Step 1: per-symbol 1m -> 5m -> 1h RV_up/RV_down -> 24h sum -> log-ratio -> 30d z ---")
    sym_data = {}
    per_sym_days = {}
    z_aggregate = []
    log_ratio_aggregate = []
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < 30 * 24 * 60 * 2:  # need at least 60d 1m bars
                log.warning("%s: insufficient 1m data (n=%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days

            semivar = compute_semivariance_components_1h(df)
            if len(semivar) < ZSCORE_ROLLING_HOURS + SEMIVAR_ROLLING_HOURS:
                log.warning("%s: insufficient semivariance series (n=%d) -- skip",
                            sym, len(semivar))
                continue

            log_ratio, z = compute_log_ratio_z(semivar)
            bar4h = aggregate_to_4h(df)

            # Sample empirical distributions
            z_finite = z.dropna().values
            lr_finite = log_ratio.dropna().values
            z_aggregate.extend(z_finite.tolist()[:5000])
            log_ratio_aggregate.extend(lr_finite.tolist()[:5000])

            sym_data[sym] = {
                "df_1m": df,
                "semivar": semivar,
                "log_ratio": log_ratio,
                "z": z,
                "bar4h": bar4h,
            }
            log.info("%s: %d days, %d 1h semivar, %d 4h bars, "
                     "z range [%.2f, %.2f] valid=%d, log_ratio range [%.3f, %.3f]",
                     sym, days, len(semivar), len(bar4h),
                     float(np.nanmin(z_finite)) if len(z_finite) else float("nan"),
                     float(np.nanmax(z_finite)) if len(z_finite) else float("nan"),
                     len(z_finite),
                     float(np.nanmin(lr_finite)) if len(lr_finite) else float("nan"),
                     float(np.nanmax(lr_finite)) if len(lr_finite) else float("nan"))
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

    # Lesson #34 empirical z distribution
    z_arr = np.array(z_aggregate)
    z_arr_finite = z_arr[np.isfinite(z_arr)]
    pct_z = {p: float(np.percentile(z_arr_finite, p))
             for p in [1, 5, 10, 50, 70, 90, 95, 99]}
    z_max = float(np.max(z_arr_finite)) if len(z_arr_finite) else float("nan")
    z_min = float(np.min(z_arr_finite)) if len(z_arr_finite) else float("nan")
    log.info("log_ratio_z empirical percentiles (n=%d): %s", len(z_arr_finite), pct_z)
    log.info("log_ratio_z min=%.2f max=%.2f", z_min, z_max)

    lr_arr = np.array(log_ratio_aggregate)
    lr_arr_finite = lr_arr[np.isfinite(lr_arr)]
    pct_lr = {p: float(np.percentile(lr_arr_finite, p))
              for p in [1, 5, 10, 50, 70, 90, 95, 99]}
    log.info("log_ratio empirical percentiles (n=%d): %s", len(lr_arr_finite), pct_lr)

    # Lesson #40 — symmetric threshold reachable on BOTH sides
    z_max_reachable = z_max >= Z_THRESHOLD
    z_min_reachable = z_min <= -Z_THRESHOLD
    n_z_above_thresh = int((z_arr_finite > Z_THRESHOLD).sum())
    n_z_below_thresh = int((z_arr_finite < -Z_THRESHOLD).sum())
    pct_above = n_z_above_thresh / len(z_arr_finite) if len(z_arr_finite) else 0.0
    pct_below = n_z_below_thresh / len(z_arr_finite) if len(z_arr_finite) else 0.0
    lesson_40 = {
        "threshold_definition": f"|z| > {Z_THRESHOLD} on per-symbol 30d-rolling z of "
                                f"24h-rolling log(RV_up/RV_down)",
        "stat_class": "log_transformed_positive_ratio_symmetric",
        "log_transform_applied": True,
        "symmetric_negative_use": True,
        "reformulation": "log_transform_per_lesson_40_makes_symmetric_z_feasible",
        "empirical_z_max": z_max,
        "empirical_z_min": z_min,
        "z_max_reachable_pos2": z_max_reachable,
        "z_min_reachable_neg2": z_min_reachable,
        "n_above_pos2": n_z_above_thresh,
        "n_below_neg2": n_z_below_thresh,
        "pct_above_pos2": pct_above,
        "pct_below_neg2": pct_below,
        "verdict": ("PASS" if (z_max_reachable and z_min_reachable)
                    else "FAIL_STRUCTURAL_THRESHOLD_INFEASIBLE"),
    }
    log.info("Lesson #40 verification: %s", lesson_40)

    if not (z_max_reachable and z_min_reachable):
        log.error("z threshold structurally infeasible (one or both sides) -- HALT")
        out_path = OUT_DIR / "r0_prescreen.json"
        out_path.write_text(json.dumps({
            "paradigm_name": PARADIGM_NAME,
            "paradigm_number": PARADIGM_NUM,
            "phase": "R-0",
            "verdict": "R0_HALT_LESSON_40_STRUCTURAL_THRESHOLD_INFEASIBLE",
            "lesson_40": lesson_40,
        }, indent=2, default=str))
        sys.exit(2)

    # Step 2: build triggers per-symbol (debounced) + signed direction + fwd_4h
    log.info("--- Step 2: build triggers (|z| > %.1f, debounce %dh, fwd 4h) ---",
             Z_THRESHOLD, DEBOUNCE_HOURS)
    trig_rows = []
    for sym, d in sym_data.items():
        z = d["z"]
        bar4h = d["bar4h"]

        # Resample z to 4h: take z value AT bar boundary (last 1h within the 4h)
        # Use last() to preserve sign (max/min would bias)
        z_4h = z.resample("4h").last().dropna()
        z_4h_aligned = z_4h.reindex(bar4h.index, method="ffill")
        bar4h = bar4h.copy()
        bar4h["z_log_ratio"] = z_4h_aligned
        bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)

        last_ts = None
        for ts, row in bar4h.iterrows():
            z_val = row["z_log_ratio"]
            if pd.isna(z_val) or abs(z_val) <= Z_THRESHOLD:
                continue
            if pd.isna(row["log_ret_4h"]) or pd.isna(row["fwd_log_ret_4h"]):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            # DIRECTION CARRIED BY Z SIGN (not by trigger-bar return) — Patton-Sheppard insight
            direction = 1 if z_val > 0 else -1
            signed_fwd_bp = float(row["fwd_log_ret_4h"]) * direction * 10000.0
            trig_rows.append({
                "ts": ts,
                "sym": sym,
                "z_log_ratio": float(z_val),
                "log_ret_4h": float(row["log_ret_4h"]),
                "direction": direction,
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "signed_fwd_bp": signed_fwd_bp,
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts

    trig_df = pd.DataFrame(trig_rows)
    if trig_df.empty:
        log.error("zero triggers -- abort")
        sys.exit(1)
    log.info("total triggers across %d syms: %d (z>+2 pos=%d, z<-2 neg=%d)",
             len(sym_data), len(trig_df),
             int((trig_df["direction"] > 0).sum()),
             int((trig_df["direction"] < 0).sum()))

    # Per-quarter density (Lesson #11)
    n_quarters = trig_df["qtr"].nunique()
    per_q_pos = trig_df[trig_df["direction"] > 0].groupby("qtr").size()
    per_q_neg = trig_df[trig_df["direction"] < 0].groupby("qtr").size()
    log.info("per-quarter pos (z>+2): %s", per_q_pos.to_dict())
    log.info("per-quarter neg (z<-2): %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (>=30): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT (10th dogfood)
    log.info("--- Lesson #46 REFINEMENT: temporally-stratified n=50x4q R-0 (10th dogfood) ---")
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

    qa = stats(a_focus, "A_focus_z_pos_LONG_4h")
    qam = stats(a_mirror, "A_mirror_z_pos_SHORT_4h")
    qb = stats(b_focus, "B_focus_z_neg_SHORT_4h")
    qbm = stats(b_mirror, "B_mirror_z_neg_LONG_4h")
    log.info("R-0 4-quadrant stratified estimate (strategy=%s):", strat_strategy)
    for q in [qa, qam, qb, qbm]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter sign-flip detection (Lesson #46 sub-amendment 10th dogfood)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 sub-amendment 10th dogfood) ---")
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

    # Lesson #44 cross-reference (17th dogfood)
    lesson_44_xref = {
        "paradigm_65_skewness_mr":
            "GRAVEYARD — 3rd moment cross-sec MR. DISTINCT: semivariance RATIO (2nd-order signed decomp), NOT 3rd moment.",
        "paradigm_66_skewness_momentum":
            "GRAVEYARD — 3rd moment momentum. DISTINCT: signed semivariance ratio, NOT 3rd moment.",
        "paradigm_67_btc_rv_spike_alt_recovery":
            "GRAVEYARD — BTC 1d total RV. DISTINCT: per-sym up/down semivariance decomp, NOT BTC total RV.",
        "paradigm_68_btc_rv_spike_up_conditional":
            "GRAVEYARD R-3.5 — BTC RV sign-cond. DISTINCT: intrinsic semivariance ratio (no BTC dep).",
        "paradigm_69_btc_rv_spike_highvol_filter":
            "R-5 SEEDED — BTC RV p90 LONG. DISTINCT: per-sym signed semivariance, NOT BTC RV level.",
        "paradigm_81_rolling_beta_regime":
            "GRAVEYARD — rolling beta vs BTC. DISTINCT: intrinsic asymmetric semivariance, no beta.",
        "paradigm_84_book_depth_cusum":
            "SAMPLE_INSUFFICIENT — Page-Hinkley CP. DISTINCT: stateless ratio z, return-based.",
        "paradigm_118_realized_correlation_regime":
            "GRAVEYARD — universe-aggregate corr. DISTINCT: per-sym ratio, no cross-corr.",
        "paradigm_121_hmm_realized_vol_state":
            "GRAVEYARD Lesson #45 — HMM unsup on RV. DISTINCT: explicit z on signed log-ratio (Lesson #45 compliant).",
        "paradigm_123_alt_volume_cusum_change_point":
            "GRAVEYARD Lesson #19 SNT — stateful CP on volume. DISTINCT: stateless ratio z, return-based.",
        "paradigm_124_alt_realized_kurtosis_skewness":
            "GRAVEYARD — 3rd × 4th moment joint. DISTINCT: 2nd-order signed semivariance decomp (NOT higher-order moment).",
        "paradigm_125_alt_realized_quarticity_bipower":
            "R-0 HALT Lesson #40 — B-N jump test ratio. DISTINCT: semivariance ratio (signed asymmetry NOT jump test).",
        "paradigm_129_alt_parkinson_range":
            "GRAVEYARD — Parkinson high-low range. DISTINCT: signed up/down decomposition (sign info preserved, NOT lost via high-low).",
        "paradigm_130_alt_atr_normalized_range_breakout":
            "GRAVEYARD — ATR + breakout. DISTINCT: pure semivariance ratio, NOT level breakout/ATR.",
        "paradigm_131_alt_volume_burst_intra5m_signed":
            "GRAVEYARD — 5m volume burst. DISTINCT: 4h frame + return-based, NOT 5m volume.",
        "paradigm_132_funding_oi_magnitude_triple":
            "GRAVEYARD Lesson #21 — 3-way axis stacking. DISTINCT: single trigger axis (Lesson #21 compliant).",
        "paradigm_133_alt_realized_vol_of_vol":
            "GRAVEYARD CONCENTRATED_R1_PASS — vol-of-vol 2nd-order clustering (magnitude only, direction separate). "
            "DISTINCT: signed up/down semivariance ratio (direction NATIVELY embedded in stat) — key advantage over p133 separable mag/dir.",
        "paradigm_126_127_128_volume_burst_family":
            "R-5 SEEDED 127+128 — 1m volume burst. DISTINCT: 4h frame + signed semivariance stat, NOT 1m volume.",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit z-threshold on log_ratio, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (price-based)",
        "Stateful_CP_Page_Hinkley": "AVOIDED (stateless rolling z, Lesson #22)",
        "Higher_order_moment_kurtosis_skewness": "AVOIDED (2nd-order signed semivariance decomp, NOT 3rd/4th moment)",
        "Funding_single_signal": "AVOIDED (no funding)",
        "Volume_share": "AVOIDED (no volume)",
        "Magnitude_confluence": "AVOIDED (single trigger axis, Lesson #21)",
        "Listing_event": "AVOIDED (continuous rolling)",
        "5m_microstructure_single_domain": "AVOIDED (1h base + 4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-symbol)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed_deviation": "AVOIDED (rolling sums, no smoothing)",
        "paradigm_118_realized_corr_matrix": "AVOIDED (per-sym, NOT cross-corr)",
        "paradigm_124_higher_order_moments": "AVOIDED (2nd-order signed decomp, NOT 3rd/4th moment)",
        "paradigm_129_Parkinson_range": "AVOIDED (signed semivariance, NOT high-low range)",
        "paradigm_133_vol_of_vol_magnitude_clustering":
            "AVOIDED (signed asymmetric decomp NATIVELY directional, NOT magnitude clustering with direction proxy)",
        "Funding_family_3way_stack": "AVOIDED (single axis)",
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
            "semivar_rolling_hours": SEMIVAR_ROLLING_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold_absolute": Z_THRESHOLD,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_bp": FEE_BP,
            "log_epsilon": EPS,
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
        "lesson_34_empirical_log_ratio_percentiles": pct_lr,
        "lesson_34_z_min": z_min,
        "lesson_34_z_max": z_max,
        "lesson_40": lesson_40,
        "lesson_46_amendment_refinement_strategy": strat_strategy,
        "lesson_46_quarters_used": qtrs_to_use,
        "r0_4quadrant_stratified_estimate": {
            "A_focus_z_pos_LONG_4h": qa,
            "A_mirror_z_pos_SHORT_4h": qam,
            "B_focus_z_neg_SHORT_4h": qb,
            "B_mirror_z_neg_LONG_4h": qbm,
        },
        "per_quarter_r0_detail": per_qtr_r0,
        "lesson_46_sign_flips": {"A_focus_flips": a_flips, "A_signs": a_signs,
                                 "B_focus_flips": b_flips, "B_signs": b_signs},
        "lesson_44_xref_17th_dogfood": lesson_44_xref,
        "family_avoidance_verification": family_avoidance,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("VERDICT: %s", verdict)
    log.info("R-0 saved to %s", out_path)


if __name__ == "__main__":
    main()
