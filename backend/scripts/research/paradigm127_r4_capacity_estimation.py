"""paradigm 127 R-4 capacity / liquidity / slippage scaling estimation.

R-4 elite gate caveat #4 (NEW). Quantifies per-trade USDT notional capacity
across 13 alts × paradigm 127 trigger events (1m vol > 30d p99 AND |1m_ret|>0.5%)
under 0.1% impact-volume threshold.

Output: r4__capacity_estimation.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paradigm127_r4_capacity")

UNIVERSE = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

IMPACT_THRESHOLD = 0.001  # 0.1% of 1m volume = soft-fill threshold (typical perp)
ACCOUNT_SIZES = [10_000, 100_000, 1_000_000]  # USDT account sizes for scaling
HOLD_MINUTES = 75  # paradigm 127 R-3 sweet-spot
TRIGGER_PCT = 99.0
MAGNITUDE_THRESHOLD = 0.005

OUTPUT_PATH = ROOT / "runs" / "research_track" / "alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m" / "r4__capacity_estimation.json"


def load_recent_1m(sym: str, days: int = 90) -> pd.DataFrame:
    """Load last N days of 1m OHLCV for liquidity estimation (recent active volume)."""
    db = SessionLocal()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        rows = db.execute(
            text(
                "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                "WHERE symbol = :sym AND time_frame = '1m' AND timestamp >= :cutoff "
                "ORDER BY timestamp ASC"
            ),
            {"sym": sym, "cutoff": cutoff},
        ).fetchall()
    finally:
        db.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()


def estimate_burst_capacity_for_symbol(sym: str) -> dict:
    """For each minute, identify burst event candidates and measure capacity.

    For paradigm 127 burst events:
      - 1m volume > p99 of trailing 30d
      - |1m_ret| > 0.5%
      - burst-minute sign > 0 (LONG continuation)
    Capacity USDT per event = burst_volume_USDT × IMPACT_THRESHOLD.
    """
    df = load_recent_1m(sym, days=90)
    if df.empty or len(df) < 30 * 1440:
        return {"sym": sym, "status": "insufficient_data", "n_bars": len(df)}

    df = df.sort_values("timestamp").reset_index(drop=True)
    df["ret_1m"] = df["close"].pct_change()
    # USDT notional 1m volume
    df["vol_usdt"] = df["volume"] * df["close"]
    # 30d trailing volume rolling p99 (in BASE units, then convert)
    df["vol_p99_30d"] = df["volume"].rolling(window=30 * 1440, min_periods=15 * 1440).quantile(0.99)
    # Trigger mask
    mask = (
        (df["volume"] > df["vol_p99_30d"])
        & (df["ret_1m"].abs() > MAGNITUDE_THRESHOLD)
        & (df["ret_1m"] > 0)
    )
    triggers = df[mask].copy()
    if triggers.empty:
        return {"sym": sym, "status": "no_triggers_in_90d", "n_bars": len(df)}

    # Capacity per trigger = burst-minute USDT volume × IMPACT_THRESHOLD
    triggers["capacity_usdt"] = triggers["vol_usdt"] * IMPACT_THRESHOLD

    # Note: actual fill must occur during 75-min hold window. Approximate per-minute
    # fill capacity by burst-minute volume; realistic VWAP fill spans several minutes.
    cap = triggers["capacity_usdt"]
    return {
        "sym": sym,
        "status": "ok",
        "n_bars": int(len(df)),
        "n_triggers_90d": int(len(triggers)),
        "triggers_per_year_extrapolated": float(len(triggers) * (365.0 / 90.0)),
        "burst_minute_volume_usdt_median": float(triggers["vol_usdt"].median()),
        "burst_minute_volume_usdt_p25": float(triggers["vol_usdt"].quantile(0.25)),
        "burst_minute_volume_usdt_p75": float(triggers["vol_usdt"].quantile(0.75)),
        "capacity_usdt_per_trigger_median": float(cap.median()),
        "capacity_usdt_per_trigger_p25": float(cap.quantile(0.25)),
        "capacity_usdt_per_trigger_p75": float(cap.quantile(0.75)),
        "capacity_usdt_per_trigger_min": float(cap.min()),
    }


def evaluate_account_scaling(per_sym: list[dict]) -> dict:
    """For each account size, evaluate fill feasibility per symbol.

    For each account size, position per symbol = account_size / 13 (equal weight).
    Slippage impact ≈ position / burst_volume_USDT (linear approximation).
    PASS if slippage impact < 5bp for median trigger.
    """
    results = {}
    for acct in ACCOUNT_SIZES:
        per_sym_position = acct / len(UNIVERSE)
        sym_results = []
        for r in per_sym:
            if r.get("status") != "ok":
                sym_results.append({"sym": r["sym"], "status": r["status"]})
                continue
            burst_vol_median = r["burst_minute_volume_usdt_median"]
            # Linear impact approximation: impact_bp ≈ 10000 × (position / burst_volume)
            impact_bp_median = 10000.0 * per_sym_position / burst_vol_median if burst_vol_median > 0 else float("inf")
            # Worst-case at p25 burst volume
            impact_bp_worst = 10000.0 * per_sym_position / r["burst_minute_volume_usdt_p25"] if r["burst_minute_volume_usdt_p25"] > 0 else float("inf")
            sym_results.append({
                "sym": r["sym"],
                "per_sym_position_usdt": per_sym_position,
                "impact_bp_median": impact_bp_median,
                "impact_bp_p25_worst": impact_bp_worst,
                "pass_median_le_5bp": impact_bp_median <= 5.0,
                "pass_worst_le_10bp": impact_bp_worst <= 10.0,
            })
        n_pass_median = sum(1 for s in sym_results if s.get("pass_median_le_5bp"))
        n_pass_worst = sum(1 for s in sym_results if s.get("pass_worst_le_10bp"))
        n_eval = sum(1 for s in sym_results if "impact_bp_median" in s)
        results[f"account_{acct}"] = {
            "account_size_usdt": acct,
            "per_sym_position_usdt": per_sym_position,
            "n_syms_evaluated": n_eval,
            "n_syms_pass_median_5bp": n_pass_median,
            "n_syms_pass_worst_10bp": n_pass_worst,
            "ratio_pass_median": n_pass_median / max(n_eval, 1),
            "ratio_pass_worst": n_pass_worst / max(n_eval, 1),
            "overall_pass_median": n_pass_median >= len(UNIVERSE) * 0.8,
            "overall_pass_worst": n_pass_worst >= len(UNIVERSE) * 0.8,
            "per_sym": sym_results,
        }
    return results


def main():
    t0 = time.time()
    log.info(f"paradigm 127 R-4 capacity estimation start ({len(UNIVERSE)} syms, 90d window, impact={IMPACT_THRESHOLD*100:.1f}%)")
    per_sym = []
    for sym in UNIVERSE:
        ts = time.time()
        r = estimate_burst_capacity_for_symbol(sym)
        log.info(f"  {sym}: {r.get('status','?')} n_triggers_90d={r.get('n_triggers_90d','-')} cap_med_usdt={r.get('capacity_usdt_per_trigger_median','-')} ({time.time()-ts:.1f}s)")
        per_sym.append(r)

    scaling = evaluate_account_scaling(per_sym)

    # Overall capacity verdict
    n_ok = sum(1 for r in per_sym if r.get("status") == "ok")
    median_caps = [r["capacity_usdt_per_trigger_median"] for r in per_sym if r.get("status") == "ok"]
    overall = {
        "n_syms_ok": n_ok,
        "median_capacity_usdt_across_syms": float(np.median(median_caps)) if median_caps else 0.0,
        "min_capacity_usdt_across_syms": float(np.min(median_caps)) if median_caps else 0.0,
        "max_capacity_usdt_across_syms": float(np.max(median_caps)) if median_caps else 0.0,
        "r4_capacity_gate_pass_account_100k": scaling.get("account_100000", {}).get("overall_pass_worst", False),
        "verdict": "PASS_R4_CAPACITY" if scaling.get("account_100000", {}).get("overall_pass_worst", False) else "FAIL_R4_CAPACITY",
    }

    output = {
        "paradigm_name": "alt_volume_burst_intra5m_event_pos_burst_continuation_long_60m",
        "paradigm_number": 127,
        "phase": "R-4",
        "caveat": "capacity_liquidity_estimation",
        "executed_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "method": "90d recent 1m OHLCV per-sym, trigger reproduction (vol p99 30d AND |1m_ret|>0.5% AND sign>0), burst-minute USDT volume × 0.1% impact threshold = per-trigger capacity USDT, linear slippage impact estimation",
        "universe": UNIVERSE,
        "impact_threshold": IMPACT_THRESHOLD,
        "account_sizes_evaluated": ACCOUNT_SIZES,
        "hold_minutes": HOLD_MINUTES,
        "per_symbol": per_sym,
        "account_scaling": scaling,
        "overall": overall,
        "wall_clock_seconds": time.time() - t0,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log.info(f"wrote {OUTPUT_PATH}")
    log.info(f"overall verdict: {overall['verdict']} (median cap USDT = {overall['median_capacity_usdt_across_syms']:.0f})")


if __name__ == "__main__":
    main()
