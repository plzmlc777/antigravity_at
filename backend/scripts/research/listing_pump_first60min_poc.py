"""paradigm-architect generated R-1 PoC — listing_pump_first60min.

Hypothesis: Newly listed Binance Futures perpetuals exhibit Day-1 intraday
pump-and-fade pattern. The first minutes of trading produce a euphoria
spike, then the next hours mean-revert. Short at minute-60 close, exit at
hour-4 close. This is DIFFERENT from lifecycle_pump_decay (which holds
30 days from Day-1 close) — operating on an intraday timescale captures
distinct microstructure.

Sub-hypotheses:

  (a) BASE TRADE — for each listing event:
        entry: listing_start + 60 min (close of minute 60)
        exit:  listing_start + 240 min (close of minute 240)
        ret_short_net = -(exit/entry - 1) - 2*4bps fee
      H1: cohort median > 0 AND perm test p < 0.05.

  (b) PUMP-CONDITIONAL — stratify by pump_60min magnitude:
        pump_60min = entry/listing_first_close - 1
      If pump_60min > +20% (heavily pumped) → fade should be stronger.
      Test: cohort split high-pump vs low-pump, compare median forward ret.

  (c) WINDOW GRID — entry minute ∈ {30, 60, 120}, hold minutes ∈ {60,
      120, 240, 480}. Find the most robust (entry, hold) combination.

  (d) SL sensitivity — within best window, test SL ∈ {None, +5%, +10%,
      +15%} (price rise above entry).

Cohort: all symbols in listing_dates.json with 1m ohlcv covering the
first 8 hours from listing. Age 30-365 days (same cohort as lifecycle).

Output: backend/runs/research_track/listing_pump_first60min/poc__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("listing_pump_first60min_poc")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "listing_pump_first60min" / "poc__metrics.json"

FEE_ROUND_TRIP = 0.0008
PUMP_THRESHOLD_HIGH = 0.20
MIN_BARS_NEEDED = 480  # 8h of 1m bars required


def load_minutes(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp LIMIT 50000"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def simulate(minutes: pd.DataFrame, entry_min: int, hold_min: int,
             sl_pct: float | None = None) -> dict | None:
    """Short at minute(entry_min) close, exit at minute(entry_min+hold_min)
    close OR when high crosses entry × (1+sl_pct). Returns trade dict or None."""
    if len(minutes) < entry_min + hold_min + 1:
        return None
    entry_close = minutes.iloc[entry_min]["close"]
    if entry_close <= 0:
        return None
    sl_trigger = entry_close * (1 + sl_pct) if sl_pct else None
    exit_idx = entry_min + hold_min
    exit_close = minutes.iloc[exit_idx]["close"]
    exit_reason = "time"
    if sl_pct:
        for i in range(entry_min + 1, exit_idx + 1):
            if minutes.iloc[i]["high"] >= sl_trigger:
                exit_idx = i
                exit_close = sl_trigger
                exit_reason = "sl"
                break
    ret_gross = (entry_close - exit_close) / entry_close
    return {
        "entry_close": float(entry_close),
        "exit_close": float(exit_close),
        "ret_gross": float(ret_gross),
        "ret_net": float(ret_gross - FEE_ROUND_TRIP),
        "exit_reason": exit_reason,
        "hold_min_actual": int(exit_idx - entry_min),
    }


def cohort_stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0}
    arr = np.array(rets)
    return {
        "n": len(arr),
        "mean_pct": round(float(arr.mean()) * 100, 3),
        "median_pct": round(float(np.median(arr)) * 100, 3),
        "std_pct": round(float(arr.std(ddof=1)) * 100, 3) if len(arr) > 1 else None,
        "t_stat": round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2) if len(arr) > 1 and arr.std() > 0 else None,
        "win_rate_positive": round(float((arr > 0).mean()), 3),
        "p25_pct": round(float(np.percentile(arr, 25)) * 100, 3),
        "p75_pct": round(float(np.percentile(arr, 75)) * 100, 3),
    }


def permutation_test(symbol_minutes: dict, entry_min: int, hold_min: int,
                     sl_pct: float | None, n_perm: int = 500) -> dict:
    """Null: random entry minute (uniform in [60, 1200]) instead of listing-anchored
    minute-60. Compute synthetic cohort median, build null distribution."""
    rng = np.random.default_rng(42)
    actuals = []
    for sym, mins in symbol_minutes.items():
        sim = simulate(mins, entry_min, hold_min, sl_pct)
        if sim:
            actuals.append(sim["ret_net"])
    if not actuals:
        return {"skip": "no_actuals"}
    actual_median = float(np.median(actuals))

    null_medians = []
    for _ in range(n_perm):
        rets = []
        for sym, mins in symbol_minutes.items():
            if len(mins) < 1320:
                continue
            random_entry = int(rng.integers(60, 1200))
            sim = simulate(mins, random_entry, hold_min, sl_pct)
            if sim:
                rets.append(sim["ret_net"])
        if rets:
            null_medians.append(np.median(rets))
    null_arr = np.array(null_medians)
    p_one = float((null_arr >= actual_median).mean())
    return {
        "actual_median_pct": round(actual_median * 100, 3),
        "null_median_mean_pct": round(float(null_arr.mean()) * 100, 3),
        "null_median_std_pct": round(float(null_arr.std()) * 100, 3),
        "n_null_draws": len(null_arr),
        "p_value_one_sided": round(p_one, 4),
        "sigma": round((actual_median - null_arr.mean()) / null_arr.std(), 2) if null_arr.std() > 0 else None,
    }


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    listings = json.loads(LISTINGS_PATH.read_text())
    today = date.today()
    db = SessionLocal()
    try:
        syms_in_db = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
        )).fetchall()})
        log.info("syms in DB: %d", len(syms_in_db))

        symbol_minutes: dict[str, pd.DataFrame] = {}
        listing_meta: list[dict] = []
        for sym in syms_in_db:
            if sym not in listings:
                continue
            ld = datetime.strptime(listings[sym]["onboard_date"], "%Y-%m-%d").date()
            age = (today - ld).days
            if age < 30 or age > 365:
                continue
            mins = load_minutes(db, sym)
            if mins.empty:
                continue
            # Need at least the first 8h of bars (480 minutes)
            # The first bar timestamp should be near listing_date
            first_ts = mins.index[0]
            if abs((first_ts.date() - ld).days) > 2:
                continue
            if len(mins) < MIN_BARS_NEEDED:
                continue
            symbol_minutes[sym] = mins
            listing_meta.append({
                "symbol": sym,
                "listing_date": str(ld),
                "year_quarter": f"{ld.year}Q{(ld.month-1)//3+1}",
                "age_days": age,
                "first_minute_ts": str(first_ts),
                "n_bars": len(mins),
            })
        log.info("cohort with sufficient data: %d", len(symbol_minutes))
    finally:
        db.close()

    if not symbol_minutes:
        OUT_PATH.write_text(json.dumps({"error": "no cohort"}, indent=2))
        return 1

    # ─── (a) BASE TRADE: entry=60, hold=180 (= minute 60 to minute 240) ───
    base_rets = []
    base_records = []
    for sym, mins in symbol_minutes.items():
        sim = simulate(mins, entry_min=60, hold_min=180, sl_pct=None)
        if sim:
            base_rets.append(sim["ret_net"])
            base_records.append({
                "symbol": sym, **sim,
                "year_quarter": [m["year_quarter"] for m in listing_meta if m["symbol"] == sym][0],
            })
    base_summary = cohort_stats(base_rets)

    # ─── (b) PUMP-CONDITIONAL: stratify by pump_60min magnitude ───
    pump_cond_records = []
    for sym, mins in symbol_minutes.items():
        first_close = mins.iloc[0]["close"]
        min_60_close = mins.iloc[60]["close"]
        if first_close <= 0:
            continue
        pump_60min = min_60_close / first_close - 1
        sim = simulate(mins, entry_min=60, hold_min=180, sl_pct=None)
        if sim:
            pump_cond_records.append({
                "symbol": sym,
                "pump_60min": float(pump_60min),
                "ret_net": sim["ret_net"],
            })
    pc_df = pd.DataFrame(pump_cond_records) if pump_cond_records else pd.DataFrame()
    pump_strat = {}
    if not pc_df.empty:
        high_pump = pc_df[pc_df["pump_60min"] >= PUMP_THRESHOLD_HIGH]
        low_pump = pc_df[pc_df["pump_60min"] < PUMP_THRESHOLD_HIGH]
        pump_strat["high_pump"] = cohort_stats(high_pump["ret_net"].tolist())
        pump_strat["high_pump"]["threshold"] = f">= +{PUMP_THRESHOLD_HIGH*100:.0f}%"
        pump_strat["low_pump"] = cohort_stats(low_pump["ret_net"].tolist())
        pump_strat["low_pump"]["threshold"] = f"< +{PUMP_THRESHOLD_HIGH*100:.0f}%"

    # ─── (c) WINDOW GRID ───
    grid = []
    for entry in [30, 60, 120]:
        for hold in [60, 120, 240, 480]:
            rets = []
            for sym, mins in symbol_minutes.items():
                sim = simulate(mins, entry, hold, sl_pct=None)
                if sim:
                    rets.append(sim["ret_net"])
            grid.append({"entry_min": entry, "hold_min": hold, **cohort_stats(rets)})

    # ─── (d) SL grid on entry=60, hold=240 ───
    sl_grid = []
    for sl in [None, 0.05, 0.10, 0.15, 0.20]:
        rets = []
        for sym, mins in symbol_minutes.items():
            sim = simulate(mins, 60, 180, sl_pct=sl)
            if sim:
                rets.append(sim["ret_net"])
        sl_grid.append({"sl": sl, **cohort_stats(rets)})

    # ─── Permutation test on base (entry=60, hold=180) ───
    log.info("running permutation test (n=500)...")
    perm = permutation_test(symbol_minutes, 60, 180, None, n_perm=500)

    # ─── Quarterly fold ───
    bd_df = pd.DataFrame(base_records)
    quarterly = {}
    if not bd_df.empty:
        for q in sorted(bd_df["year_quarter"].unique()):
            q_df = bd_df[bd_df["year_quarter"] == q]
            if len(q_df) < 5:
                continue
            quarterly[q] = {
                "n": len(q_df),
                "median_pct": round(float(q_df["ret_net"].median()) * 100, 3),
                "mean_pct": round(float(q_df["ret_net"].mean()) * 100, 3),
                "win_rate_positive": round(float((q_df["ret_net"] > 0).mean()), 3),
            }

    out = {
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP,
            "pump_threshold_high": PUMP_THRESHOLD_HIGH,
            "min_bars_needed": MIN_BARS_NEEDED,
        },
        "cohort_summary": {
            "n_symbols_used": len(symbol_minutes),
        },
        "hyp_a_base_trade_short_60_to_240min": base_summary,
        "hyp_b_pump_conditional": pump_strat,
        "hyp_c_window_grid": grid,
        "hyp_d_sl_grid": sl_grid,
        "permutation_test_base": perm,
        "quarterly_folds_base": quarterly,
        "top_5_winners": sorted(base_records, key=lambda r: -r["ret_net"])[:5] if base_records else [],
        "bottom_5_losers": sorted(base_records, key=lambda r: r["ret_net"])[:5] if base_records else [],
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    log.info("\n%s", json.dumps({k: v for k, v in out.items() if k not in ("top_5_winners", "bottom_5_losers", "config")},
                                  indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
