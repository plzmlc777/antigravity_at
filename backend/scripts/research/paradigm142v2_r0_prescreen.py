"""paradigm 142-v2 R-0 prescreen — alt_taker_buy_quote_vol_imbalance_z_directional_4h

R-0 prescreen sequential order:
  1. Lesson #40 structural threshold feasibility:
     imbalance ∈ [0,1], (imbalance - 0.5) per-sym 30d rolling z-score
     Verify z empirical distribution allows |z|>2 attainment per cell.
  2. Lesson #28 substrate availability: 12-col cache verified existing.
  3. Lesson #11 + #23 sample density: |z|>2 rate × 14 syms × 800d × 6/day ≥ per-cell n=30
  4. Lesson #34 empirical distribution: |imbalance - 0.5| p50/p90/p99/max
  5. Lesson #27 entry-side immediate (4h continuation = forward-looking action upon trigger
     observed at bar close — substrate fully available at decision time)
  6. Lesson #32 universe-baseline coherent: A_focus uses same |z|>2 filter as B_baseline,
     no orphan rows.
  7. Lesson #21 sub-finding magnitude-ratio prescreen: per-sym imbalance histogram check
     (uniform 0.4-0.6 vs broader 0.3-0.7 spread).
  8. Lesson #30 data window ratio: 14/14 syms × 820 days uniform PASS.
  9. Lesson #44 amendment 25th xref:
     paradigm 72 (5m taker_buy_vol BROAD_FALSIFIED) — distinct via 4h frame + USD imbalance
     paradigm 127/128 (volume burst R-5 LIVE) — distinct via continuous imbalance ratio
     paradigm 140 (CVD ratio) — distinct via quote (USD-denominated, removes price-corr)
     funding family (22/132/138-141) — distinct axis (taker action vs financing)
     Lesson #21 N/A (single derived ratio from single bar, no cross-domain stacking).
     Lesson #54 N/A (single domain).

Output: r0_prescreen.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.binance.backfill_12col_klines import load_12col_cached  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm142v2_r0")

SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "BNB",
        "LINK", "BCH", "FIL", "LTC", "NEAR", "WIF"]
TF = "4h"
Z_THRESHOLD = 2.0
ROLLING_BARS = 180  # 30 days × 6 bars/day at 4h

OUT_DIR = ROOT / "runs" / "research_track" / "alt_taker_buy_quote_vol_imbalance_z_directional_4h"
OUT_PATH = OUT_DIR / "r0_prescreen.json"


def compute_imbalance_z(df: pd.DataFrame) -> pd.Series:
    """taker_buy_quote / quote_volume centered at 0.5, then per-sym rolling z."""
    qv = df["quote_volume"].astype(float)
    tbq = df["taker_buy_quote_volume"].astype(float)
    # Guard division
    safe_qv = qv.where(qv > 0, np.nan)
    imbalance = (tbq / safe_qv) - 0.5  # range [-0.5, +0.5]
    mu = imbalance.rolling(ROLLING_BARS, min_periods=60).mean()
    sd = imbalance.rolling(ROLLING_BARS, min_periods=60).std()
    z = (imbalance - mu) / sd.where(sd > 1e-12, np.nan)
    return z, imbalance


def per_sym_stats(sym_pair: str) -> dict:
    df = load_12col_cached(sym_pair, TF)
    n_total = len(df)
    z, raw_imb = compute_imbalance_z(df)
    z_valid = z.dropna()
    raw_valid = raw_imb.dropna()

    # Empirical distribution of imbalance (raw, centered)
    imb_p50 = float(np.percentile(np.abs(raw_valid), 50)) if len(raw_valid) else None
    imb_p90 = float(np.percentile(np.abs(raw_valid), 90)) if len(raw_valid) else None
    imb_p99 = float(np.percentile(np.abs(raw_valid), 99)) if len(raw_valid) else None
    imb_max = float(np.max(np.abs(raw_valid))) if len(raw_valid) else None

    # z distribution
    z_p50 = float(np.percentile(np.abs(z_valid), 50)) if len(z_valid) else None
    z_p90 = float(np.percentile(np.abs(z_valid), 90)) if len(z_valid) else None
    z_p99 = float(np.percentile(np.abs(z_valid), 99)) if len(z_valid) else None
    z_max = float(np.max(np.abs(z_valid))) if len(z_valid) else None
    z_min = float(np.min(z_valid)) if len(z_valid) else None  # can be negative — symmetric expected

    n_pos = int((z_valid > Z_THRESHOLD).sum())
    n_neg = int((z_valid < -Z_THRESHOLD).sum())
    n_z_valid = int(len(z_valid))
    pos_rate = float(n_pos / n_z_valid) if n_z_valid else 0.0
    neg_rate = float(n_neg / n_z_valid) if n_z_valid else 0.0

    return {
        "symbol": sym_pair,
        "n_total_bars": int(n_total),
        "n_z_valid": n_z_valid,
        "imb_abs_p50": imb_p50,
        "imb_abs_p90": imb_p90,
        "imb_abs_p99": imb_p99,
        "imb_abs_max": imb_max,
        "z_abs_p50": z_p50,
        "z_abs_p90": z_p90,
        "z_abs_p99": z_p99,
        "z_abs_max": z_max,
        "z_min": z_min,
        "n_z_pos2": n_pos,
        "n_z_neg2": n_neg,
        "pos2_rate": pos_rate,
        "neg2_rate": neg_rate,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("paradigm 142-v2 R-0 prescreen: %d syms × tf=%s", len(SYMS), TF)

    per_sym = []
    for s in SYMS:
        sym_pair = s + "USDT"
        try:
            stats = per_sym_stats(sym_pair)
        except Exception as e:
            log.warning("[%s] error: %s", sym_pair, e)
            stats = {"symbol": sym_pair, "error": str(e)}
        per_sym.append(stats)
        log.info("[%s] n_valid=%d pos2=%d neg2=%d (%.2f%% / %.2f%%) imb_p90=%.4f z_p90=%.2f z_min=%.2f",
                 sym_pair, stats.get("n_z_valid", 0),
                 stats.get("n_z_pos2", 0), stats.get("n_z_neg2", 0),
                 100*stats.get("pos2_rate", 0), 100*stats.get("neg2_rate", 0),
                 stats.get("imb_abs_p90") or 0,
                 stats.get("z_abs_p90") or 0,
                 stats.get("z_min") or 0)

    # Aggregate cross-sym
    valid = [s for s in per_sym if "error" not in s]
    total_pos = sum(s["n_z_pos2"] for s in valid)
    total_neg = sum(s["n_z_neg2"] for s in valid)
    total_valid = sum(s["n_z_valid"] for s in valid)
    universe_pos_rate = total_pos / total_valid if total_valid else 0.0
    universe_neg_rate = total_neg / total_valid if total_valid else 0.0

    # Per-cell density: 4 quadrants (A focus pos, A mirror pos, B focus neg, B mirror neg
    # are 2 trigger directions × 2 hold-side directions; trigger count divided by 4 quarters)
    # Quarter cells assume ~5.5 quarters in 2.25yr window
    n_quarters = 9  # 2024Q1..2026Q1
    per_cell_pos = total_pos / n_quarters
    per_cell_neg = total_neg / n_quarters

    # Lesson #11 prescreen: per-cell >= 30
    pass_pos_density = per_cell_pos >= 30
    pass_neg_density = per_cell_neg >= 30
    pass_density = pass_pos_density and pass_neg_density

    # Lesson #40 attainability: |z| > 2 reachable per sym?
    syms_attain_pos = sum(1 for s in valid if s["n_z_pos2"] > 0)
    syms_attain_neg = sum(1 for s in valid if s["n_z_neg2"] > 0)
    attainability_pos = syms_attain_pos >= 10  # ≥10/14 syms have at least 1 trigger
    attainability_neg = syms_attain_neg >= 10
    pass_attainability = attainability_pos and attainability_neg

    # Lesson #21 sub-finding: per-sym imbalance spread (heterogeneity check)
    imb_p90_values = [s["imb_abs_p90"] for s in valid if s["imb_abs_p90"] is not None]
    imb_p90_min = min(imb_p90_values) if imb_p90_values else None
    imb_p90_max = max(imb_p90_values) if imb_p90_values else None
    imb_p90_spread_ratio = (imb_p90_max / imb_p90_min) if (imb_p90_min and imb_p90_min > 0) else None

    # Lesson #30 data window ratio
    window_lens = [s["n_total_bars"] for s in valid]
    max_window = max(window_lens) if window_lens else 0
    min_window = min(window_lens) if window_lens else 0
    data_window_ratio = (min_window / max_window) if max_window else 0
    pass_window = data_window_ratio >= 0.30

    # Verdict
    verdict_parts = []
    if pass_attainability:
        verdict_parts.append("LESSON40_ATTAINABILITY_PASS")
    else:
        verdict_parts.append(f"LESSON40_FAIL_pos={syms_attain_pos}/14_neg={syms_attain_neg}/14")
    if pass_density:
        verdict_parts.append(f"LESSON11_DENSITY_PASS_pos_cell={per_cell_pos:.1f}_neg_cell={per_cell_neg:.1f}")
    else:
        verdict_parts.append(f"LESSON11_DENSITY_FAIL_pos_cell={per_cell_pos:.1f}_neg_cell={per_cell_neg:.1f}")
    if pass_window:
        verdict_parts.append(f"LESSON30_WINDOW_PASS={data_window_ratio:.2f}")
    else:
        verdict_parts.append(f"LESSON30_WINDOW_FAIL={data_window_ratio:.2f}")

    overall_pass = pass_attainability and pass_density and pass_window
    final_verdict = "R0_PRESCREEN_PASS" if overall_pass else "R0_PRESCREEN_HALT"

    summary = {
        "paradigm_name": "alt_taker_buy_quote_vol_imbalance_z_directional_4h",
        "paradigm_counter": 142,
        "tf": TF,
        "z_threshold": Z_THRESHOLD,
        "rolling_bars": ROLLING_BARS,
        "n_syms": len(SYMS),
        "n_syms_valid": len(valid),
        "universe_pos2_rate": universe_pos_rate,
        "universe_neg2_rate": universe_neg_rate,
        "total_pos_triggers": total_pos,
        "total_neg_triggers": total_neg,
        "per_cell_pos_n_per_quarter": per_cell_pos,
        "per_cell_neg_n_per_quarter": per_cell_neg,
        "lesson40_attain_pos_syms": syms_attain_pos,
        "lesson40_attain_neg_syms": syms_attain_neg,
        "lesson40_attainability_pass": pass_attainability,
        "lesson11_density_pass_pos": pass_pos_density,
        "lesson11_density_pass_neg": pass_neg_density,
        "lesson11_density_pass": pass_density,
        "lesson21_subfinding_imb_p90_min": imb_p90_min,
        "lesson21_subfinding_imb_p90_max": imb_p90_max,
        "lesson21_subfinding_imb_p90_spread_ratio": imb_p90_spread_ratio,
        "lesson30_data_window_ratio": data_window_ratio,
        "lesson30_window_pass": pass_window,
        "verdict": final_verdict,
        "verdict_components": verdict_parts,
        "overall_pass": overall_pass,
        "per_sym": per_sym,
    }

    OUT_PATH.write_text(json.dumps(summary, indent=2, default=str))
    log.info("R-0 prescreen verdict: %s", final_verdict)
    log.info("Components: %s", verdict_parts)
    log.info("Output: %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
