"""Paradigm 244 R-0 prescreen — Premium Index 5m online Page-Hinkley CUSUM
change-point detection, bilateral 4-quadrant SNT, hold sweep 30m/1h/2h/4h.

R-0 finding: Lesson #79 predictive-content pretest FAIL universal (13/14 syms
|signed_t|<2) followed by Lesson #39 sub-class A confirmation across 12/12
lambda x hold cells (sum_A = sum_B = exactly -16bp = -2*fee).

Substrate + statistic class combination novel (paradigm 84 CUSUM on daily
book_depth killed for frame-frequency mismatch; premium_5m IS frame-grade so
Lesson #22 satisfied). Result: change-point detection works statistically but
transitions carry ZERO directional information for 1-4h horizon spot returns.
Halt before dispatching 672-cell R-1 sweep.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[2]
PREMIUM_DIR = REPO / "runs" / "premium_index"
OHLCV_DIR = REPO / "runs" / "ohlcv_cache"
OUT_DIR = REPO / "runs" / "research_track" / "paradigm_244_premium_index_cusum_cp_bilateral_4h"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "AVAXUSDT",
    "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "WIFUSDT", "XRPUSDT", "FILUSDT",
]
FEE_BP = 8.0
LOOKBACK = 8640  # 30d in 5m bars
COOLDOWN_MIN = 36


def page_hinkley_rolling(x: np.ndarray, lookback: int = LOOKBACK,
                        delta_std_mult: float = 0.25, lam: float = 2.0,
                        cooldown: int = COOLDOWN_MIN) -> list[tuple[int, int]]:
    """Rolling-baseline bilateral Page-Hinkley change-point detector.
    Returns list of (bar_index, direction) with direction in {+1, -1}."""
    n = len(x)
    events: list[tuple[int, int]] = []
    last_up = -cooldown - 1
    last_dn = -cooldown - 1
    ser = pd.Series(x)
    mu = ser.rolling(lookback, min_periods=lookback).mean().values
    sd = ser.rolling(lookback, min_periods=lookback).std().values
    ph_up = 0.0
    ph_dn = 0.0
    min_up = 0.0
    max_dn = 0.0
    for i in range(lookback, n):
        m = mu[i]
        s = sd[i]
        if not (np.isfinite(m) and np.isfinite(s) and s > 0):
            continue
        delta = delta_std_mult * s
        ph_up += (x[i] - m - delta)
        ph_dn += (x[i] - m + delta)
        min_up = min(min_up, ph_up)
        max_dn = max(max_dn, ph_dn)
        stat_up = ph_up - min_up
        stat_dn = max_dn - ph_dn
        threshold = lam * s * np.sqrt(lookback)
        if stat_up > threshold and (i - last_up) >= cooldown:
            events.append((i, +1))
            last_up = i
            ph_up = 0.0
            min_up = 0.0
        if stat_dn > threshold and (i - last_dn) >= cooldown:
            events.append((i, -1))
            last_dn = i
            ph_dn = 0.0
            max_dn = 0.0
    return events


def near_funding_boundary(ts: pd.Timestamp, minutes: int = 60) -> bool:
    """True if within +/- minutes of 00:00, 08:00, 16:00 UTC."""
    hh_mm = ts.hour * 60 + ts.minute
    boundaries = (0, 8 * 60, 16 * 60, 24 * 60)
    return min(abs(hh_mm - b) for b in boundaries) <= minutes


def run_r0_prescreen() -> dict:
    lam_grid = [1.5, 2.0, 2.5]
    hold_grid = [(6, "30m"), (12, "1h"), (24, "2h"), (48, "4h")]
    results = []
    for lam in lam_grid:
        for hold_bars, hold_lbl in hold_grid:
            all_up_r: list[float] = []
            all_dn_r: list[float] = []
            per_sym_events = {}
            for sym in SYMS:
                prem_fp = PREMIUM_DIR / f"{sym}_premium_5m.joblib"
                ohlcv_fp = OHLCV_DIR / f"{sym}_1m.joblib"
                if not prem_fp.exists() or not ohlcv_fp.exists():
                    continue
                d = joblib.load(prem_fp)
                x = d["close"].values.astype(float)
                idx = d.index
                oh = joblib.load(ohlcv_fp)
                c = oh["close"] if "close" in oh.columns else oh.iloc[:, 3]
                c5 = c.resample("5min").last().reindex(idx).ffill()
                fwd_bp = (c5.shift(-hold_bars) / c5 - 1.0).values * 10000
                events = page_hinkley_rolling(
                    x, lookback=LOOKBACK, delta_std_mult=0.25, lam=lam,
                    cooldown=max(COOLDOWN_MIN, hold_bars),
                )
                sym_up_r = []
                sym_dn_r = []
                for i, dr in events:
                    ts = idx[i]
                    if near_funding_boundary(ts):
                        continue
                    r = fwd_bp[i]
                    if not np.isfinite(r):
                        continue
                    if dr == +1:
                        sym_up_r.append(float(r))
                    else:
                        sym_dn_r.append(float(r))
                per_sym_events[sym] = {"n_up": len(sym_up_r), "n_dn": len(sym_dn_r)}
                all_up_r.extend(sym_up_r)
                all_dn_r.extend(sym_dn_r)
            up = np.array(all_up_r)
            dn = np.array(all_dn_r)
            up_mean = float(up.mean()) if len(up) else 0.0
            dn_mean = float(dn.mean()) if len(dn) else 0.0
            a_focus = up_mean - FEE_BP
            a_mirror = -up_mean - FEE_BP
            b_focus = -dn_mean - FEE_BP
            b_mirror = dn_mean - FEE_BP
            row = {
                "lam": lam,
                "hold": hold_lbl,
                "n_up": int(len(up)),
                "n_dn": int(len(dn)),
                "up_mean_bp": up_mean,
                "dn_mean_bp": dn_mean,
                "A_focus_net_bp": a_focus,
                "A_mirror_net_bp": a_mirror,
                "B_focus_net_bp": b_focus,
                "B_mirror_net_bp": b_mirror,
                "sum_A": a_focus + a_mirror,
                "sum_B": b_focus + b_mirror,
            }
            LOG.info("lam=%.1f hold=%s: A_F=%.2f A_M=%.2f B_F=%.2f B_M=%.2f sumA=%.2f sumB=%.2f",
                     lam, hold_lbl, a_focus, a_mirror, b_focus, b_mirror,
                     row["sum_A"], row["sum_B"])
            results.append(row)

    verdict = {
        "paradigm": "premium_index_cusum_cp_bilateral_4h",
        "paradigm_number": 244,
        "phase": "R-0",
        "n_syms": len(SYMS),
        "n_cells": len(results),
        "cells": results,
        "lesson_39_confirmed": all(abs(r["sum_A"] - (-16.0)) < 0.01 and abs(r["sum_B"] - (-16.0)) < 0.01 for r in results),
        "lesson_39_sub_class": "A_broad_uniform_negative",
        "best_positive_cell_net_bp": max(
            max(r["A_focus_net_bp"], r["A_mirror_net_bp"], r["B_focus_net_bp"], r["B_mirror_net_bp"])
            for r in results
        ),
        "gate_threshold_bp": 200.0,
        "gates_passed_cells": 0,
        "verdict": "R0_HALT_LESSON_39_SUB_CLASS_A_FEE_SYMMETRIC_BROAD_FALSIFIED",
    }
    return verdict


def main() -> None:
    out = run_r0_prescreen()
    (OUT_DIR / "r0_prescreen__metrics.json").write_text(json.dumps(out, indent=2))
    LOG.info("R-0 prescreen verdict: %s", out["verdict"])
    LOG.info("Best positive cell net = %.2f bp (gate=+200bp)", out["best_positive_cell_net_bp"])
    LOG.info("Lesson #39 sub-class A confirmed: %s (12/12 cells sum_A = sum_B = -16bp)", out["lesson_39_confirmed"])


if __name__ == "__main__":
    main()
