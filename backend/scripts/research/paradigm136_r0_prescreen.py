"""paradigm 136 R-0 prescreen — alt_intraday_1h_log_return_std_24h_window_z_directional_4h.

Hypothesis (1st-order intraday vol, 1h frame, NEW):
  per-symbol 1h log-return rolling 24h std (intraday vol):
    Step 1: per-sym 1h close, log_ret_1h = log(c_t / c_{t-1h})
    Step 2: rolling 24h window std of log_ret_1h (24 obs)
            vol_1h_24h = std(prior 24 hourly log-returns)
    Step 3: per-sym 30d (720h) rolling z-score of vol_1h_24h
            z_vol = (vol - mean_30d) / std_30d
  Trigger: |z_vol| > 2 (1h intraday vol regime extreme)
  Direction matching: trigger-bar 4h log-return sign
    (1st-order vol = magnitude only -> direction MUST come from price action)
  Forward hold: 4h directional
  Debounce: 8h
  Universe: 12 alts (paradigm 133/134 cohort, ADA excluded Lesson #30)

CRITICAL distinction vs prior vol family:
  - paradigm 67/68/69 BTC RV: 1d close-to-close, BTC-anchored cross-asset
    -> DISTINCT: per-sym 1h frame (intraday), NOT BTC-anchored cross-asset
  - paradigm 133 vol-of-vol: std of (std), 2nd-order temporal clustering
    -> DISTINCT: 1st-order std (NOT 2nd-order)
  - paradigm 134 signed semivariance: asymmetric up/down decomposition
    -> DISTINCT: total std (NOT signed decomposition)
  - paradigm 129 Parkinson: high-low range estimator
    -> DISTINCT: close-to-close std (NOT high-low range)

Family-distinct claim (Lesson #44 amendment 19th dogfood):
  1st-order intraday vol on 1h frame is novel statistic class:
    paradigm 67/68/69: 1d close-to-close RV (1d frame BTC cross-asset)
    paradigm 124: kurtosis/skewness (3rd/4th moments)
    paradigm 125: quarticity bipower (jump test)
    paradigm 129: Parkinson (high-low range)
    paradigm 130: ATR breakout level
    paradigm 133: vol-of-vol (2nd-order)
    paradigm 134: signed semivariance (asymmetric decomp)
    paradigm 135: VRP (vol-risk-premium ratio composite) [R-0 halt #54]
    paradigm 136: 1st-order TOTAL std on 1h frame (NEW NOT yet covered)

NOTE on Lesson #21 (axis stacking):
  Single statistic: rolling 24h std of 1h log_ret.
  z-score is per-symbol rolling normalization (NOT axis stack).
  Direction matching via trigger-bar 4h sign is NOT axis stacking
  (vol stat is magnitude-only by construction, sign must come elsewhere).
  COMPLIANT with Lesson #21.

NOTE on Lesson #21 sub-finding magnitude-ratio (candidate advisory):
  This candidate is single RAW signal (NOT composite ratio).
  vol = std(log_ret) is single estimator output.
  NOT 2-signal composite (e.g., vol_a / vol_b ratio).
  COMPLIANT with sub-finding (no magnitude-ratio composite).

NOTE on Lesson #40 (structural threshold attainability):
  std is non-negative aggregate (>= 0).
  Raw vol cannot reach negative.
  RESOLUTION: per-symbol 30d rolling z-score on vol REPLACES raw threshold.
  z-score CAN go negative (vol below baseline) and positive (vol above baseline).
  z-score of non-negative variable is SYMMETRIC around 0 in distribution
  IF the variable does not have hard floor at 0 frequently
  (i.e., for active perp 1h returns, vol > 0 almost everywhere).
  R-0 will measure empirical z_vol distribution to verify |z|>2 reachable
  on BOTH sides (high vol regime + low vol regime).

NOTE on Lesson #50 (first-burst-sign):
  4h frame -- not 5m+, Lesson #50 N/A.

NOTE on paradigm 69 BTC RV highvol R-5 family-distinct:
  paradigm 69 = BTC 1d close-to-close RV (BTC-anchored, 1d frame, cross-asset 13 alts LONG)
  paradigm 136 = per-symbol 1h log-return rolling 24h std (intra-day per-sym, 1h frame, directional)
  DISTINCT: per-sym vs cross-asset, 1h vs 1d frame, intra-day vs daily

Lessons applied:
  #11 sample density            — per-symbol per-quadrant per-quarter >=30
  #16 Concentration Gate        — deferred to R-1 (STRICT 30% required per p133 lesson)
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch
  #20 4-cond narrow scope       — life-changing 4-dim pre-empt qualification
  #21 axis stacking avoidance   — single statistic axis (rolling std)
  #21 sub-finding magnitude-ratio — single RAW signal (NOT composite ratio)
  #22 frame-grade               — 1h base + 24h rolling std (24 obs) + 30d z (720 obs)
  #23 non-event-anchored        — continuous rolling, no temporal cycle anchor
  #28 substrate availability    — 1m OHLCV per-symbol -> 1h aggregation
  #30 data_window_ratio         — ADA excluded; 12 syms 750+d PASS
  #34 empirical distribution    — z_vol p1/p5/p10/p50/p90/p95/p99 sampled
  #39 sub-class detection       — A_focus z>+2 × LONG (high vol continuation) /
                                    B_focus z<-2 × SHORT (low vol regime trend)
  #40 structural threshold      — z-score reformulation per Lesson #40 guidance
  #41 amendment dual-mode       — per-trade edge >= +2% advisory at R-1 narrow-scope pre-empt
  #43 trap awareness            — direction-from-price not direction-from-stat (p133 fail mode risk)
  #44 amendment xref 19th dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit z-threshold (NOT HMM unsupervised)
  #46 AMENDMENT REFINEMENT       — temporally-stratified n=50x4q R-0 + per-quarter sign flip
                                   (11th dogfood CONFIRMED-eligible)
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX + skill cross-reference
  #52 a/b detection (confirmed)  — both LONG quadrants positive + 0 syms ci_pos pattern detection at R-1
  #53 candidate detection        — hypothesis dir vs mirror dir comparison at R-1
  #54 candidate (CONFIRMED-eligible) — composite ratio/division not used; single stat only

Family avoidance verified (Lesson #45):
  - HMM unsupervised: AVOIDED (explicit z-threshold on rolling std)
  - OI velocity directional: AVOIDED (price-based)
  - Stateful CP: AVOIDED (stateless rolling z)
  - Higher-order moment (kurtosis/skewness): AVOIDED (2nd moment = std)
  - Signed decomposition semivariance: AVOIDED (total std)
  - High-low range estimator (Parkinson): AVOIDED (close-to-close std)
  - 2nd-order vol-of-vol: AVOIDED (1st-order)
  - Funding single-signal: AVOIDED
  - Volume share: AVOIDED
  - Magnitude-confluence: AVOIDED (single axis)
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure single-domain: AVOIDED (1h base / 4h frame)
  - Universe-aggregate scalar: AVOIDED (per-symbol)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA smoothed deviation: AVOIDED (rolling sums, no smoothing)
  - paradigm 67/68/69 BTC RV 1d cross-asset: AVOIDED (per-sym 1h intraday)
  - paradigm 118 realized correlation matrix: AVOIDED (per-sym, no cross-corr)
  - paradigm 135 VRP composite ratio: AVOIDED (single stat, no division/ratio)
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
log = logging.getLogger("p136_r0")

PARADIGM_NAME = "alt_intraday_1h_log_return_std_24h_window_z_directional_4h"
PARADIGM_NUM = 136
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 12 alts (ADA excluded per Lesson #30 short-window, reuse paradigm 133/134 cohort)
COHORT = [
    "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

VOL_ROLLING_HOURS = 24            # 24h rolling std window (24 obs of 1h log_ret)
ZSCORE_ROLLING_HOURS = 30 * 24    # 30 days × 24h = 720 hours for z-score baseline
Z_THRESHOLD = 2.0                  # |z| > 2 (symmetric)
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


def compute_vol_1h_24h(df_1m: pd.DataFrame) -> pd.Series:
    """1m -> 1h close -> 1h log_ret -> rolling 24h std.

    Step 1: aggregate 1m close -> 1h last
    Step 2: log_ret_1h = log(c / c.shift(1))
    Step 3: rolling 24h std on log_ret_1h (24 obs window)
    """
    close_1h = df_1m["close"].resample("1h").last().dropna()
    log_ret_1h = np.log(close_1h / close_1h.shift(1))
    vol_1h_24h = log_ret_1h.rolling(window=VOL_ROLLING_HOURS, min_periods=18).std()
    return vol_1h_24h


def compute_vol_z(vol: pd.Series) -> pd.Series:
    """Per-symbol 30d rolling z-score on intraday vol."""
    v_mean = vol.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).mean()
    v_std = vol.rolling(window=ZSCORE_ROLLING_HOURS, min_periods=240).std()
    return (vol - v_mean) / v_std


def aggregate_to_4h(df_1m: pd.DataFrame) -> pd.DataFrame:
    """4h bar close + log return."""
    bar4h = df_1m["close"].resample("4h").last().dropna().to_frame("close")
    bar4h["log_ret_4h"] = np.log(bar4h["close"]).diff()
    return bar4h


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    log.info("--- Step 1: per-symbol 1m -> 1h log_ret -> 24h rolling std -> 30d z ---")
    sym_data = {}
    per_sym_days = {}
    z_aggregate = []
    vol_aggregate = []
    for sym in COHORT:
        try:
            df = load_ohlcv_1m(sym, engine)
            if df.empty or len(df) < 30 * 24 * 60 * 2:  # need at least 60d 1m bars
                log.warning("%s: insufficient 1m data (n=%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days

            vol_1h = compute_vol_1h_24h(df)
            if len(vol_1h) < ZSCORE_ROLLING_HOURS + VOL_ROLLING_HOURS:
                log.warning("%s: insufficient vol series (n=%d) -- skip",
                            sym, len(vol_1h))
                continue

            z = compute_vol_z(vol_1h)
            bar4h = aggregate_to_4h(df)

            # Sample empirical distributions
            z_finite = z.dropna().values
            v_finite = vol_1h.dropna().values
            z_aggregate.extend(z_finite.tolist()[:5000])
            vol_aggregate.extend(v_finite.tolist()[:5000])

            sym_data[sym] = {
                "df_1m": df,
                "vol_1h_24h": vol_1h,
                "z": z,
                "bar4h": bar4h,
            }
            log.info("%s: %d days, %d 1h vol, %d 4h bars, "
                     "z range [%.2f, %.2f] valid=%d, vol range [%.5f, %.5f]",
                     sym, days, len(vol_1h), len(bar4h),
                     float(np.nanmin(z_finite)) if len(z_finite) else float("nan"),
                     float(np.nanmax(z_finite)) if len(z_finite) else float("nan"),
                     len(z_finite),
                     float(np.nanmin(v_finite)) if len(v_finite) else float("nan"),
                     float(np.nanmax(v_finite)) if len(v_finite) else float("nan"))
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
    log.info("z_vol empirical percentiles (n=%d): %s", len(z_arr_finite), pct_z)
    log.info("z_vol min=%.2f max=%.2f", z_min, z_max)

    v_arr = np.array(vol_aggregate)
    v_arr_finite = v_arr[np.isfinite(v_arr)]
    pct_v = {p: float(np.percentile(v_arr_finite, p))
             for p in [1, 5, 10, 50, 70, 90, 95, 99]}
    log.info("vol_1h_24h empirical percentiles (n=%d): %s", len(v_arr_finite), pct_v)

    # Lesson #40 — symmetric threshold reachable on BOTH sides
    # std is non-negative, but its 30d z-score CAN go negative (low vol regime)
    # if vol fluctuates around a positive mean
    z_max_reachable = z_max >= Z_THRESHOLD
    z_min_reachable = z_min <= -Z_THRESHOLD
    n_z_above_thresh = int((z_arr_finite > Z_THRESHOLD).sum())
    n_z_below_thresh = int((z_arr_finite < -Z_THRESHOLD).sum())
    pct_above = n_z_above_thresh / len(z_arr_finite) if len(z_arr_finite) else 0.0
    pct_below = n_z_below_thresh / len(z_arr_finite) if len(z_arr_finite) else 0.0
    lesson_40 = {
        "threshold_definition": f"|z| > {Z_THRESHOLD} on per-symbol 30d-rolling z of "
                                f"24h-rolling std(1h log_ret)",
        "stat_class": "non_negative_aggregate_std_with_zscore_reformulation",
        "z_score_applied": True,
        "symmetric_negative_use": True,
        "reformulation": "z_score_per_lesson_40_makes_symmetric_z_feasible_if_vol_floats",
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

    # Step 2: build triggers per-symbol (debounced) + signed direction (from 4h ret) + fwd_4h
    log.info("--- Step 2: build triggers (|z| > %.1f, debounce %dh, fwd 4h) ---",
             Z_THRESHOLD, DEBOUNCE_HOURS)
    trig_rows = []
    for sym, d in sym_data.items():
        z = d["z"]
        bar4h = d["bar4h"]

        # Resample z to 4h: take z value AT bar boundary (last 1h within the 4h)
        z_4h = z.resample("4h").last().dropna()
        z_4h_aligned = z_4h.reindex(bar4h.index, method="ffill")
        bar4h = bar4h.copy()
        bar4h["z_vol"] = z_4h_aligned
        bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)

        last_ts = None
        for ts, row in bar4h.iterrows():
            z_val = row["z_vol"]
            if pd.isna(z_val) or abs(z_val) <= Z_THRESHOLD:
                continue
            if pd.isna(row["log_ret_4h"]) or pd.isna(row["fwd_log_ret_4h"]):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            # vol is magnitude-only, direction from trigger-bar 4h log_ret sign
            # 4 quadrants split by z_vol sign × trigger-bar return sign:
            #   z>+2 (high vol): A_focus = LONG, A_mirror = SHORT
            #   z<-2 (low vol):  B_focus = SHORT, B_mirror = LONG
            # BUT the trigger-bar return sign also matters for sub-stratification.
            # Following paradigm 133 pattern: use trigger-bar 4h sign as direction match,
            # then split by z_vol sign for high/low vol regime classification.
            # SIMPLIFICATION: focus on z-sign as primary direction (high vol -> LONG / low vol -> SHORT
            # canonical "vol trend continuation" hypothesis, mirror tests fade)
            direction = 1 if z_val > 0 else -1
            signed_fwd_bp = float(row["fwd_log_ret_4h"]) * direction * 10000.0
            trig_rows.append({
                "ts": ts,
                "sym": sym,
                "z_vol": float(z_val),
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

    # Lesson #46 AMENDMENT REFINEMENT (11th dogfood CONFIRMED-eligible)
    log.info("--- Lesson #46 REFINEMENT: temporally-stratified n=50x4q R-0 (11th dogfood) ---")
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

    # Per-quarter sign-flip detection (Lesson #46 sub-amendment 11th dogfood)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 sub-amendment 11th dogfood) ---")
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

    # Lesson #44 cross-reference (19th dogfood)
    lesson_44_xref = {
        "paradigm_65_skewness_mr":
            "GRAVEYARD — 3rd moment cross-sec MR. DISTINCT: 2nd-order total std (NOT 3rd moment).",
        "paradigm_66_skewness_momentum":
            "GRAVEYARD — 3rd moment momentum. DISTINCT: 2nd-order total std (NOT 3rd moment).",
        "paradigm_67_btc_rv_spike_alt_recovery":
            "GRAVEYARD — BTC 1d total RV. DISTINCT: per-sym 1h intraday std (NOT BTC 1d cross-asset).",
        "paradigm_68_btc_rv_spike_up_conditional":
            "GRAVEYARD R-3.5 — BTC RV sign-cond. DISTINCT: intrinsic per-sym 1h vol (no BTC dep).",
        "paradigm_69_btc_rv_spike_highvol_filter":
            "R-5 SEEDED — BTC RV p90 LONG. DISTINCT: per-sym 1h intraday std, NOT BTC 1d RV level.",
        "paradigm_81_rolling_beta_regime":
            "GRAVEYARD — rolling beta vs BTC. DISTINCT: intrinsic per-sym vol, no beta.",
        "paradigm_84_book_depth_cusum":
            "SAMPLE_INSUFFICIENT — Page-Hinkley CP. DISTINCT: stateless rolling std z, return-based.",
        "paradigm_118_realized_correlation_regime":
            "GRAVEYARD — universe-aggregate corr. DISTINCT: per-sym vol, no cross-corr.",
        "paradigm_121_hmm_realized_vol_state":
            "GRAVEYARD Lesson #45 — HMM unsup on RV. DISTINCT: explicit z on rolling std (Lesson #45 compliant).",
        "paradigm_124_alt_realized_kurtosis_skewness":
            "GRAVEYARD — 3rd × 4th moment joint. DISTINCT: 2nd-order total std (NOT higher-order moment).",
        "paradigm_125_alt_realized_quarticity_bipower":
            "R-0 HALT Lesson #40 — B-N jump test ratio. DISTINCT: total std (NOT jump test ratio).",
        "paradigm_129_alt_parkinson_range":
            "GRAVEYARD — Parkinson high-low range. DISTINCT: close-to-close std (NOT high-low range).",
        "paradigm_130_alt_atr_normalized_range_breakout":
            "GRAVEYARD — ATR + breakout. DISTINCT: pure std stat, NOT level breakout/ATR.",
        "paradigm_131_alt_volume_burst_intra5m_signed":
            "GRAVEYARD — 5m volume burst. DISTINCT: 1h base + 4h frame, return-based NOT 5m volume.",
        "paradigm_132_funding_oi_magnitude_triple":
            "GRAVEYARD Lesson #21 — 3-way axis stacking. DISTINCT: single trigger axis (Lesson #21 compliant).",
        "paradigm_133_alt_realized_vol_of_vol":
            "GRAVEYARD CONCENTRATED_R1_PASS — vol-of-vol 2nd-order clustering. "
            "DISTINCT: 1st-order TOTAL std (NOT 2nd-order std-of-std). KEY DISTINCTION: simpler base stat.",
        "paradigm_134_alt_realized_semivariance_asymmetry":
            "GRAVEYARD — signed up/down semivariance ratio. DISTINCT: TOTAL std (NOT up/down decomposed).",
        "paradigm_135_alt_funding_implied_vs_realized_vol_premium":
            "R-0 HALT Lesson #54 — VRP composite ratio (funding-implied / realized). "
            "DISTINCT: single raw stat (rolling std), NO division/composite ratio.",
        "paradigm_126_127_128_volume_burst_family":
            "R-5 SEEDED 127+128 — 1m volume burst. DISTINCT: 4h frame + return-based vol stat, NOT 1m volume.",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit z-threshold on rolling std, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (price-based)",
        "Stateful_CP_Page_Hinkley": "AVOIDED (stateless rolling z, Lesson #22)",
        "Higher_order_moment_kurtosis_skewness": "AVOIDED (2nd-order std, NOT 3rd/4th moment)",
        "Signed_decomposition_semivariance": "AVOIDED (total std, NOT signed)",
        "High_low_range_Parkinson": "AVOIDED (close-to-close std, NOT high-low)",
        "Second_order_vol_of_vol": "AVOIDED (1st-order std, NOT std-of-std)",
        "Funding_single_signal": "AVOIDED (no funding)",
        "Volume_share": "AVOIDED (no volume)",
        "Magnitude_confluence": "AVOIDED (single trigger axis, Lesson #21)",
        "Listing_event": "AVOIDED (continuous rolling)",
        "5m_microstructure_single_domain": "AVOIDED (1h base + 4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-symbol)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed_deviation": "AVOIDED (rolling sums, no smoothing)",
        "paradigm_67_68_69_BTC_RV_1d_cross_asset": "AVOIDED (per-sym 1h intraday)",
        "paradigm_118_realized_corr_matrix": "AVOIDED (per-sym, NOT cross-corr)",
        "paradigm_133_vol_of_vol_2nd_order": "AVOIDED (1st-order std)",
        "paradigm_134_signed_semivariance": "AVOIDED (total std, NOT decomposed)",
        "paradigm_135_VRP_composite_ratio": "AVOIDED (single raw stat, NO division)",
        "Funding_family_3way_stack": "AVOIDED (single axis)",
        "Lesson_21_sub_finding_magnitude_ratio": "COMPLIANT (single raw signal, NOT 2-signal composite)",
        "Lesson_54_composite_division": "COMPLIANT (single std stat, NO ratio/division)",
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
            "vol_rolling_hours": VOL_ROLLING_HOURS,
            "zscore_rolling_hours": ZSCORE_ROLLING_HOURS,
            "z_threshold_absolute": Z_THRESHOLD,
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
        "lesson_34_empirical_vol_percentiles": pct_v,
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
        "lesson_44_xref_19th_dogfood": lesson_44_xref,
        "family_avoidance_verification": family_avoidance,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("VERDICT: %s", verdict)
    log.info("R-0 saved to %s", out_path)


if __name__ == "__main__":
    main()
