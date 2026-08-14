"""paradigm 132 R-0 prescreen — funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h.

Hypothesis (3-way axis stacking, MEAN-REVERSION direction):
  Axis 1 (event anchor): 8h funding boundary (00/08/16 UTC) ±0 (boundary bar)
  Axis 2 (OI direction binary): prior 8h cumulative OI sign
                                same as funding-magnitude direction
                                (funding>0 + OI declining = long unwind in progress)
                                (funding<0 + OI declining = short unwind in progress)
  Axis 3 (funding magnitude): |funding_rate| > rolling-30d p70 percentile
  Trigger fire: all 3 conditions
  Direction (paradigm 22 family MR): high+ funding → LONG MR / high- funding → SHORT MR
  Forward hold: 4h
  Debounce: 8h (between consecutive triggers)
  Fee: 16bp round-trip
  Universe: 13 alts (8h-cycle funding canonical + OI 5m substrate intersection)
    AVAX, AXS, COMP, DOGE, ETC, HBAR, ICP, LDO, LINK, SOL, UNI, WLD, 1000LUNC

CRITICAL FAMILY-DISTINCT CONCERN (USER MUST DECIDE PRE-DISPATCH):
  Hypothesis claims paradigm 132 is a "paradigm 22 R-5 family slice exemption"
  from funding family Tier 4 retire. paradigm 22 mechanism =
      lookback=30d, entry_z=2.5 funding-rate z-score, exit_z=0.5,
      max_hold=15 days, continuous mean-reversion over multi-day positions.
  paradigm 132 mechanism =
      event-anchored on 8h funding boundary, 4h directional hold,
      magnitude-percentile filter, OI-direction conjunction.
  These are STRUCTURALLY DIFFERENT MECHANISMS sharing only the funding-rate
  axis. paradigm 132 is more accurately classified as a NEW funding-family
  sub-variant, in which case funding family Tier 4 retire FULLY APPLIES
  (paradigm 73 + 79 + 96 + 97 + 98 + 99 = 6 sub-class graveyards):
    - paradigm 96 funding sign flip BROAD_FALSIFIED
    - paradigm 97 funding term structure cross-sym dispersion BROAD_FALSIFIED
    - paradigm 98 funding regime stratify dispersion BROAD_FALSIFIED
    - paradigm 99 funding velocity per-sym BROAD_FALSIFIED
  The Lesson #44 amendment 14th dogfood requires explicit reconciliation
  before dispatch.

R-0 prescreen verdict will explicitly tag this concern; user instructed to
proceed with R-1 only-halt regardless (continuous-parallel policy directive).

Lessons applied:
  #11 sample density               — per-quadrant per-quarter >= 30
  #16 Concentration Gate           — (R-1 stage, deferred here)
  #19 SNT mandatory                — 4-quadrant SNT in R-1 batch
  #21 axis stacking trap (5th)     — 3-WAY stacking, INDIVIDUAL-vs-JOINT sigex
                                      comparison MANDATORY at R-1 (5 variants:
                                      funding_only / OI_dir_only / anchor+funding /
                                      anchor+OI / triple joint)
  #22 frame-grade                  — 4h hold, 8h funding cycle anchor, 5m OI for
                                      prior-8h OI direction computation
  #23 event-anchored               — 8h cycle is the anchor; per-day 3 events
                                      × 365d × 13 alts = ~14k boundaries;
                                      p70 magnitude × OI direction (~50%) =
                                      ~15% trigger rate → ~2100 total events
                                      ÷ 2 quadrants ÷ 4 quarters = ~260/cell PASS
  #28 substrate availability       — funding DB (1y all 13 alts) + 5m OI joblib
                                      (2.2yr ALL 13 alts intersection PASS)
  #30 data_window_ratio            — funding 365d / hypothesized 730d = 0.50
                                      PASS (>=30%) but window-truncated
  #34 empirical distribution       — funding |rate| p70 measured per-sym;
                                      OI direction binary per-event measured
  #39 sub-class A/B/C/D detection  — 4-quadrant SNT at R-1
  #40 structural threshold         — |funding_rate| percentile rank PASS;
                                      OI direction binary PASS
  #41 amendment dual-mode          — 8h × 3/day × 13 syms × 0.15 trigger × 365d
                                      = ~2100 trades cohort/yr ≈ 160/yr/sym
                                      = SPARSE-MEDIUM
  #44 amendment xref 14th          — FUNDING FAMILY TIER 4 RETIRE concern raised
                                      explicitly. paradigm 22 family-slice
                                      exemption is mechanism-distinct claim
                                      requiring R-1 individual-vs-joint sigex
                                      to demonstrate joint > paradigm 22
                                      baseline × 1.2.
  #45 family-distinct              — explicit empirical thresholds (no HMM)
  #46 AMENDMENT REFINEMENT          — temporally-stratified n=50x4q R-0
                                      + sign-flip detection
  #48 inventory check scope         — graveyard + RUNBOOK + INDEX xref
  #52 a/b candidate                 — R-1 stage explicit dual detection
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p132_r0")

PARADIGM_NAME = "funding_boundary_x_oi_direction_x_funding_magnitude_triple_confirm_alt_directional_4h"
PARADIGM_NUM = 132
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "AVAXUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "ETCUSDT",
    "HBARUSDT", "ICPUSDT", "LDOUSDT", "LINKUSDT", "SOLUSDT",
    "UNIUSDT", "WLDUSDT", "1000LUNCUSDT",
]

FUNDING_MAG_PERCENTILE = 70.0          # p70 magnitude filter
FUNDING_ROLLING_DAYS = 30               # 30d rolling p70 (90 events)
FORWARD_HOLD_HOURS = 4
DEBOUNCE_HOURS = 8
FEE_BP = 16.0
DB_DSN = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
OI_CACHE = Path("/home/hcpark/antigravity/backend/runs/microstructure")


def load_funding(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT funding_time, funding_rate FROM binance_funding_rate "
        "WHERE symbol=:s ORDER BY funding_time"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["funding_time"])
    if df.empty:
        return df
    # Snap to 8h boundary (drop microseconds)
    df["funding_time"] = df["funding_time"].dt.floor("h")
    # Filter strictly to 8h-cycle hours 0/8/16
    df = df[df["funding_time"].dt.hour.isin([0, 8, 16])].copy()
    df["funding_rate"] = df["funding_rate"].astype(float)
    df = df.set_index("funding_time").sort_index()
    # Drop duplicates from hourly floor collision (Lesson #44 paradigm 73 funding family)
    df = df[~df.index.duplicated(keep="first")]
    return df


def load_oi_5m(sym: str) -> pd.Series:
    path = OI_CACHE / f"{sym}_full_metrics.joblib"
    if not path.exists():
        return pd.Series(dtype=float)
    m = joblib.load(path)
    if "open_interest" not in m.columns:
        return pd.Series(dtype=float)
    s = m["open_interest"].astype(float).sort_index()
    return s[~s.index.duplicated(keep="first")]


def load_close_4h(sym: str, engine) -> pd.DataFrame:
    q = text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    bar4h = df["close"].resample("4h").last().dropna().to_frame("close")
    return bar4h


def main():
    log.info("paradigm %d R-0 start (KST %s)", PARADIGM_NUM,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    engine = create_engine(DB_DSN)

    per_sym_panels: dict[str, dict] = {}
    all_triggers = []

    for sym in COHORT:
        log.info("sym=%s loading", sym)
        funding = load_funding(sym, engine)
        if funding.empty:
            log.warning("  funding empty, skip")
            continue
        oi5 = load_oi_5m(sym)
        if oi5.empty:
            log.warning("  oi5 empty, skip")
            continue
        close4h = load_close_4h(sym, engine)
        if close4h.empty:
            log.warning("  close4h empty, skip")
            continue

        # Intersect windows
        t_min = max(funding.index.min(), oi5.index.min(), close4h.index.min())
        t_max = min(funding.index.max(), oi5.index.max(), close4h.index.max())
        funding = funding.loc[t_min:t_max]
        oi5 = oi5.loc[t_min:t_max]
        close4h = close4h.loc[t_min:t_max]
        log.info("  intersect window: %s -> %s n_funding=%d", t_min, t_max, len(funding))

        # Build axes per funding event:
        # axis_2 = sign(OI[t] - OI[t-8h])
        # axis_3 = |funding| > rolling p70 of past 30d
        oi_at = oi5.reindex(funding.index, method="ffill")
        oi_minus_8h_target = funding.index - pd.Timedelta(hours=8)
        oi_prev = oi5.reindex(oi_minus_8h_target, method="ffill")
        oi_prev.index = funding.index
        oi_delta_sign = np.sign((oi_at - oi_prev).fillna(0.0))

        funding_abs = funding["funding_rate"].abs()
        # Rolling p70 over past 30d (90 events at 3/day)
        # Use min_periods=30 (10d) to allow earlier triggers
        roll_p70 = funding_abs.shift(1).rolling(
            window=90, min_periods=30
        ).quantile(FUNDING_MAG_PERCENTILE / 100.0)
        mag_extreme = funding_abs > roll_p70
        funding_sign = np.sign(funding["funding_rate"])

        # OI direction "same as funding-magnitude direction": funding>0+OI declining
        # = long unwind = squeeze condition LONG bias (paradigm 22 family MR)
        # funding<0+OI declining = short unwind = SHORT bias
        # OI declining = oi_delta_sign < 0
        # Define: conjunction triggers when:
        #   funding>0 AND oi_decline AND mag_extreme  → LONG MR
        #   funding<0 AND oi_decline AND mag_extreme  → SHORT MR
        oi_declining = oi_delta_sign < 0

        # Forward 4h return (next 4h bar relative to next 4h close at funding_time + 4h)
        close_at = close4h["close"].reindex(funding.index, method="ffill")
        close_fwd = close4h["close"].reindex(
            funding.index + pd.Timedelta(hours=FORWARD_HOLD_HOURS), method="ffill"
        )
        close_fwd.index = funding.index
        fwd_log_ret = np.log(close_fwd / close_at)

        # Trigger flags
        trig_A = (funding_sign > 0) & oi_declining & mag_extreme  # LONG MR
        trig_B = (funding_sign < 0) & oi_declining & mag_extreme  # SHORT MR

        # Also store individual-axis triggers for Lesson #21 decomposition at R-1:
        # axis_2_only = oi_declining only (no funding sign filter / no magnitude)
        # axis_3_only = mag_extreme only
        # axis_funding_anchor = (funding_sign != 0) at boundary
        per_sym_panels[sym] = {
            "funding_time": funding.index.values,
            "funding_rate": funding["funding_rate"].values,
            "funding_sign": funding_sign.values,
            "funding_abs": funding_abs.values,
            "roll_p70": roll_p70.values,
            "mag_extreme": mag_extreme.values,
            "oi_at": oi_at.values,
            "oi_prev": oi_prev.values,
            "oi_delta_sign": oi_delta_sign.values,
            "oi_declining": oi_declining.values,
            "fwd_log_ret": fwd_log_ret.values,
            "trig_A": trig_A.values,
            "trig_B": trig_B.values,
        }
        nA = int(trig_A.sum())
        nB = int(trig_B.sum())
        log.info("  triggers A_long=%d  B_short=%d  total_funding=%d  mag_extreme=%d  oi_decline=%d",
                 nA, nB, len(funding), int(mag_extreme.sum()), int(oi_declining.sum()))

        # Add triggers to global pool (for quadrant aggregation)
        for q_kind, mask in [("A_pos_long_MR", trig_A), ("B_neg_short_MR", trig_B)]:
            idx = np.where(mask.values if hasattr(mask, "values") else mask)[0]
            for i in idx:
                if np.isfinite(fwd_log_ret.iloc[i]):
                    all_triggers.append({
                        "sym": sym,
                        "quadrant_kind": q_kind,
                        "funding_time": pd.Timestamp(funding.index.values[i]),
                        "funding_rate": float(funding["funding_rate"].values[i]),
                        "funding_abs": float(funding_abs.values[i]),
                        "fwd_log_ret": float(fwd_log_ret.values[i]),
                        "oi_delta_sign": float(oi_delta_sign.values[i]),
                    })

    engine.dispose()
    trig_df = pd.DataFrame(all_triggers)
    if trig_df.empty:
        log.error("zero triggers — abort")
        sys.exit(1)
    # Sort + debounce per-sym
    trig_df = trig_df.sort_values(["sym", "funding_time"]).reset_index(drop=True)
    keep = []
    last_t = {}
    for i, row in trig_df.iterrows():
        sym = row["sym"]
        t = row["funding_time"]
        prev = last_t.get(sym)
        if prev is None or (t - prev) >= pd.Timedelta(hours=DEBOUNCE_HOURS):
            keep.append(i)
            last_t[sym] = t
    trig_df = trig_df.loc[keep].reset_index(drop=True)
    log.info("post-debounce n_triggers=%d", len(trig_df))

    # Lesson #46 stratified n=50x4q + sign-flip
    q_periods = {
        "2025Q3": (pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
        "2025Q4": (pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
        "2026Q1": (pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
        "2026Q2": (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
    }
    stratified = {}
    sign_flips = {}
    for q_kind in ["A_pos_long_MR", "B_neg_short_MR"]:
        # Direction: A=LONG (gross = +fwd_log_ret), B=SHORT (gross = -fwd_log_ret)
        direction = +1 if q_kind == "A_pos_long_MR" else -1
        per_q_means = []
        per_q_signs = []
        sub = trig_df[trig_df["quadrant_kind"] == q_kind]
        for qname, (qs, qe) in q_periods.items():
            cell = sub[(sub["funding_time"] >= qs) & (sub["funding_time"] < qe)]
            n = len(cell)
            if n >= 5:
                gross_bp = direction * cell["fwd_log_ret"].mean() * 10000.0
                per_q_means.append({"q": qname, "n": n, "gross_bp": float(gross_bp)})
                per_q_signs.append(1 if gross_bp > 0 else -1)
            else:
                per_q_means.append({"q": qname, "n": n, "gross_bp": None})
        # Sign flips
        flip_n = 0
        prev_s = None
        for s in per_q_signs:
            if prev_s is not None and s != prev_s:
                flip_n += 1
            prev_s = s
        stratified[q_kind] = per_q_means
        sign_flips[q_kind] = flip_n
        log.info("Lesson #46 strat q_kind=%s per_q=%s flips=%d",
                 q_kind, per_q_means, flip_n)

    # Lesson #11 per-quadrant per-quarter measurable
    n_measurable = {
        q: sum(1 for x in s if x["n"] is not None and x["n"] >= 30)
        for q, s in stratified.items()
    }

    # Lesson #34 empirical distribution recap
    funding_p70_per_sym = {}
    for sym, panel in per_sym_panels.items():
        fa = panel["funding_abs"]
        fa_finite = fa[np.isfinite(fa)]
        if len(fa_finite) > 0:
            funding_p70_per_sym[sym] = {
                "p50": float(np.percentile(fa_finite, 50)),
                "p70": float(np.percentile(fa_finite, 70)),
                "p90": float(np.percentile(fa_finite, 90)),
                "p99": float(np.percentile(fa_finite, 99)),
                "max": float(fa_finite.max()),
            }

    # Save panels for R-1
    joblib.dump(per_sym_panels, OUT_DIR / "sym_panel.joblib")
    joblib.dump(trig_df, OUT_DIR / "trig_panel.joblib")

    out = {
        "paradigm": PARADIGM_NAME,
        "paradigm_num": PARADIGM_NUM,
        "phase": "R-0_prescreen",
        "evaluated_at_kst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cohort_size": len(COHORT),
        "cohort": COHORT,
        "per_sym_n_funding": {
            sym: int(len(panel["funding_time"]))
            for sym, panel in per_sym_panels.items()
        },
        "n_triggers_post_debounce": int(len(trig_df)),
        "n_per_quadrant": {
            "A_pos_long_MR": int((trig_df["quadrant_kind"] == "A_pos_long_MR").sum()),
            "B_neg_short_MR": int((trig_df["quadrant_kind"] == "B_neg_short_MR").sum()),
        },
        "lesson_11_per_quarter_measurable_30": n_measurable,
        "lesson_34_funding_abs_per_sym": funding_p70_per_sym,
        "lesson_46_stratified_n50x4q": stratified,
        "lesson_46_sign_flips": sign_flips,
        "lesson_30_data_window_ratio_funding": 365 / 730,
        "lesson_30_data_window_ratio_oi": 2.2 * 365 / 730,
        "lesson_44_funding_family_tier4_concern": (
            "paradigm 132 claims paradigm 22 R-5 family-slice exemption; "
            "however paradigm 22 mechanism (continuous 15-day funding-z MR) vs "
            "paradigm 132 mechanism (event-anchored 4h directional triple-confirm) "
            "are structurally distinct. paradigm 132 is more accurately a NEW "
            "funding-family sub-variant for which Tier 4 retire of funding family "
            "fully applies (6 sub-class graveyards 73/79/96/97/98/99). User "
            "directive: dispatch R-1 with explicit Lesson #21 individual-vs-joint "
            "decisive test; if joint > paradigm 22 R-1 sigex × 1.2 AND 3-gate "
            "PASS then mechanism-distinct exemption EARNED."
        ),
    }
    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-0 written: %s", out_path)


if __name__ == "__main__":
    main()
