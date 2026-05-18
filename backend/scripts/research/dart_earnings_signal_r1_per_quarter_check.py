"""Per-quarter stratification of H1 R-1 focus cell (Lesson #26 prescreen).

Re-runs collect_events + compute_event_returns from dart_earnings_signal_r1
and breaks the A_focus_pos_long cell by calendar quarter. Reports per-Q
count, mean net return, and t-stat. If any quarter has n < 5 OR a
single-quarter outlier drives the aggregate, the R-1 PASS is downgraded
to FRAGILE pending R-2 walk-forward.
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

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from scripts.research.dart_earnings_signal_r1 import (  # noqa: E402
    collect_events, compute_event_returns, build_universe,
    TOP_KOSPI, TOP_KOSDAQ, WINDOW_BGN, WINDOW_END, OHLCV_PAD_DAYS,
    GAP_THRESHOLD, FEE_ROUND_TRIP, HOLD_DAYS, OUT_DIR,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("h1_r1_perQ")


def per_quarter_stats(events_ret: pd.DataFrame) -> dict:
    pos = events_ret[events_ret["gap"] >= GAP_THRESHOLD].copy()
    if pos.empty:
        return {"error": "pos cohort empty"}
    pos["net_ret"] = pos["fwd_ret_gross"] - FEE_ROUND_TRIP
    pos["quarter"] = pos["entry_date"].dt.to_period("Q").astype(str)
    rows = []
    for q, g in pos.groupby("quarter"):
        n = len(g)
        m = float(g["net_ret"].mean())
        sd = float(g["net_ret"].std(ddof=1)) if n >= 2 else 0.0
        t = m / sd * np.sqrt(n) if sd > 0 else 0.0
        rows.append({
            "quarter": q,
            "n": n,
            "net_mean_bp": m * 10_000,
            "t_stat": t,
            "min_bp": float(g["net_ret"].min()) * 10_000,
            "max_bp": float(g["net_ret"].max()) * 10_000,
            "win_rate": float((g["net_ret"] > 0).mean()),
        })
    rows.sort(key=lambda r: r["quarter"])
    # Drop-one-quarter sensitivity
    sensitivities = []
    full_mean = pos["net_ret"].mean()
    for q in pos["quarter"].unique():
        rest = pos[pos["quarter"] != q]["net_ret"]
        if len(rest) > 0:
            sensitivities.append({
                "drop_quarter": q,
                "remaining_n": len(rest),
                "remaining_net_mean_bp": float(rest.mean()) * 10_000,
                "delta_from_full_bp": float(rest.mean() - full_mean) * 10_000,
            })
    sensitivities.sort(key=lambda r: abs(r["delta_from_full_bp"]), reverse=True)
    return {
        "per_quarter": rows,
        "drop_one_sensitivity_top3": sensitivities[:3],
        "n_quarters": len(rows),
        "min_quarter_n": min(r["n"] for r in rows) if rows else 0,
        "fragility_flags": _flag(rows, sensitivities, full_mean),
    }


def _flag(rows: list, sens: list, full_mean: float) -> list:
    flags = []
    if rows and min(r["n"] for r in rows) < 5:
        flags.append("min_quarter_n_lt_5")
    pos_q = [r for r in rows if r["net_mean_bp"] > 0]
    if len(pos_q) / max(1, len(rows)) < 0.6:
        flags.append("less_than_60pct_quarters_positive")
    if sens:
        top = sens[0]
        # If removing one quarter drops aggregate by >50% of full mean, fragile
        if abs(top["delta_from_full_bp"]) > abs(full_mean * 10_000) * 0.5:
            flags.append(f"single_quarter_drives_aggregate ({top['drop_quarter']})")
    return flags


def main():
    log.info("re-loading universe + events from cache for per-Q stratification")
    universe = build_universe(TOP_KOSPI, TOP_KOSDAQ)
    universe_codes = set(universe["itemCode"].astype(str).str.zfill(6).tolist())
    events = collect_events(universe_codes)
    ohlcv_bgn = (pd.to_datetime(WINDOW_BGN, format="%Y%m%d")
                 - pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    ohlcv_end = (pd.to_datetime(WINDOW_END, format="%Y%m%d")
                 + pd.Timedelta(days=OHLCV_PAD_DAYS)).strftime("%Y%m%d")
    events_ret = compute_event_returns(events, ohlcv_bgn, ohlcv_end)
    result = per_quarter_stats(events_ret)
    out_path = OUT_DIR / "h1_earnings_r1_perQ.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    log.info("WROTE %s", out_path)
    print(json.dumps({
        "n_quarters": result["n_quarters"],
        "min_quarter_n": result["min_quarter_n"],
        "fragility_flags": result["fragility_flags"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
