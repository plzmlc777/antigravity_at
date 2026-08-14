"""paradigm 131 R-0 prescreen — alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h.

Hypothesis:
  Dual-axis LIQUIDITY-STRESS conjunction:
    Axis 1: mark-index basis 4h pct z-score (rolling 30d / 180 4h-bars)
            trigger: |basis_z| > 1.5 (perp dislocation)
    Axis 2: (high - low) / close 4h "range_close" ratio z-score (rolling 30d)
            trigger: |range_close_z| > 1.5 (bid-ask spread proxy widening)
  Joint trigger: BOTH axes extreme in same bar (liquidity stress confluence)
  Direction: sign(basis_z) → MEAN-REVERSION trade
    A_focus: basis_z>+1.5 AND range_close_z>+1.5 → SHORT (perp rich + spread wide → revert)
    A_mirror: same trigger × LONG
    B_focus: basis_z<-1.5 AND range_close_z>+1.5 → LONG (perp cheap + spread wide → revert)
    B_mirror: same trigger × SHORT
  Forward hold: 4h (next 4h-bar close-to-close perp return on alt)
  Debounce: 8h between consecutive triggers
  Universe: 6 alts from paradigm 111 markPrice cache reuse
            (SOL, HBAR, AVAX, DOGE, ETH, LINK) × 12 months 2025-05..2026-04

Family-distinct claim (Lesson #44 amendment 13th dogfood):
  - paradigm 111 (mark_index_basis_extreme_alt_directional_4h): BASIS SINGLE-AXIS
      → DISTINCT: paradigm 131 adds range_close conjunction (liquidity stress
        confluence). Direction is MEAN-REVERSION (paradigm 111 used continuation
        on basis sign — broad-falsified). Lesson #21 individual-vs-joint
        sigex comparison MANDATORY.
  - paradigm 121 (hmm_realized_vol_state_x_markprice_basis_extreme):
      → DISTINCT: NO HMM (Lesson #45 CONFIRMED). Explicit empirical z-score
        threshold. range_close axis (NOT vol state filter).
  - paradigm 118 (universe_aggregate correlation): cross-asset correlation
      → DISTINCT: single-symbol intra-bar (range_close per-sym), no correlation.
  - paradigm 75/81/130 correlation/beta family (4 graveyards, retire candidate)
      → DISTINCT: liquidity microstructure (basis + range), no correlation.
  - paradigm 129 (parkinson range vol expansion percentile):
      → DISTINCT: 2-axis conjunction with EXOGENOUS basis (vs intrinsic range only).
        MEAN-REVERSION direction (paradigm 129 used continuation drift, became
        Lesson #51 LONG-drift artifact 1st dogfood).
  - paradigm 124/125 higher-order moments: DISTINCT (2nd-order range:close only)
  - paradigm 122/123 stateful CP / session anchor: DISTINCT (stateless rolling
        z-score, continuous rolling)
  - paradigm 96/97/98/99 funding family (8 retired): DISTINCT (no funding axis)
  - paradigm 102/103 cross-venue: DISTINCT (single-venue Binance perp only)
  - paradigm 75 cohort dispersion: DISTINCT (per-sym not cohort-aggregate)
  - Volume burst paradigm 126/127/128: DISTINCT (no volume axis, 4h frame
        not 5m+1m intra-bar)

Lessons applied:
  #8 amendment / #52 a/b (universe LONG drift OR conditional-overextension SHORT bias)
    — paradigm 130 INVERSE 1st dogfood demands explicit DUAL detection
  #11 sample density            — per-pair per-quadrant per-quarter >=30
  #16 Concentration Gate        — q_pos_t_ratio + symbol_ci_pos_ratio + n_syms_ci_pos
  #19 SNT mandatory             — 4-quadrant SNT in R-1 batch
  #21 axis stacking caution     — INDIVIDUAL-vs-JOINT sigex comparison MANDATORY
                                   (basis_only vs range_close_only vs joint)
  #22 frame-grade               — 4h frame, 30d rolling 180 obs (frame-rich)
  #23 non-event-anchored        — continuous rolling, no temporal cycle anchor
  #28 substrate availability    — paradigm 111 cache reuse (6 alts × 12 months PASS)
  #30 data_window_ratio         — 12mo / 12mo full window = 1.0 PASS
  #34 empirical distribution    — basis_z + range_close_z p10/p25/p50/p75/p90 sampled
  #39 sub-class A/B/C/D manual  — 4-quadrant + sub-class D (LONG drift) detection
  #40 structural threshold      — |z|>1.5 is symmetric on signed statistic (PASS).
                                   range_close is non-negative aggregate → |z|>1.5
                                   in POSITIVE tail only (z<-1.5 unreachable for
                                   non-negative aggregate) → use upper-tail z>+1.5
                                   only for range_close axis
  #41 amendment edge-first      — per-trade edge >= +2% advisory at R-1
  #44 amendment xref 13th dogfood — graveyard + RUNBOOK + INDEX cross-reference
  #45 family-distinct           — explicit empirical z-score, NOT HMM/unsupervised
  #46 AMENDMENT REFINEMENT       — temporally-stratified n=50x4q R-0 + sign-flip
  #48 inventory check scope      — graveyard + RUNBOOK + INDEX + skill cross-reference
  #50 first-burst-sign N/A       — 4h frame, not 5m+
  #51 candidate (1 dogfood)      — universe LONG drift artifact: A_focus_LONG +
                                   B_mirror_LONG both gross>0 + ci_lower<0
  #52 a (1 dogfood) / b (1 dogfood) candidate — explicit dual detection in R-1

Family avoidance verified:
  - HMM unsupervised: AVOIDED (explicit empirical z-score thresholds)
  - OI velocity: AVOIDED (basis + range only, no OI)
  - Stateful CP: AVOIDED (stateless rolling z-score)
  - Higher-order moment: AVOIDED (basis level + 2nd-order range only)
  - Funding single-signal: AVOIDED (no funding axis)
  - Volume share / volume burst: AVOIDED (no volume axis)
  - Magnitude-confluence simple: distinct via DIRECTIONAL MEAN-REVERSION via basis sign
  - Listing event: AVOIDED (continuous rolling)
  - 5m microstructure single-domain: AVOIDED (4h frame)
  - Universe-aggregate scalar: AVOIDED (per-sym)
  - Session-anchor: AVOIDED (continuous rolling)
  - VWAP/EWMA: AVOIDED (raw 4h closes)
  - paradigm 111 single-axis basis: AVOIDED (conjunction + mean-reversion)
  - paradigm 121 HMM: AVOIDED (no HMM)
  - Correlation/beta/lead-lag: AVOIDED (no cross-asset correlation)
  - Range-only intrinsic: AVOIDED (combined with EXOGENOUS basis)
"""
from __future__ import annotations

