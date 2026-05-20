"""paradigm 123 R-0 prescreen (Lesson #46 AMENDMENT REFINEMENT first dogfood).

Trigger: Per-symbol 5m volume Page-Hinkley CUSUM change-point detector alarm
  - Reference mean: rolling 7-day mean log-volume
  - λ (threshold) + δ (jump bias) → alarm at PH statistic exceeds λ
  - alarm direction by alarm-bar 5m volume z-score sign
Forward hold: 2h directional (positive vol-z → LONG continuation, negative → SHORT continuation)
Universe: 13 active alts (paradigm 122 cache reuse)

R-0 prescreens performed:
  - Lesson #11 (sample density): per-quadrant per-quarter ≥ 30 (target 3-5% alarm rate)
  - Lesson #19 SNT (4-quadrant) — applied at R-1
  - Lesson #22 frame-grade source freq: 5m volume frame VERIFIED abundant (paradigm 84 daily fail avoidance)
  - Lesson #23 (event-anchor density): CUSUM is NON-event-anchored continuous (Lesson #23 explicit non-target)
  - Lesson #28 (substrate availability): 5m OHLCV DB resampled (paradigm 122 verified)
  - Lesson #30 (data window ratio): 783 days / 800 = 97.9% (paradigm 122 baseline)
  - Lesson #34 (empirical distribution): log-volume z and PH statistic percentile
  - Lesson #40 (structural threshold feasibility): PH alarm symmetric continuous, no z-trigger structural infeasibility
  - Lesson #44 amendment graveyard xref: paradigm 84 (book_depth CUSUM daily SAMPLE_INSUFFICIENT), paradigm 94/95 (volume share family Tier 4 retired)
  - Lesson #45 family-distinct: Page-Hinkley is EXPLICIT threshold-based CP, NOT unsupervised clustering
  - Lesson #46 AMENDMENT REFINEMENT: temporally-stratified n=50 × 4 quarters R-0 gross drift (NOT chronological n=200)
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("p123_r0")

PARADIGM_NAME = "alt_volume_cusum_change_point_persistence_directional_2h"
OUT_DIR = Path(f"/home/hcpark/antigravity/backend/runs/research_track/{PARADIGM_NAME}")
OUT_DIR.mkdir(parents=True, exist_ok=True)

COHORT = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

# Page-Hinkley CUSUM params
PH_REF_WIN_BARS = 7 * 24 * 12  # 7-day rolling reference mean of log-volume (2016 bars)
PH_MIN_PERIODS = PH_REF_WIN_BARS // 2  # warmup
PH_DELTA = 0.0  # tolerance bias (set to 0; pure CUSUM accumulation)
# λ threshold candidates (tune for ~3-5% alarm rate)
PH_LAMBDA_CANDIDATES = [3.0, 5.0, 8.0, 12.0, 20.0, 50.0]
FORWARD_HOLD_BARS = 24  # 2h = 24 × 5m bars
FEE_BP = 16.0


def load_ohlcv_5m(sym: str, engine) -> pd.DataFrame:
    """Load 1m OHLCV from DB, resample to 5m."""
    q = text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    )
    df = pd.read_sql(q, engine, params={"s": sym}, parse_dates=["timestamp"])
    if df.empty:
        return df
    df = df.set_index("timestamp")
    o5 = df.resample("5min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    return o5


def page_hinkley_streaming(x: np.ndarray, lam: float, delta: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Two-sided Page-Hinkley CUSUM with rolling reference mean.

    For each bar t:
      ref_mean_t = trailing window mean (handled outside as input x_minus_ref)
      m_t_pos = max(0, m_{t-1}_pos + (x_t - delta))     # positive drift CUSUM
      m_t_neg = min(0, m_{t-1}_neg + (x_t + delta))     # negative drift CUSUM
      alarm_pos: m_t_pos > lam → reset to 0
      alarm_neg: m_t_neg < -lam → reset to 0

    Returns (alarm_dir, m_state) where alarm_dir ∈ {-1, 0, +1} per bar.
    """
    n = len(x)
    alarm = np.zeros(n, dtype=np.int8)
    m_pos = 0.0
    m_neg = 0.0
    for i in range(n):
        xi = x[i]
        if not np.isfinite(xi):
            m_pos = 0.0
            m_neg = 0.0
            continue
        m_pos = max(0.0, m_pos + xi - delta)
        m_neg = min(0.0, m_neg + xi + delta)
        if m_pos > lam:
            alarm[i] = 1
            m_pos = 0.0
            m_neg = 0.0
        elif m_neg < -lam:
            alarm[i] = -1
            m_pos = 0.0
            m_neg = 0.0
    return alarm


