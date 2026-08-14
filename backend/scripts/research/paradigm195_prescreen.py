"""Paradigm 195 R-0 prescreen — empirical distribution of absolute spread
(5d_mean_var - 30d_mean_var) z-score, MEAN (per-bar) variance not sum.

Hypothesis fix: short_var = mean of squared returns over last 5d (30 bars),
long_var  = mean of squared returns over last 30d (180 bars).
Both have same dimensional scale (per-bar variance). Spread can be + or -.

Lesson #34 empirical distribution measurement.
Lesson #40 structural threshold feasibility check (absolute spread can be NEGATIVE,
so z>=+2 AND z<=-2 should both be reachable).
Lesson #11 sample density check.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "runs" / "ohlcv_cache_12col"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("p195_prescreen")

SYMS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX",
        "LINK", "LTC", "BCH", "NEAR", "FIL", "WIF"]

BARS_PER_DAY = 6
WIN_SHORT = 5 * BARS_PER_DAY    # 30 bars
WIN_LONG = 30 * BARS_PER_DAY    # 180 bars
WIN_Z = 90 * BARS_PER_DAY       # 540 bars


def compute_spread_z(close: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ser = pd.Series(close)
    log_ret = np.log(ser / ser.shift(1))
    sq = log_ret.pow(2)
    # MEAN variance (per-bar) — comparable dimensional scale
    short_var = sq.rolling(WIN_SHORT, min_periods=WIN_SHORT).mean()
    long_var = sq.rolling(WIN_LONG, min_periods=WIN_LONG).mean()
    spread = short_var - long_var  # can be + (5d > 30d, expansion) or - (5d < 30d, contraction)
    mu = spread.rolling(WIN_Z, min_periods=WIN_Z).mean()
    sd = spread.rolling(WIN_Z, min_periods=WIN_Z).std()
    z = (spread - mu) / sd
    z_arr = z.values
    bar_ret = (ser / ser.shift(1) - 1.0).values
    valid = ~np.isnan(z_arr) & ~np.isnan(bar_ret) & np.isfinite(z_arr)
    return z_arr, bar_ret, valid, spread.values


def main() -> None:
    log.info("paradigm 195 prescreen — MEAN-based absolute spread |z| distribution")
    t0 = time.time()
    all_z = []
    per_sym_stats = []
    panel_pos2 = 0
    panel_neg2 = 0
    panel_total = 0

    for sym in SYMS:
        p = CACHE_DIR / f"{sym}USDT_4h.joblib"
        if not p.exists():
            log.warning("missing %s", sym)
            continue
        df = joblib.load(p).sort_index()
        close = df["close"].astype(float).values
        z, bar_ret, valid, spread = compute_spread_z(close)
        zv = z[valid]
        spread_v = spread[valid]

        pos2 = int((zv >= 2).sum())
        neg2 = int((zv <= -2).sum())
        pos1_5 = int((zv >= 1.5).sum())
        neg1_5 = int((zv <= -1.5).sum())
        panel_pos2 += pos2
        panel_neg2 += neg2
        panel_total += len(zv)
        all_z.append(zv)
        per_sym_stats.append(dict(
            sym=sym,
            n_valid=int(len(zv)),
            z_min=float(zv.min()) if len(zv) else float("nan"),
            z_max=float(zv.max()) if len(zv) else float("nan"),
            spread_min_bp=float(spread_v.min() * 1e4) if len(spread_v) else float("nan"),
            spread_max_bp=float(spread_v.max() * 1e4) if len(spread_v) else float("nan"),
            spread_mean_bp=float(spread_v.mean() * 1e4) if len(spread_v) else float("nan"),
            pos2=pos2,
            neg2=neg2,
            pos1_5=pos1_5,
            neg1_5=neg1_5,
            pct_pos=float((spread_v > 0).sum() / max(len(spread_v), 1)),
            pct_neg=float((spread_v < 0).sum() / max(len(spread_v), 1)),
        ))

    all_z_arr = np.concatenate(all_z)
    log.info("panel stats:")
    log.info("  total valid: %d", panel_total)
    log.info("  z>=+2: %d (%.2f%%)", panel_pos2, 100*panel_pos2/panel_total)
    log.info("  z<=-2: %d (%.2f%%)", panel_neg2, 100*panel_neg2/panel_total)
    log.info("  |z|>=2: %d (%.2f%%)", panel_pos2 + panel_neg2, 100*(panel_pos2+panel_neg2)/panel_total)
    log.info("  z percentiles: p1=%.2f p5=%.2f p50=%.2f p95=%.2f p99=%.2f",
             np.percentile(all_z_arr, 1), np.percentile(all_z_arr, 5),
             np.percentile(all_z_arr, 50), np.percentile(all_z_arr, 95),
             np.percentile(all_z_arr, 99))

    log.info("per-sym:")
    for s in per_sym_stats:
        log.info("  %s: n=%d zmin=%.2f zmax=%.2f spread_mean=%.4fbp pos%%=%.1f neg%%=%.1f pos2=%d neg2=%d pos1.5=%d neg1.5=%d",
                 s["sym"], s["n_valid"], s["z_min"], s["z_max"],
                 s["spread_mean_bp"], s["pct_pos"]*100, s["pct_neg"]*100,
                 s["pos2"], s["neg2"], s["pos1_5"], s["neg1_5"])

    # Lesson #11 expected n per quadrant per quarter
    # 4-quadrant uses z>=+2 only (vol expansion: 5d>30d), split by bar dir
    # Expected: panel_pos2 / ~9 quarters / 2 bar dirs
    expected_per_cell_per_quarter = panel_pos2 / 9 / 2
    log.info("Lesson #11 expected_n per quadrant per quarter (z>=+2 trigger, split by bar dir): %.1f", expected_per_cell_per_quarter)
    log.info("  PASS (>=30): %s", expected_per_cell_per_quarter >= 30)

    # Lesson #40 verdict
    log.info("Lesson #40 absolute spread bilateral reachability: z>=+2=%.2f%% z<=-2=%.2f%%",
             100*panel_pos2/panel_total, 100*panel_neg2/panel_total)
    log.info("  z>=+2 (expansion) reachable: %s", panel_pos2 > 100)
    log.info("  z<=-2 (contraction) reachable: %s", panel_neg2 > 100)

    log.info("elapsed %.1fs", time.time() - t0)


if __name__ == "__main__":
    main()