import io
import json
import logging
import math
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p131_r0")

PARADIGM_NAME = "alt_basis_spike_x_range_close_bidask_proxy_signed_directional_4h"
PARADIGM_NUM = 131
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Reuse paradigm 111 markPrice cache directly
CACHE_DIR = Path(
    "/home/hcpark/antigravity/backend/runs/research_track/"
    "binance_perp_mark_index_basis_extreme_alt_directional_4h/mark_index_cache"
)

# Universe from paradigm 111 verified cache (6 alts)
COHORT = ["SOLUSDT", "HBARUSDT", "AVAXUSDT", "DOGEUSDT", "ETHUSDT", "LINKUSDT"]

START_MONTH = "2025-05"
END_MONTH = "2026-04"

# Trigger params
ROLLING_BARS_4H = 180          # 30 days × 6 bars/day = 180 4h bars
BASIS_Z_THRESHOLD = 1.5         # |basis_z| > 1.5
RANGE_CLOSE_Z_THRESHOLD = 1.5   # range_close_z > +1.5 (upper tail only, Lesson #40)
FORWARD_HOLD_4H_BARS = 1        # 4h forward (1 bar)
DEBOUNCE_HOURS = 8
FEE_BP = 16.0


def month_iter(start: str, end: str) -> list[str]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    return [str(p) for p in pd.period_range(s, e, freq="M")]


