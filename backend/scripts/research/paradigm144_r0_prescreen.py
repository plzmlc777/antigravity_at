"""Paradigm 144 R-0 prescreen: alt_avg_trade_size_quote_vol_per_n_trades_z_directional_4h.

R-0 Prescreen checks (mandatory before R-1 dispatch)
----------------------------------------------------
1. Lesson #40 structural threshold feasibility:
   z-score is unbounded → both tails attainable. Verify empirically per sym.
2. Lesson #28 substrate availability: 12-col cache exists w/ quote_volume + count.
3. Lesson #11 sample density expected per-cell ≥ 30.
4. Lesson #34 empirical distribution: avg_size USD p50/p90/p99/max per sym.
5. Lesson #21 sub-finding magnitude-ratio prescreen (CRITICAL for same-bar same-substrate ratio):
   Compute corr(log_qv, log_cnt). High corr (>0.85) → ratio is near-trivial residual
   = paradigm 137 Yang-Zhang Parkinson/close antipattern signature.
   Also compute residual variance share: Var(log_ats) / Var(log_qv).
   Low residual share (<25%) → axis is dominated by common activity strength,
   ratio adds minimal new information.
6. Lesson #30 data_window_ratio: full window
7. Lesson #54 same-bar same-substrate ratio (informational caution, paradigm 137 precedent)

Verdict tree
------------
R0_HALT_PRESCREEN_FAIL if:
  - any Lesson #40 / #11 / #30 fails (hard halt)
  - Lesson #21 sub-finding: mean_corr ≥ 0.90 AND mean_residual_share ≤ 0.20
    → STRONG_AXIS_DEGENERACY (informational halt per Lesson #54 precedent strength)

R0_PASS_DISPATCH_R1 otherwise (Lesson #21 sub-finding warning still emitted).
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.binance.backfill_12col_klines import load_12col_cached  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm144_r0")

PARADIGM_NAME = "alt_avg_trade_size_quote_vol_per_n_trades_z_directional_4h"
PARADIGM_ID = 144
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
            "ADAUSDT", "AVAXUSDT", "BNBUSDT", "LINKUSDT", "BCHUSDT",
            "FILUSDT", "LTCUSDT", "NEARUSDT", "WIFUSDT"]
TF = "4h"
ROLLING_BARS = 180  # 30d × 6 bars/day
Z_TRIGGER_ABS = 2.0

# Lesson #21 sub-finding thresholds
CORR_DEGENERACY_THRESHOLD = 0.90        # mean corr ≥ this → strong warning
RESIDUAL_SHARE_DEGENERACY_THRESHOLD = 0.20  # Var(log_ats)/Var(log_qv) ≤ this → strong warning


def main() -> int:
    t0 = time.time()
    log.info("paradigm 144 R-0 prescreen starting")

    per_sym: Dict[str, Dict] = {}
    n_loaded = 0
    z_min_global = []
    z_max_global = []
    trigger_rates_pos = []
    trigger_rates_neg = []
    corrs_qv_cnt = []
    residual_shares = []
    avg_size_p50 = []
    avg_size_p90 = []
    avg_size_p99 = []
    avg_size_max = []

    for sym in UNIVERSE:
        try:
            df = load_12col_cached(sym, TF)
        except FileNotFoundError as e:
            log.warning("[%s] cache missing: %s", sym, e)
            continue
        if df.empty:
            log.warning("[%s] empty", sym)
            continue
        d = df.copy()
        d["quote_volume"] = pd.to_numeric(d["quote_volume"], errors="coerce").astype(float)
        d["count"] = pd.to_numeric(d["count"], errors="coerce").astype(float)
        safe_cnt = d["count"].where(d["count"] > 0, np.nan)
        safe_qv = d["quote_volume"].where(d["quote_volume"] > 0, np.nan)
        d["avg_trade_size"] = safe_qv / safe_cnt

        ats = d["avg_trade_size"].dropna()
        if len(ats) < 100:
            log.warning("[%s] avg_trade_size too few valid: %d", sym, len(ats))
            continue

        p50 = float(np.percentile(ats, 50))
        p90 = float(np.percentile(ats, 90))
        p99 = float(np.percentile(ats, 99))
        amax = float(ats.max())

        # 30d rolling z-score (shifted)
        roll = d["avg_trade_size"].rolling(ROLLING_BARS, min_periods=60)
        mu = roll.mean()
        sd = roll.std(ddof=1)
        z = (d["avg_trade_size"] - mu) / sd.where(sd > 0, np.nan)
        z = z.shift(1)
        zv = z.dropna()

        if len(zv) < 100:
            log.warning("[%s] z too few valid: %d", sym, len(zv))
            continue

        zmin = float(zv.min())
        zmax = float(zv.max())
        n_pos = int((zv > Z_TRIGGER_ABS).sum())
        n_neg = int((zv < -Z_TRIGGER_ABS).sum())
        rate_pos = n_pos / len(zv)
        rate_neg = n_neg / len(zv)

        # Lesson #21 sub-finding: corr + residual variance share
        log_qv = np.log(safe_qv)
        log_cnt = np.log(safe_cnt)
        log_ats = log_qv - log_cnt
        valid_mask = log_qv.notna() & log_cnt.notna()
        if valid_mask.sum() < 100:
            corr = float("nan")
            residual_share = float("nan")
            var_qv = float("nan")
            var_cnt = float("nan")
            var_ats = float("nan")
        else:
            lqv = log_qv[valid_mask].values
            lcnt = log_cnt[valid_mask].values
            lats = log_ats[valid_mask].values
            var_qv = float(np.var(lqv, ddof=1))
            var_cnt = float(np.var(lcnt, ddof=1))
            var_ats = float(np.var(lats, ddof=1))
            corr = float(np.corrcoef(lqv, lcnt)[0, 1])
            # residual variance share = Var(log_ats) / Var(log_qv)
            # low share = avg_size axis carries little new info beyond qv
            residual_share = var_ats / var_qv if var_qv > 0 else float("nan")

        per_sym[sym] = {
            "n_bars": int(len(d)),
            "n_avg_size_valid": int(len(ats)),
            "n_z_valid": int(len(zv)),
            "span_days": float((d.index.max() - d.index.min()).total_seconds() / 86400),
            "avg_size_p50_usd": p50,
            "avg_size_p90_usd": p90,
            "avg_size_p99_usd": p99,
            "avg_size_max_usd": amax,
            "z_min": zmin,
            "z_max": zmax,
            "z_min_threshold_attainable": bool(zmin <= -Z_TRIGGER_ABS),
            "z_max_threshold_attainable": bool(zmax >= Z_TRIGGER_ABS),
            "n_trigger_pos": n_pos,
            "n_trigger_neg": n_neg,
            "rate_pos": float(rate_pos),
            "rate_neg": float(rate_neg),
            "var_log_qv": var_qv,
            "var_log_cnt": var_cnt,
            "var_log_ats": var_ats,
            "corr_log_qv_log_cnt": corr,
            "residual_variance_share": residual_share,
        }
        n_loaded += 1
        z_min_global.append(zmin)
        z_max_global.append(zmax)
        trigger_rates_pos.append(rate_pos)
        trigger_rates_neg.append(rate_neg)
        if np.isfinite(corr):
            corrs_qv_cnt.append(corr)
        if np.isfinite(residual_share):
            residual_shares.append(residual_share)
        avg_size_p50.append(p50)
        avg_size_p90.append(p90)
        avg_size_p99.append(p99)
        avg_size_max.append(amax)

        log.info("[%s] bars=%d ats p50=%.1f p90=%.1f USD | z [%.2f, %.2f] rate_pos=%.2f%% rate_neg=%.2f%% | "
                 "corr(log_qv,log_cnt)=%.3f resid_share=%.3f",
                 sym, len(d), p50, p90, zmin, zmax, rate_pos*100, rate_neg*100,
                 corr if np.isfinite(corr) else float("nan"),
                 residual_share if np.isfinite(residual_share) else float("nan"))

    # ===== Aggregate Gates =====
    l40_all_pos = all(s["z_max_threshold_attainable"] for s in per_sym.values())
    l40_all_neg = all(s["z_min_threshold_attainable"] for s in per_sym.values())
    l40_pass = l40_all_pos and l40_all_neg

    mean_rate_pos = float(np.mean(trigger_rates_pos)) if trigger_rates_pos else 0.0
    mean_rate_neg = float(np.mean(trigger_rates_neg)) if trigger_rates_neg else 0.0
    typical_bars_per_sym = float(np.mean([s["n_z_valid"] for s in per_sym.values()])) if per_sym else 0.0
    expected_n_pos_total = mean_rate_pos * typical_bars_per_sym * n_loaded
    expected_n_neg_total = mean_rate_neg * typical_bars_per_sym * n_loaded
    expected_per_cell_pos = expected_n_pos_total / 10.0
    expected_per_cell_neg = expected_n_neg_total / 10.0
    l11_pass = expected_per_cell_pos >= 30 and expected_per_cell_neg >= 30

    # Lesson #21 sub-finding (CRITICAL Lesson #54 precedent check)
    mean_corr = float(np.mean(corrs_qv_cnt)) if corrs_qv_cnt else float("nan")
    max_corr = float(np.max(corrs_qv_cnt)) if corrs_qv_cnt else float("nan")
    min_corr = float(np.min(corrs_qv_cnt)) if corrs_qv_cnt else float("nan")
    mean_resid_share = float(np.mean(residual_shares)) if residual_shares else float("nan")
    max_resid_share = float(np.max(residual_shares)) if residual_shares else float("nan")
    min_resid_share = float(np.min(residual_shares)) if residual_shares else float("nan")

    l21_strong_axis_degeneracy = (
        np.isfinite(mean_corr) and np.isfinite(mean_resid_share)
        and mean_corr >= CORR_DEGENERACY_THRESHOLD
        and mean_resid_share <= RESIDUAL_SHARE_DEGENERACY_THRESHOLD
    )
    l21_warning_only = (
        np.isfinite(mean_corr) and mean_corr >= 0.80
        and not l21_strong_axis_degeneracy
    )

    l30_pass = n_loaded >= 12

    l54_compliance = {
        "ratio_type": "same_bar_same_substrate (quote_volume / count from identical 4h bar)",
        "precedent_paradigm_137_yang_zhang": "Parkinson/close ratio BROAD_FALSIFIED — same-bar same-substrate antipattern",
        "lesson_54_status_for_144": "STRONG MATCH — quote_volume/count is same-bar same-substrate activity ratio",
    }

    # Decision: Lesson #21 sub-finding STRONG AXIS DEGENERACY triggers R-0 HALT
    overall_pass = bool(
        l40_pass and l11_pass and l30_pass and n_loaded >= 12
        and not l21_strong_axis_degeneracy
    )

    if l21_strong_axis_degeneracy:
        verdict_reason = (
            f"R-0 HALT — Lesson #21 sub-finding STRONG_AXIS_DEGENERACY: "
            f"mean corr(log_qv, log_cnt)={mean_corr:.3f} ≥ {CORR_DEGENERACY_THRESHOLD} AND "
            f"mean Var(log_ats)/Var(log_qv)={mean_resid_share:.3f} ≤ {RESIDUAL_SHARE_DEGENERACY_THRESHOLD}. "
            f"avg_trade_size ratio carries minimal information independent of activity strength. "
            f"Lesson #54 paradigm 137 (Yang-Zhang Parkinson/close) precedent strong match — same-bar "
            f"same-substrate trivial ratio antipattern."
        )
    else:
        verdict_reason = "R-0 PASS — Lessons #11 #40 #21 #30 all pass"

    family_distinct = {
        "n_trades_count_column_first_use": "144 paradigms 중 0회 사용 — axis novelty 입증",
        "paradigm_72_taker_buy_vol": "distinct: taker-side action vs total quote_vol / count",
        "paradigm_127_128_volume_burst_R5_LIVE": "distinct: 1m binary burst vs 4h continuous ratio z",
        "paradigm_140_CVD_ratio": "distinct: directional flow vs trade size",
        "paradigm_142v2_quote_vol_imbalance_z": "distinct: taker_buy/total flow direction vs quote_vol/count size aggregation",
        "paradigm_143_quote_vol_percentile": "distinct: imbalance percentile vs avg_size z-score",
        "paradigm_137_yang_zhang": "Lesson #54 precedent — same-bar same-substrate ratio antipattern",
        "lesson_57_family_evasion": "Lesson #57 = aggressive taker quote-vol imbalance; paradigm 144 has zero taker filter (total quote_vol)",
    }

    out = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_id": PARADIGM_ID,
        "phase": "R-0_prescreen",
        "run_ts": str(pd.Timestamp.now(tz="UTC")),
        "wall_clock_seconds": float(time.time() - t0),
        "config": {
            "universe": UNIVERSE,
            "n_syms_universe": len(UNIVERSE),
            "n_syms_loaded": n_loaded,
            "tf": TF,
            "rolling_bars": ROLLING_BARS,
            "z_trigger_abs": Z_TRIGGER_ABS,
            "corr_degeneracy_threshold": CORR_DEGENERACY_THRESHOLD,
            "residual_share_degeneracy_threshold": RESIDUAL_SHARE_DEGENERACY_THRESHOLD,
        },
        "per_symbol": per_sym,
        "aggregate": {
            "n_loaded": n_loaded,
            "mean_typical_bars_per_sym": typical_bars_per_sym,
            "z_min_global": float(min(z_min_global)) if z_min_global else None,
            "z_max_global": float(max(z_max_global)) if z_max_global else None,
            "mean_trigger_rate_pos": mean_rate_pos,
            "mean_trigger_rate_neg": mean_rate_neg,
            "expected_n_pos_total": float(expected_n_pos_total),
            "expected_n_neg_total": float(expected_n_neg_total),
            "expected_per_cell_pos": float(expected_per_cell_pos),
            "expected_per_cell_neg": float(expected_per_cell_neg),
            "avg_size_p50_median_usd": float(np.median(avg_size_p50)) if avg_size_p50 else None,
            "avg_size_p90_median_usd": float(np.median(avg_size_p90)) if avg_size_p90 else None,
            "avg_size_p99_median_usd": float(np.median(avg_size_p99)) if avg_size_p99 else None,
            "corr_log_qv_log_cnt_mean": mean_corr,
            "corr_log_qv_log_cnt_min": min_corr,
            "corr_log_qv_log_cnt_max": max_corr,
            "residual_variance_share_mean": mean_resid_share,
            "residual_variance_share_min": min_resid_share,
            "residual_variance_share_max": max_resid_share,
        },
        "gates": {
            "lesson_40_threshold_attainable_pos": bool(l40_all_pos),
            "lesson_40_threshold_attainable_neg": bool(l40_all_neg),
            "lesson_40_pass": bool(l40_pass),
            "lesson_11_expected_per_cell_pos_pass": bool(expected_per_cell_pos >= 30),
            "lesson_11_expected_per_cell_neg_pass": bool(expected_per_cell_neg >= 30),
            "lesson_11_pass": bool(l11_pass),
            "lesson_21_sub_finding_strong_axis_degeneracy": bool(l21_strong_axis_degeneracy),
            "lesson_21_sub_finding_warning_only": bool(l21_warning_only),
            "lesson_21_pass": bool(not l21_strong_axis_degeneracy),
            "lesson_30_n_syms_pass": bool(l30_pass),
            "lesson_54_compliance": l54_compliance,
            "overall_pass": overall_pass,
        },
        "family_distinct_paradigms": family_distinct,
        "verdict": "R0_PASS_DISPATCH_R1" if overall_pass else "R0_HALT_PRESCREEN_FAIL",
        "verdict_reason": verdict_reason,
    }
    out_path = OUT_DIR / "r0_prescreen.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("wrote %s", out_path)
    log.info("=== R-0 verdict: %s ===", out["verdict"])
    log.info("%s", verdict_reason)
    log.info("L40=%s L11=%s (cell pos=%.1f neg=%.1f) L21=%s (mean_corr=%.3f resid=%.3f) L30=%s (n=%d)",
             l40_pass, l11_pass, expected_per_cell_pos, expected_per_cell_neg,
             not l21_strong_axis_degeneracy, mean_corr, mean_resid_share, l30_pass, n_loaded)
    log.info("wall clock: %.1fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
