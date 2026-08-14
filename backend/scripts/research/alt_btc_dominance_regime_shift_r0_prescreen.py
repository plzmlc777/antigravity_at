"""Paradigm 239 R-0 prescreen — Lesson #79 predictive-content pretest.

Hypothesis: BTC dominance regime shifts predict alt rotation on 1-3d holds.
Signal: 90d rolling z-score of (btc_7d_ret - alt_basket_7d_ret) spread.

Lesson #79 gate: OOS half + BTCUSDT + 3 rep alts (SOL/AVAX/DOGE).
Measure corr(dom_z, fwd_pct_change_at_1d/3d) per (sym × hold).
HALT if max |corr| across all (sym × hold) < 0.02.

Additional prescreen: Lesson #40 structural threshold feasibility (dom_z distribution).
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

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p239_r0")

OUT_DIR = ROOT / "runs" / "research_track" / "alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Universe: BTCUSDT + 13 alts actually in cache
BTC = "BTCUSDT"
ALT_UNIVERSE = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
REP_ALTS = ["SOLUSDT", "AVAXUSDT", "DOGEUSDT"]

WINDOW_DAYS = 90
SPREAD_DAYS = 7


def load_daily_close(sym: str) -> pd.Series:
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    daily = df["close"].resample("1D").last().dropna()
    return daily


def compute_dom_z(btc_close: pd.Series, alt_closes: dict[str, pd.Series]) -> pd.Series:
    btc_ret = btc_close.pct_change(SPREAD_DAYS)
    alt_ret_df = pd.DataFrame({s: c.pct_change(SPREAD_DAYS) for s, c in alt_closes.items()})
    alt_ret_df = alt_ret_df.reindex(btc_ret.index)
    alt_basket_ret = alt_ret_df.mean(axis=1)
    spread = btc_ret - alt_basket_ret
    dom_z = (spread - spread.rolling(WINDOW_DAYS).mean()) / spread.rolling(WINDOW_DAYS).std(ddof=1)
    return dom_z.dropna()


def run() -> int:
    log.info("R-0 loading BTC + %d alts", len(ALT_UNIVERSE))
    btc = load_daily_close(BTC)
    if btc.empty:
        log.error("BTC daily empty")
        return 2
    alts = {}
    for s in ALT_UNIVERSE:
        c = load_daily_close(s)
        if not c.empty:
            alts[s] = c
        else:
            log.warning("skip %s (empty)", s)

    log.info("BTC range %s..%s (%d days)", btc.index.min(), btc.index.max(), len(btc))
    log.info("alts loaded: %d/%d", len(alts), len(ALT_UNIVERSE))

    # Align
    all_idx = btc.index
    for s, c in alts.items():
        all_idx = all_idx.intersection(c.index)
    btc = btc.reindex(all_idx)
    alts = {s: c.reindex(all_idx) for s, c in alts.items()}

    log.info("aligned days: %d", len(all_idx))

    dom_z = compute_dom_z(btc, alts)
    log.info("dom_z valid days: %d (range %s..%s)", len(dom_z), dom_z.index.min(), dom_z.index.max())

    # Empirical distribution — Lesson #40 feasibility
    empirical = {
        "n": int(len(dom_z)),
        "min": float(dom_z.min()),
        "max": float(dom_z.max()),
        "p01": float(dom_z.quantile(0.01)),
        "p05": float(dom_z.quantile(0.05)),
        "p10": float(dom_z.quantile(0.10)),
        "p50": float(dom_z.quantile(0.50)),
        "p90": float(dom_z.quantile(0.90)),
        "p95": float(dom_z.quantile(0.95)),
        "p99": float(dom_z.quantile(0.99)),
        "std": float(dom_z.std(ddof=1)),
        "mean": float(dom_z.mean()),
    }
    log.info("dom_z distribution: %s", empirical)

    # Trigger rate estimation at |z| thresholds
    trigger_rate = {}
    for T in [1.0, 1.5, 2.0]:
        n_pos = int((dom_z >= T).sum())
        n_neg = int((dom_z <= -T).sum())
        total = n_pos + n_neg
        trigger_rate[f"|z|>={T}"] = {
            "n_pos": n_pos, "n_neg": n_neg, "total": total,
            "rate_pct": round(100.0 * total / len(dom_z), 2),
            "annual_est": int(total * 365.0 / len(dom_z)),
        }
    log.info("trigger rate: %s", trigger_rate)

    # OOS half: split at median date
    split_idx = len(dom_z) // 2
    oos_start = dom_z.index[split_idx]
    log.info("OOS split at %s (in-sample=%d, oos=%d)", oos_start, split_idx, len(dom_z) - split_idx)

    dom_z_oos = dom_z.iloc[split_idx:]

    # Compute forward returns per rep alt on OOS
    lesson79 = {}
    for sym in REP_ALTS:
        if sym not in alts:
            log.warning("skip %s (missing)", sym)
            continue
        close = alts[sym].reindex(dom_z_oos.index)
        # Forward returns
        for hold_d in [1, 2, 3]:
            fwd_ret = close.pct_change(hold_d).shift(-hold_d)
            paired = pd.DataFrame({"z": dom_z_oos, "r": fwd_ret}).dropna()
            if len(paired) < 30:
                lesson79[f"{sym}_h{hold_d}"] = {"n": len(paired), "corr": None, "abs_corr": None, "note": "insufficient"}
                continue
            corr = float(paired["z"].corr(paired["r"]))
            lesson79[f"{sym}_h{hold_d}"] = {
                "n": int(len(paired)),
                "corr": round(corr, 5),
                "abs_corr": round(abs(corr), 5),
            }

    max_abs_corr = max((v["abs_corr"] for v in lesson79.values() if v.get("abs_corr") is not None), default=0.0)
    lesson79_verdict = "PASS" if max_abs_corr >= 0.02 else "HALT"

    log.info("Lesson #79 pretest: max |corr| = %.5f -> %s", max_abs_corr, lesson79_verdict)
    for k, v in lesson79.items():
        log.info("  %s: %s", k, v)

    # Structural threshold feasibility (Lesson #40)
    lesson40 = {}
    for T in [1.0, 1.5, 2.0]:
        feasible_neg = empirical["min"] <= -T
        feasible_pos = empirical["max"] >= T
        lesson40[f"z>={T}"] = feasible_pos
        lesson40[f"z<=-{T}"] = feasible_neg
    lesson40_verdict = "PASS" if all(lesson40.values()) else "PARTIAL"

    result = {
        "paradigm": "alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h",
        "phase": "R-0",
        "window_days": WINDOW_DAYS,
        "spread_days": SPREAD_DAYS,
        "universe_btc": BTC,
        "universe_alts": list(alts.keys()),
        "n_alts": len(alts),
        "aligned_days": len(all_idx),
        "dom_z_days": len(dom_z),
        "dom_z_distribution": empirical,
        "trigger_rate": trigger_rate,
        "oos_split_ts": str(oos_start),
        "oos_n_days": int(len(dom_z_oos)),
        "lesson_79_pretest": lesson79,
        "lesson_79_max_abs_corr": max_abs_corr,
        "lesson_79_threshold": 0.02,
        "lesson_79_verdict": lesson79_verdict,
        "lesson_40_feasibility": lesson40,
        "lesson_40_verdict": lesson40_verdict,
    }

    out_path = OUT_DIR / "r0_prescreen__metrics.json"
    out_path.write_text(json.dumps(result, indent=2, default=str))
    log.info("wrote %s", out_path)

    if lesson79_verdict == "HALT":
        log.error("R-0 HALT: Lesson #79 predictive-content < 0.02")
        return 1
    log.info("R-0 PASS → proceed to R-1")
    return 0


if __name__ == "__main__":
    sys.exit(run())