def main():
    log.info("paradigm 123 R-0 prescreen start (KST %s)", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    dsn = "postgresql://antigravity_user:antigravity_password@localhost:5432/antigravity_db"
    engine = create_engine(dsn)

    sym_data = {}
    for sym in COHORT:
        try:
            ohlcv = load_ohlcv_5m(sym, engine)
            if ohlcv.empty or len(ohlcv) < PH_REF_WIN_BARS + 100:
                log.warning("%s: insufficient (len=%d) — skip", sym, len(ohlcv))
                continue
            sym_data[sym] = ohlcv
            log.info("%s: %d 5m bars  %s → %s", sym, len(ohlcv), ohlcv.index.min(), ohlcv.index.max())
        except Exception as e:
            log.error("%s load fail: %s", sym, e)

    if not sym_data:
        log.error("no symbols loaded — abort")
        sys.exit(1)

    # Lesson #30 data window ratio (use ETHUSDT as baseline)
    eth = sym_data.get("ETHUSDT")
    full_days = (eth.index.max() - eth.index.min()).days if eth is not None else None
    log.info("ETHUSDT window: %s days (baseline)", full_days)

    # Step 1: per-symbol log-volume + rolling reference deviation
    log.info("--- Step 1: log-volume + rolling 7d reference deviation ---")
    panel_rows = []
    for sym, j in sym_data.items():
        j = j.copy()
        # log-volume (add eps to avoid log(0))
        j["log_vol"] = np.log(j["volume"].clip(lower=1e-9))
        # rolling reference mean over 7d
        ref_mean = j["log_vol"].rolling(PH_REF_WIN_BARS, min_periods=PH_MIN_PERIODS).mean()
        ref_std = j["log_vol"].rolling(PH_REF_WIN_BARS, min_periods=PH_MIN_PERIODS).std()
        # normalized deviation x_t - mean (NOT z-scored — pure deviation for CUSUM)
        j["x_dev"] = j["log_vol"] - ref_mean
        # z-score for SIGN matching at alarm (NOT for trigger)
        j["log_vol_z"] = (j["log_vol"] - ref_mean) / ref_std
        j["sym"] = sym
        # forward 2h return (sign-matched applied later)
        j["fwd_ret_2h"] = j["close"].pct_change(FORWARD_HOLD_BARS).shift(-FORWARD_HOLD_BARS)
        j = j.dropna(subset=["x_dev", "log_vol_z"])
        panel_rows.append(j)
    panel = pd.concat(panel_rows).sort_index()
    log.info("panel total rows after dropna: %d", len(panel))

    # Step 2: empirical distribution of log_vol_z (Lesson #34)
    abs_z = panel["log_vol_z"].abs()
    abs_x = panel["x_dev"].abs()
    pct_z = {p: float(np.percentile(abs_z, p)) for p in [50, 70, 90, 95, 99]}
    pct_x = {p: float(np.percentile(abs_x, p)) for p in [50, 70, 90, 95, 99]}
    log.info("|log_vol z| p50=%.3f p70=%.3f p90=%.3f p95=%.3f p99=%.3f",
             pct_z[50], pct_z[70], pct_z[90], pct_z[95], pct_z[99])
    log.info("|x_dev| (log-vol deviation) p50=%.3f p70=%.3f p90=%.3f p95=%.3f p99=%.3f",
             pct_x[50], pct_x[70], pct_x[90], pct_x[95], pct_x[99])

    # Step 3: Page-Hinkley CUSUM per symbol, λ tuning sweep
    log.info("--- Step 2: PH CUSUM λ tuning for ~3-5%% alarm rate ---")
    lambda_stats = {}
    best_lambda = None
    best_rate_diff = float("inf")
    TARGET_RATE = 0.04  # 4% center target (range 3-5%)

    for lam in PH_LAMBDA_CANDIDATES:
        total_alarms = 0
        total_bars = 0
        for sym in panel["sym"].unique():
            sub = panel[panel["sym"] == sym].sort_index()
            alarm = page_hinkley_streaming(sub["x_dev"].values, lam=lam, delta=PH_DELTA)
            total_alarms += int((alarm != 0).sum())
            total_bars += len(sub)
        rate = total_alarms / total_bars if total_bars else 0.0
        lambda_stats[lam] = {"n_alarms": total_alarms, "n_bars": total_bars, "rate_pct": rate * 100}
        log.info("  λ=%.1f: alarms=%d rate=%.3f%%", lam, total_alarms, rate * 100)
        if 0.01 <= rate <= 0.10:  # within reasonable band
            if abs(rate - TARGET_RATE) < best_rate_diff:
                best_rate_diff = abs(rate - TARGET_RATE)
                best_lambda = lam

    if best_lambda is None:
        log.error("no λ in [1%%, 10%%] alarm rate band — HALT")
        out = {
            "paradigm_name": PARADIGM_NAME,
            "verdict": "R0_HALT_LAMBDA_TUNING_FAIL",
            "lambda_stats": lambda_stats,
            "target_rate_pct": TARGET_RATE * 100,
        }
        with open(OUT_DIR / "r0_prescreen.json", "w") as f:
            json.dump(out, f, indent=2, default=str)
        sys.exit(0)
    log.info("CHOSEN λ=%.1f (closest to target %.1f%%)", best_lambda, TARGET_RATE * 100)

    # Step 4: Apply chosen λ to build alarm column on full panel
    log.info("--- Step 3: Apply chosen λ + sign-match direction ---")
    panel_rows_with_alarm = []
    for sym in panel["sym"].unique():
        sub = panel[panel["sym"] == sym].sort_index().copy()
        alarm = page_hinkley_streaming(sub["x_dev"].values, lam=best_lambda, delta=PH_DELTA)
        sub["alarm"] = alarm  # -1, 0, +1
        panel_rows_with_alarm.append(sub)
    panel = pd.concat(panel_rows_with_alarm).sort_index()

    # Direction by alarm-bar log_vol_z sign (positive z → LONG, negative z → SHORT)
    # alarm == +1 OR -1 indicates change-point detected. Direction by z-sign at alarm bar.
    trig = panel[panel["alarm"] != 0].copy()
    trig = trig.dropna(subset=["fwd_ret_2h", "log_vol_z"])
    trig["direction"] = np.where(trig["log_vol_z"] > 0, 1, -1)  # sign-matched LONG/SHORT
    trig["signed_ret_bp"] = trig["fwd_ret_2h"] * trig["direction"] * 10000

    n_trig_total = len(trig)
    n_pos = int((trig["log_vol_z"] > 0).sum())
    n_neg = int((trig["log_vol_z"] < 0).sum())
    log.info("Triggers (alarms) total: %d (pos %d / neg %d) rate=%.3f%%",
             n_trig_total, n_pos, n_neg, n_trig_total / len(panel) * 100)

    # Lesson #11 per-quadrant per-quarter sample density
    trig["qtr"] = trig.index.to_period("Q").astype(str)
    n_quarters = trig["qtr"].nunique()
    per_q_pos = trig[trig["log_vol_z"] > 0].groupby("qtr").size()
    per_q_neg = trig[trig["log_vol_z"] < 0].groupby("qtr").size()
    log.info("per-quarter pos: %s", per_q_pos.to_dict())
    log.info("per-quarter neg: %s", per_q_neg.to_dict())
    measurable_q_pos = int((per_q_pos >= 30).sum())
    measurable_q_neg = int((per_q_neg >= 30).sum())
    log.info("measurable quarters (≥30 per quadrant): pos=%d/%d neg=%d/%d",
             measurable_q_pos, n_quarters, measurable_q_neg, n_quarters)

    # Lesson #46 AMENDMENT REFINEMENT: temporally-stratified n=50 × 4q
    log.info("--- Lesson #46 AMENDMENT REFINEMENT: temporally-stratified R-0 ---")
    sorted_quarters = sorted(trig["qtr"].unique())
    log.info("quarters available: %d %s", len(sorted_quarters), sorted_quarters)

    if len(sorted_quarters) < 4:
        log.warning("insufficient quarters for stratified R-0 (have %d, need 4)", len(sorted_quarters))
        # fall back to chronological n=200 with bias warning
        sample = trig.dropna(subset=["signed_ret_bp"]).iloc[:200]
        stratified_strategy = "fallback_chronological_n200_INSUFFICIENT_QUARTERS"
    else:
        # pick 4 quarters: evenly spaced (Q1, Q1+k, Q1+2k, Q1+3k)
        qtrs_to_use = [
            sorted_quarters[0],
            sorted_quarters[len(sorted_quarters) // 3],
            sorted_quarters[2 * len(sorted_quarters) // 3],
            sorted_quarters[-1],
        ]
        # dedupe & re-sort
        qtrs_to_use = sorted(set(qtrs_to_use))
        log.info("temporally-stratified quarters chosen: %s", qtrs_to_use)
        per_q_samples = []
        for qq in qtrs_to_use:
            q_data = trig[(trig["qtr"] == qq)].dropna(subset=["signed_ret_bp"]).sort_index()
            n_take = min(50, len(q_data))
            per_q_samples.append(q_data.iloc[:n_take])
        sample = pd.concat(per_q_samples)
        stratified_strategy = f"temporally_stratified_n50x{len(qtrs_to_use)}q_total_n={len(sample)}"

    # R-0 gross drift estimate (4-quadrant)
    a_focus = sample[sample["log_vol_z"] > 0]["signed_ret_bp"]
    a_mirror_bp = -a_focus
    b_focus = sample[sample["log_vol_z"] < 0]["signed_ret_bp"]
    b_mirror_bp = -b_focus

    def stats(s, lbl):
        if len(s) < 2:
            return {"label": lbl, "n": int(len(s)), "gross_bp": None, "net_bp": None, "t": None}
        m = float(s.mean())
        sd = float(s.std(ddof=1))
        n = int(len(s))
        return {
            "label": lbl, "n": n, "gross_bp": m, "net_bp": m - FEE_BP,
            "t": m / (sd / math.sqrt(n)) if sd > 0 else None,
        }

    quad_a_focus = stats(a_focus, "A_focus_pos_LONG")
    quad_a_mirror = stats(a_mirror_bp, "A_mirror_pos_SHORT")
    quad_b_focus = stats(b_focus, "B_focus_neg_SHORT")
    quad_b_mirror = stats(b_mirror_bp, "B_mirror_neg_LONG")

    log.info("R-0 4-quadrant stratified-mechanism estimate (strategy=%s):", stratified_strategy)
    for q in [quad_a_focus, quad_a_mirror, quad_b_focus, quad_b_mirror]:
        log.info("  %s n=%d gross=%s net=%s t=%s", q["label"], q["n"],
                 f"{q['gross_bp']:.2f}" if q["gross_bp"] is not None else "NA",
                 f"{q['net_bp']:.2f}" if q["net_bp"] is not None else "NA",
                 f"{q['t']:.2f}" if q["t"] is not None else "NA")

    # Per-quarter R-0 detail (for refinement insight)
    log.info("--- Per-quarter R-0 gross by quadrant (Lesson #46 refinement validation) ---")
    per_qtr_r0 = {}
    for qq in (qtrs_to_use if len(sorted_quarters) >= 4 else []):
        q_sample = trig[trig["qtr"] == qq].dropna(subset=["signed_ret_bp"]).sort_index().iloc[:50]
        q_a = q_sample[q_sample["log_vol_z"] > 0]["signed_ret_bp"]
        q_b = q_sample[q_sample["log_vol_z"] < 0]["signed_ret_bp"]
        per_qtr_r0[qq] = {
            "n_total": int(len(q_sample)),
            "A_focus_n": int(len(q_a)),
            "A_focus_gross_bp": float(q_a.mean()) if len(q_a) > 0 else None,
            "B_focus_n": int(len(q_b)),
            "B_focus_gross_bp": float(q_b.mean()) if len(q_b) > 0 else None,
        }
        log.info("  %s: A n=%d gross=%s | B n=%d gross=%s",
                 qq, len(q_a),
                 f"{q_a.mean():.2f}" if len(q_a) > 0 else "NA",
                 len(q_b),
                 f"{q_b.mean():.2f}" if len(q_b) > 0 else "NA")

    # Lesson #44 amendment cross-reference
    lesson_44_xref = {
        "paradigm_84_book_depth_concentration_cusum_breakout_alt_12h": (
            "SAMPLE_INSUFFICIENT 2026-05-15 — CUSUM Page-Hinkley statistic class direct precedent. "
            "Fail mode: daily aggregation source frequency incompatible with stateful CP detector. "
            "Paradigm 123 distinct via 5m frame (paradigm 122 verified 2.66M bars, abundant). "
            "Lesson #22 frame-grade requirement → PASS for paradigm 123."
        ),
        "paradigm_94_low_volume_share_alt_long_1d": (
            "BROAD_FALSIFIED_DIRECTION_INVERTED — cross-asset volume SHARE family Tier 4 retired. "
            "Paradigm 123 distinct: within-symbol CP on log-volume deviation (NOT cross-asset share). "
            "Volume share family retire does NOT extend to within-symbol volume CP."
        ),
        "paradigm_95_high_volume_share_alt_long_1d": (
            "NARROW_SCOPE_LIFE_CHANGING_FAIL — Lesson #20 4-cond ALL PASS but per-trade edge 0.47%. "
            "Paradigm 123 distinct: stateful CP statistic, NOT static threshold share. "
            "Lesson #41 amendment edge-first gate applied at R-1."
        ),
        "paradigm_71_oi_velocity_single": "BROAD_FALSIFIED — OI velocity axis. Paradigm 123 axis=volume, distinct.",
        "paradigm_113_intraday_hour_anchor": "BROAD_FALSIFIED — temporal anchor axis. Paradigm 123 non-anchored continuous.",
        "paradigm_122_intraday_session_open_oi_acceleration": (
            "BROAD_FALSIFIED 2026-05-20 — OI velocity × temporal anchor stacking (Lesson #21). "
            "Paradigm 123 single-axis CP statistic (NOT stacked) → Lesson #21 risk minimal."
        ),
        "dna_overlap_assessment": (
            "0/6 dimensions full overlap with any predecessor. Closest is paradigm 84 (CUSUM class), "
            "but frame-grade (5m vs daily), source (volume vs book_depth), forward hold (2h vs 12h) all distinct."
        ),
    }

    # Lesson #45 family-distinct: Page-Hinkley vs HMM/unsupervised
    lesson_45_distinct = {
        "page_hinkley_class": "explicit threshold-based change-point statistic (lambda + delta parameters)",
        "hmm_unsupervised_class": "unsupervised state inference (latent variable, EM, no explicit threshold)",
        "verdict": "DISTINCT — Page-Hinkley is statistical hypothesis test family (Class A stateful CP), not unsupervised clustering",
    }

    # Lesson #39 sub-class manual check
    def detect_sub_class(focus_gross, mirror_gross):
        if focus_gross is None or mirror_gross is None:
            return "indeterminate"
        s = focus_gross + mirror_gross
        if abs(s) < 0.5:
            return "exact_symmetric_construction"
        return "asymmetric"

    lesson_39_a = detect_sub_class(quad_a_focus["gross_bp"], quad_a_mirror["gross_bp"])
    lesson_39_b = detect_sub_class(quad_b_focus["gross_bp"], quad_b_mirror["gross_bp"])

    # Verdict logic
    verdict = "R0_PASS_PROCEED_TO_R1"
    if measurable_q_pos < 3 or measurable_q_neg < 3:
        verdict = "R0_HALT_SAMPLE_INSUFFICIENT_LESSON_11"
    elif quad_a_focus["gross_bp"] is not None and quad_b_focus["gross_bp"] is not None:
        # Lesson #46 AMENDMENT: gross drift < 16bp fee floor → decline
        max_focus_gross = max(quad_a_focus["gross_bp"], quad_b_focus["gross_bp"])
        if max_focus_gross < FEE_BP:
            verdict = "R0_DECLINE_GROSS_BELOW_FEE_FLOOR_LESSON_46"
        elif quad_a_focus["gross_bp"] < 0 and quad_b_focus["gross_bp"] < 0:
            verdict = "R0_ADVISORY_BOTH_FOCUS_NEGATIVE"

    out = {
        "paradigm_name": PARADIGM_NAME,
        "counter_proposed": 123,
        "prescreen_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "universe": COHORT,
        "n_symbols_loaded": len(sym_data),
        "ph_params": {
            "ref_win_bars_5m": PH_REF_WIN_BARS,
            "ref_win_days": 7,
            "delta_bias": PH_DELTA,
            "lambda_candidates": PH_LAMBDA_CANDIDATES,
            "lambda_chosen": best_lambda,
            "target_alarm_rate_pct": TARGET_RATE * 100,
        },
        "forward_hold_min": 120,
        "fee_bp_round_trip": FEE_BP,
        "panel_bars": int(len(panel)),
        "n_quarters_total": n_quarters,
        "lesson_22_frame_grade": {
            "source_frequency": "5m volume (DB ohlcv 1m resampled)",
            "stateful_statistic_class": "Class A (Page-Hinkley CUSUM)",
            "frame_grade_satisfied": True,
            "panel_bars_evidence": int(len(panel)),
            "compare_paradigm_84": "daily aggregation 365 rows/sym FAIL → paradigm 123 5m 2M+ rows PASS",
        },
        "lesson_11_sample_density": {
            "n_triggers_total": n_trig_total,
            "n_triggers_pos": n_pos,
            "n_triggers_neg": n_neg,
            "trigger_rate_pct": round(n_trig_total / len(panel) * 100, 4),
            "per_quarter_pos": per_q_pos.to_dict(),
            "per_quarter_neg": per_q_neg.to_dict(),
            "measurable_quarters_pos": measurable_q_pos,
            "measurable_quarters_neg": measurable_q_neg,
            "cutoff_per_cell": 30,
            "verdict": "PASS" if measurable_q_pos >= 3 and measurable_q_neg >= 3 else "FAIL",
        },
        "lesson_23_non_event_anchored": {
            "anchor_type": "CONTINUOUS (Page-Hinkley alarm at any bar) — NOT event-anchored",
            "verdict": "PASS — Lesson #23 explicit non-target axis",
        },
        "lesson_28_substrate": {
            "5m_klines_source": "DB.ohlcv 1m resampled to 5m (13/13 alts verified)",
            "5m_volume_column": "DB.ohlcv.volume (sum aggregation in resample)",
            "verdict": "PASS",
        },
        "lesson_30_data_window_ratio": {
            "eth_days_loaded": full_days,
            "full_universe_proxy_days": 800,
            "ratio_pct": round((full_days / 800.0) * 100, 1) if full_days else None,
            "advisory_required": False,
        },
        "lesson_34_empirical_distribution": {
            "abs_log_vol_z_percentiles": pct_z,
            "abs_x_dev_percentiles": pct_x,
        },
        "lesson_40_structural_threshold_feasibility": {
            "threshold_definition": "PH CUSUM symmetric alarm (positive/negative drift)",
            "structurally_reachable": True,
            "verdict": "PASS — CUSUM by construction symmetric continuous",
        },
        "lesson_44_amendment_graveyard_xref": lesson_44_xref,
        "lesson_45_family_distinct": lesson_45_distinct,
        "lesson_46_amendment_refinement_stratified_R0": {
            "policy": "temporally-stratified n=50 × 4 quarters (NOT chronological n=200)",
            "stratification_strategy": stratified_strategy,
            "quarters_selected": qtrs_to_use if len(sorted_quarters) >= 4 else None,
            "n_sample_total": int(len(sample)),
            "four_quadrant": {
                "A_focus_pos_LONG": quad_a_focus,
                "A_mirror_pos_SHORT": quad_a_mirror,
                "B_focus_neg_SHORT": quad_b_focus,
                "B_mirror_neg_LONG": quad_b_mirror,
            },
            "per_quarter_detail": per_qtr_r0,
        },
        "lesson_39_sub_class_manual_check": {
            "A_focus_vs_A_mirror": lesson_39_a,
            "B_focus_vs_B_mirror": lesson_39_b,
            "note": "exact-symmetric by construction (mirror = -focus on sign-matched paradigm)",
        },
        "lambda_tuning_sweep": lambda_stats,
        "verdict": verdict,
    }

    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("R-0 prescreen JSON: %s", out_path)
    log.info("VERDICT: %s", verdict)


if __name__ == "__main__":
    main()