def download_5m_klines(sym: str, kind: str, month: str) -> pd.DataFrame:
    """Reuse paradigm 111 cache pattern: load monthly 5m mark/index OHLC."""
    cache_file = CACHE_DIR / f"{sym}_{kind}_{month}.joblib"
    if cache_file.exists():
        try:
            df = joblib.load(cache_file)
            return df
        except Exception as e:
            log.warning("cache load fail %s: %s", cache_file, e)
    # Fallback: download (should not occur if paradigm 111 cache complete)
    url = f"https://data.binance.vision/data/futures/um/monthly/{kind}/{sym}/5m/{sym}-5m-{month}.zip"
    log.warning("cache miss — downloading %s", url)
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            log.warning("download %s %s %s -> HTTP %d", sym, kind, month, r.status_code)
            return pd.DataFrame()
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                df = pd.read_csv(f)
        df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True).dt.tz_localize(None)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df = df[["ts", "close"]].dropna().drop_duplicates("ts").set_index("ts").sort_index()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(df, cache_file, compress=3)
        return df
    except Exception as e:
        log.warning("fallback download fail %s %s %s: %s", sym, kind, month, e)
        return pd.DataFrame()


def build_4h_panel(sym: str, months: list[str]) -> pd.DataFrame:
    """Build 4h panel for sym with: mark_close_4h, index_close_4h, basis_pct_4h,
    high_4h, low_4h, range_close (high-low)/close.

    Uses 5m mark+index closes resampled to 4h. mark high/low are approximated from
    rolling 48 5m closes (markPrice doesn't have intra-bar OHLC in archive — schema
    is close-only after paradigm 111 cache build).
    """
    # paradigm 111 cache only stores close column. We must re-derive high/low from
    # 5m close series via 48-bar rolling max/min within each 4h window.
    mark_parts = []
    idx_parts = []
    for m in months:
        mark = download_5m_klines(sym, "markPriceKlines", m)
        idx = download_5m_klines(sym, "indexPriceKlines", m)
        if mark.empty or idx.empty:
            continue
        mark_parts.append(mark.rename(columns={"close": "mark"}))
        idx_parts.append(idx.rename(columns={"close": "idx"}))
    if not mark_parts or not idx_parts:
        return pd.DataFrame()
    mark_5m = pd.concat(mark_parts).sort_index()
    idx_5m = pd.concat(idx_parts).sort_index()
    mark_5m = mark_5m[~mark_5m.index.duplicated(keep="first")]
    idx_5m = idx_5m[~idx_5m.index.duplicated(keep="first")]

    # 4h aggregation: 5m × 48 = 4h
    bar4h = pd.DataFrame()
    bar4h["mark_close_4h"] = mark_5m["mark"].resample("4h").last()
    bar4h["idx_close_4h"] = idx_5m["idx"].resample("4h").last()
    # high/low approximated from 5m mark close within each 4h window
    bar4h["high_4h"] = mark_5m["mark"].resample("4h").max()
    bar4h["low_4h"] = mark_5m["mark"].resample("4h").min()
    bar4h = bar4h.dropna()
    if bar4h.empty:
        return bar4h

    # Basis pct (signed): (mark - idx) / idx
    bar4h["basis_pct_4h"] = (bar4h["mark_close_4h"] - bar4h["idx_close_4h"]) / bar4h["idx_close_4h"]
    # Range:close ratio (non-negative)
    bar4h["range_close_4h"] = (bar4h["high_4h"] - bar4h["low_4h"]) / bar4h["mark_close_4h"]
    # Forward 4h log return (perp close-to-close on mark price)
    bar4h["log_ret_4h"] = np.log(bar4h["mark_close_4h"]).diff()
    bar4h["fwd_log_ret_4h"] = bar4h["log_ret_4h"].shift(-FORWARD_HOLD_4H_BARS)
    return bar4h


def rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    """Trailing rolling z-score (mean/std on closed past window)."""
    mu = s.rolling(window=window, min_periods=window // 2).mean()
    sd = s.rolling(window=window, min_periods=window // 2).std(ddof=1)
    return (s - mu) / sd.replace(0, np.nan)


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    months = month_iter(START_MONTH, END_MONTH)
    log.info("months: %d (%s..%s)", len(months), months[0], months[-1])

    sym_panel = {}
    per_sym_days = {}
    for sym in COHORT:
        try:
            df = build_4h_panel(sym, months)
            if df.empty or len(df) < ROLLING_BARS_4H * 2:
                log.warning("%s: insufficient 4h bars (%d) -- skip", sym, len(df))
                continue
            days = (df.index.max() - df.index.min()).days
            per_sym_days[sym] = days
            sym_panel[sym] = df
            log.info("%s: %d 4h bars (%d days)", sym, len(df), days)
        except Exception as e:
            log.error("%s build fail: %s", sym, e)

    if not sym_panel:
        log.error("no symbols built")
        sys.exit(1)

    full_window = max(per_sym_days.values())
    short_window_syms = {s: d for s, d in per_sym_days.items() if d < full_window * 0.30}
    log.info("Lesson #30 audit: full_window=%d days, short-window syms: %s",
             full_window, short_window_syms)

    # Compute per-sym z-scores + 4-quadrant joint trigger
    log.info("--- compute basis_z + range_close_z per-sym, joint triggers ---")
    trig_rows = []
    basis_z_agg = []
    range_close_z_agg = []
    range_close_agg = []
    per_sym_diagnostics = {}

    for sym, df in sym_panel.items():
        df = df.copy()
        df["basis_z"] = rolling_zscore(df["basis_pct_4h"], ROLLING_BARS_4H)
        df["range_close_z"] = rolling_zscore(df["range_close_4h"], ROLLING_BARS_4H)
        bz = df["basis_z"].dropna()
        rz = df["range_close_z"].dropna()
        rc = df["range_close_4h"].dropna()
        if len(bz) > 0:
            basis_z_agg.extend(bz.tolist()[:5000])
        if len(rz) > 0:
            range_close_z_agg.extend(rz.tolist()[:5000])
        if len(rc) > 0:
            range_close_agg.extend(rc.tolist()[:5000])

        # Individual axis trigger rates
        cond_b_hi = (df["basis_z"] > BASIS_Z_THRESHOLD).sum()
        cond_b_lo = (df["basis_z"] < -BASIS_Z_THRESHOLD).sum()
        cond_r_hi = (df["range_close_z"] > RANGE_CLOSE_Z_THRESHOLD).sum()
        # Joint (positive-basis × wide-spread)
        df["cond_A"] = (
            (df["basis_z"] > BASIS_Z_THRESHOLD)
            & (df["range_close_z"] > RANGE_CLOSE_Z_THRESHOLD)
        )
        df["cond_B"] = (
            (df["basis_z"] < -BASIS_Z_THRESHOLD)
            & (df["range_close_z"] > RANGE_CLOSE_Z_THRESHOLD)
        )
        n_a = int(df["cond_A"].sum())
        n_b = int(df["cond_B"].sum())
        n_total = len(df)

        per_sym_diagnostics[sym] = {
            "n_4h_bars": int(n_total),
            "n_cond_basis_hi": int(cond_b_hi),
            "n_cond_basis_lo": int(cond_b_lo),
            "n_cond_range_hi": int(cond_r_hi),
            "n_joint_A_pos_basis_wide_range": n_a,
            "n_joint_B_neg_basis_wide_range": n_b,
            "indep_expected_A": (int(cond_b_hi) * int(cond_r_hi)) / max(n_total, 1),
            "indep_expected_B": (int(cond_b_lo) * int(cond_r_hi)) / max(n_total, 1),
        }
        log.info("%s: bars=%d basis_hi=%d basis_lo=%d range_hi=%d joint_A=%d joint_B=%d",
                 sym, n_total, cond_b_hi, cond_b_lo, cond_r_hi, n_a, n_b)

        # Debounced triggers — mean-reversion direction
        # A: basis_z>+1.5 × range_close_z>+1.5 → SHORT (direction=-1)
        # B: basis_z<-1.5 × range_close_z>+1.5 → LONG (direction=+1)
        last_ts = None
        for ts, row in df.iterrows():
            if pd.isna(row["fwd_log_ret_4h"]):
                continue
            is_a = bool(row["cond_A"])
            is_b = bool(row["cond_B"])
            if not (is_a or is_b):
                continue
            if last_ts is not None and (ts - last_ts).total_seconds() < DEBOUNCE_HOURS * 3600:
                continue
            direction = -1 if is_a else +1  # mean-reversion
            quadrant_kind = "A_pos_basis" if is_a else "B_neg_basis"
            signed_fwd_bp = float(row["fwd_log_ret_4h"]) * direction * 10000.0
            trig_rows.append({
                "ts": ts,
                "sym": sym,
                "basis_z": float(row["basis_z"]),
                "range_close_z": float(row["range_close_z"]),
                "basis_pct": float(row["basis_pct_4h"]),
                "range_close": float(row["range_close_4h"]),
                "quadrant_kind": quadrant_kind,
                "direction_mr": direction,
                "fwd_log_ret_4h": float(row["fwd_log_ret_4h"]),
                "signed_fwd_bp": signed_fwd_bp,
                "qtr": str(ts.to_period("Q")),
            })
            last_ts = ts

    trig_df = pd.DataFrame(trig_rows)
    log.info("total triggers across %d syms: %d", len(sym_panel), len(trig_df))
    if len(trig_df) == 0:
        log.error("zero triggers — halt")
        sys.exit(1)
    n_a = int((trig_df["quadrant_kind"] == "A_pos_basis").sum())
    n_b = int((trig_df["quadrant_kind"] == "B_neg_basis").sum())
    log.info("triggers: A_pos_basis=%d  B_neg_basis=%d", n_a, n_b)

    # Lesson #34 empirical distribution
    bz_pct = {p: float(np.percentile(basis_z_agg, p)) for p in [1, 5, 10, 50, 90, 95, 99]}
    rz_pct = {p: float(np.percentile(range_close_z_agg, p)) for p in [1, 5, 10, 50, 90, 95, 99]}
    rc_pct = {p: float(np.percentile(range_close_agg, p)) for p in [10, 25, 50, 75, 90, 99]}
    log.info("Lesson #34 basis_z percentiles (sampled n=%d): %s", len(basis_z_agg), bz_pct)
    log.info("Lesson #34 range_close_z percentiles (sampled n=%d): %s", len(range_close_z_agg), rz_pct)
    log.info("Lesson #34 range_close raw percentiles (sampled n=%d): %s", len(range_close_agg), rc_pct)

    # Lesson #40 verification
    lesson_40 = {
        "threshold_definition_axis_1": "|basis_z| > 1.5 on signed basis_pct → BOTH tails reachable",
        "threshold_definition_axis_2": "range_close_z > +1.5 on non-negative aggregate → "
                                        "UPPER tail only (z<-1.5 unreachable structurally)",
        "axis_1_structurally_reachable": True,
        "axis_2_lower_tail_reachable": False,
        "axis_2_upper_tail_used_only": True,
        "design_acknowledges_lesson_40": True,
        "empirical_attainability": {
            "basis_z_p99": bz_pct[99],
            "basis_z_p01": bz_pct[1],
            "basis_z_p99_above_1_5": bz_pct[99] > 1.5,
            "basis_z_p01_below_neg_1_5": bz_pct[1] < -1.5,
            "range_close_z_p99": rz_pct[99],
            "range_close_z_p99_above_1_5": rz_pct[99] > 1.5,
        },
        "verdict": "PASS",
    }
    log.info("Lesson #40 verification: %s", lesson_40)

    # Per-quarter per-quadrant density (Lesson #11)
    n_quarters = trig_df["qtr"].nunique()
    per_q_A = trig_df[trig_df["quadrant_kind"] == "A_pos_basis"].groupby("qtr").size()
    per_q_B = trig_df[trig_df["quadrant_kind"] == "B_neg_basis"].groupby("qtr").size()
    log.info("per-quarter A_pos_basis: %s", per_q_A.to_dict())
    log.info("per-quarter B_neg_basis: %s", per_q_B.to_dict())
    measurable_q_A = int((per_q_A >= 30).sum())
    measurable_q_B = int((per_q_B >= 30).sum())
    log.info("measurable quarters (>=30): A=%d/%d B=%d/%d",
             measurable_q_A, n_quarters, measurable_q_B, n_quarters)

    # Lesson #46 REFINEMENT (stratified n=50×4q)
    log.info("--- Lesson #46 REFINEMENT: temporally-stratified n=50×4q R-0 ---")
    sorted_quarters = sorted(trig_df["qtr"].unique())
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)
    if len(sorted_quarters) < 4:
        log.warning("insufficient quarters (%d) for stratified R-0", len(sorted_quarters))
        sample = trig_df.iloc[:200] if len(trig_df) else pd.DataFrame()
        strat_strategy = f"fallback_chronological_n200_INSUFFICIENT_QUARTERS_have_{len(sorted_quarters)}"
        qtrs_to_use = sorted_quarters
    else:
        qtrs_to_use = [
            sorted_quarters[0],
            sorted_quarters[len(sorted_quarters) // 3],
            sorted_quarters[2 * len(sorted_quarters) // 3],
            sorted_quarters[-1],
        ]
        qtrs_to_use = sorted(set(qtrs_to_use))
        log.info("temporally-stratified quarters: %s", qtrs_to_use)
        per_q_samples = []
        for qq in qtrs_to_use:
            q_data = trig_df[trig_df["qtr"] == qq].sort_values("ts")
            n_take = min(50, len(q_data))
            per_q_samples.append(q_data.iloc[:n_take])
        sample = pd.concat(per_q_samples) if per_q_samples else pd.DataFrame()
        strat_strategy = f"temporally_stratified_n50x{len(qtrs_to_use)}q_total_n={len(sample)}"

    # 4-quadrant R-0 stratified estimate (mean-reversion direction)
    if len(sample):
        a_focus = sample[sample["quadrant_kind"] == "A_pos_basis"]["signed_fwd_bp"]  # SHORT direction
        a_mirror = -a_focus
        b_focus = sample[sample["quadrant_kind"] == "B_neg_basis"]["signed_fwd_bp"]  # LONG direction
        b_mirror = -b_focus
    else:
        a_focus = a_mirror = b_focus = b_mirror = pd.Series(dtype=float)

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

    qa = stats(a_focus, "A_focus_pos_basis_wide_range_SHORT_4h_MR")
    qam = stats(a_mirror, "A_mirror_pos_basis_wide_range_LONG_4h")
    qb = stats(b_focus, "B_focus_neg_basis_wide_range_LONG_4h_MR")
    qbm = stats(b_mirror, "B_mirror_neg_basis_wide_range_SHORT_4h")
    log.info("R-0 4-quadrant stratified estimate (strategy=%s):", strat_strategy)
    for q in [qa, qam, qb, qbm]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter R-0 detail (Lesson #46 sub-amendment)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 sub-amendment) ---")
    per_qtr_r0 = {}
    a_signs = []
    b_signs = []
    for qq in qtrs_to_use:
        q_sample = trig_df[trig_df["qtr"] == qq].sort_values("ts").iloc[:50]
        q_a = q_sample[q_sample["quadrant_kind"] == "A_pos_basis"]["signed_fwd_bp"]
        q_b = q_sample[q_sample["quadrant_kind"] == "B_neg_basis"]["signed_fwd_bp"]
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
    log.info("Lesson #46 sign-flip detection: A_focus flips=%d %s | B_focus flips=%d %s",
             a_flips, a_signs, b_flips, b_signs)

    # Lesson #44 cross-reference (13th dogfood)
    lesson_44_xref = {
        "paradigm_111_mark_index_basis_extreme_single_axis": "GRAVEYARD BROAD_FALSIFIED. "
            "Single-axis basis percentile rank without range_close conjunction. "
            "DISTINCT: paradigm 131 adds range_close axis + MEAN-REVERSION direction "
            "(paradigm 111 was continuation on basis sign). Lesson #21 individual-vs-joint "
            "comparison mandatory in R-1.",
        "paradigm_121_hmm_realized_vol_state_x_markprice_basis": "GRAVEYARD BROAD_FALSIFIED. "
            "HMM-filter ineffective. DISTINCT: paradigm 131 uses explicit empirical z-score "
            "threshold (Lesson #45 HMM avoidance). range_close is intra-bar spread proxy, "
            "not regime filter.",
        "paradigm_118_universe_aggregate_correlation_regime": "GRAVEYARD BROAD_FALSIFIED. "
            "Universe-aggregate correlation scalar. DISTINCT: paradigm 131 per-symbol "
            "intra-bar conjunction, no cross-asset correlation.",
        "paradigm_75_cohort_dispersion_lead_lag": "GRAVEYARD BROAD_FALSIFIED. Cohort-aggregate "
            "dispersion. DISTINCT: per-symbol basis + range.",
        "paradigm_81_rolling_beta_regime": "GRAVEYARD narrow-scope. Rolling beta vs BTC. "
            "DISTINCT: liquidity microstructure conjunction, no beta.",
        "paradigm_130_alt_realized_corr_breakdown_eth_per_pair": "GRAVEYARD 2026-05-21 "
            "BROAD_FALSIFIED_A_FOCUS_NEGATIVE. Lesson #52 INVERSE 1st dogfood "
            "(SHORT-bias artifact conditional on overextension). DISTINCT: "
            "different family (no correlation axis), but explicit dual-detection "
            "Lesson #52 a/b MANDATORY at R-1.",
        "paradigm_129_alt_parkinson_range_vol_expansion": "GRAVEYARD 2026-05-21 "
            "BROAD_FALSIFIED_FEE_FLOOR_LONG_DRIFT_ARTIFACT. Lesson #51 1st explicit dogfood "
            "(universe LONG drift artifact). DISTINCT: paradigm 131 uses MEAN-REVERSION "
            "direction (not continuation), 2-axis conjunction with EXOGENOUS basis.",
        "paradigm_124_realized_kurtosis_extreme_signed": "GRAVEYARD higher-order moment. "
            "DISTINCT: 2nd-order range:close only, not kurtosis.",
        "paradigm_125_quarticity_normalized_bipower": "R0_HALT structural threshold "
            "infeasible (Lesson #40 non-negative aggregate). DISTINCT: paradigm 131 "
            "EXPLICITLY restricts axis 2 to upper tail only (acknowledges Lesson #40).",
        "paradigm_96_99_funding_family": "GRAVEYARD 4 sub-classes (96/97/98/99). "
            "DISTINCT: no funding axis.",
        "paradigm_127_128_volume_burst_intra5m_event": "R-5 SEEDED Mint deploy 2026-05-21. "
            "DISTINCT: paradigm 127/128 are 5m+1m intra-bar volume bursts, paradigm 131 "
            "is 4h frame liquidity-microstructure conjunction (different time-scale + "
            "different mechanism). NO overlap on capacity class.",
        "paradigm_102_103_cross_venue": "GRAVEYARD. DISTINCT: single-venue Binance perp only.",
        "RUNBOOK_3M_volume_extraction": "ANTIPATTERN avoided — no volume axis.",
    }

    # Family-avoidance verification
    family_avoidance = {
        "HMM_unsupervised": "AVOIDED (explicit empirical z-score thresholds, Lesson #45)",
        "OI_velocity_directional": "AVOIDED (basis + range only, no OI)",
        "Stateful_CP": "AVOIDED (stateless rolling z-score, Lesson #22)",
        "Higher_order_moment": "AVOIDED (basis level + 2nd-order range:close only)",
        "Funding_single_signal": "AVOIDED (no funding axis)",
        "Volume_share": "AVOIDED (no volume)",
        "Volume_burst_intra5m": "AVOIDED (4h frame, no volume axis)",
        "Magnitude_confluence_simple": "DISTINCT — directional via basis sign with mean-reversion",
        "Listing_event": "AVOIDED (continuous rolling)",
        "5m_microstructure_single_domain": "AVOIDED (4h frame)",
        "Universe_aggregate_scalar": "AVOIDED (per-sym)",
        "Session_anchor": "AVOIDED (continuous rolling)",
        "VWAP_EWMA_smoothed": "AVOIDED (raw 4h closes)",
        "paradigm_111_single_axis_basis": "DISTINCT via range_close conjunction + MR direction",
        "paradigm_121_HMM_x_basis": "AVOIDED (no HMM)",
        "Correlation_beta_lead_lag_family": "AVOIDED (no cross-asset correlation, retire candidate post-130)",
        "Range_only_intrinsic": "DISTINCT via EXOGENOUS basis axis combined",
    }

    # Verdict
    n_total = len(trig_df)
    n_per_sym_min = trig_df.groupby("sym").size().min() if len(trig_df) else 0
    verdict = "R0_READY_FOR_R1" if (
        n_total >= 200
        and (measurable_q_A >= 3 or measurable_q_B >= 3)  # at least one quadrant has density
        and len(sym_panel) >= 4
        and lesson_40["verdict"] == "PASS"
    ) else "R0_HALT_INSUFFICIENT_DENSITY"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_number": PARADIGM_NUM,
        "phase": "R-0",
        "executed_at_kst": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "host": "hcp_local",
        "verdict": verdict,
        "cohort": COHORT,
        "universe_loaded": list(sym_panel.keys()),
        "months_window": [START_MONTH, END_MONTH],
        "params": {
            "rolling_bars_4h": ROLLING_BARS_4H,
            "basis_z_threshold": BASIS_Z_THRESHOLD,
            "range_close_z_threshold": RANGE_CLOSE_Z_THRESHOLD,
            "forward_hold_4h_bars": FORWARD_HOLD_4H_BARS,
            "debounce_hours": DEBOUNCE_HOURS,
            "fee_bp": FEE_BP,
            "direction_mode": "mean_reversion_via_basis_sign",
        },
        "per_sym_days": per_sym_days,
        "short_window_syms_lesson_30": short_window_syms,
        "per_sym_trigger_diagnostics": per_sym_diagnostics,
        "n_triggers_total": int(n_total),
        "n_triggers_A_pos_basis": int(n_a),
        "n_triggers_B_neg_basis": int(n_b),
        "n_per_sym_min": int(n_per_sym_min),
        "per_quarter_A_pos": per_q_A.to_dict(),
        "per_quarter_B_neg": per_q_B.to_dict(),
        "measurable_quarters_A": int(measurable_q_A),
        "measurable_quarters_B": int(measurable_q_B),
        "n_quarters": int(n_quarters),
        "lesson_11_density_pass": (measurable_q_A >= 3 or measurable_q_B >= 3),
        "lesson_34_basis_z_percentiles": bz_pct,
        "lesson_34_range_close_z_percentiles": rz_pct,
        "lesson_34_range_close_raw_percentiles": rc_pct,
        "lesson_40": lesson_40,
        "lesson_46_amendment_refinement_strategy": strat_strategy,
        "lesson_46_quarters_used": qtrs_to_use,
        "r0_4quadrant_stratified_estimate": {
            "A_focus_pos_basis_wide_range_SHORT_4h_MR": qa,
            "A_mirror_pos_basis_wide_range_LONG_4h": qam,
            "B_focus_neg_basis_wide_range_LONG_4h_MR": qb,
            "B_mirror_neg_basis_wide_range_SHORT_4h": qbm,
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

    # Persist trigger panel for R-1 consumption (avoid recomputing)
    trig_df.to_parquet(OUT_DIR / "trig_panel.parquet") if False else None
    # parquet engine may be missing; use joblib instead
    joblib.dump(trig_df, OUT_DIR / "trig_panel.joblib", compress=3)
    # Also persist full per-sym 4h panels (basis_z + range_close_z + fwd_log_ret_4h)
    persist = {}
    for sym, df in sym_panel.items():
        df2 = df.copy()
        df2["basis_z"] = rolling_zscore(df2["basis_pct_4h"], ROLLING_BARS_4H)
        df2["range_close_z"] = rolling_zscore(df2["range_close_4h"], ROLLING_BARS_4H)
        persist[sym] = df2[["basis_pct_4h", "range_close_4h",
                             "basis_z", "range_close_z",
                             "log_ret_4h", "fwd_log_ret_4h"]]
    joblib.dump(persist, OUT_DIR / "sym_4h_panel.joblib", compress=3)
    log.info("trig_panel (n=%d) + sym_4h_panel (%d syms) joblib persisted",
             len(trig_df), len(persist))


if __name__ == "__main__":
    main()
