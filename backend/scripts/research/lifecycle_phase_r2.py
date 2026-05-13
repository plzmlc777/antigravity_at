"""Direction 1 R-2 — Listing Pump Decay (Hyp B) extended cohort + simulation.

R-1 (lifecycle_phase_poc.py) findings on 42-symbol cohort:
  pumped (Day1 high ≥30%) Day30 median return: -33.5%, win_rate_negative 75%
  all cohort Day30 median: -20%+ regardless

R-2 extensions over R-1:
  1. Cohort: 30-365 days age (was 30-180) → ~170 symbols
  2. Strategy simulation with stop-loss at +50% (cap outlier risk like AIA +481%)
  3. Quarterly fold analysis (listings grouped by quarter) for time-stability
  4. Permutation test (n=200): compare actual cohort 30d return distribution
     to random non-listing-anchored 30-day windows for same symbols
  5. Subgroup stratification: pumped vs not-pumped, listing-year buckets
  6. Bootstrap CI on median return (1000 resamples)

Output: backend/runs/research_track/lifecycle_phase/r2__metrics.json
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
log = logging.getLogger("lifecycle_phase_r2")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "r2__metrics.json"

PUMP_THRESHOLD = 0.30
SL_LEVEL = 0.50         # short stop-loss: exit when price rises +50% from entry
HOLD_DAYS = 30
FEE_ROUND_TRIP = 0.0008
PERM_N = 200
BOOTSTRAP_N = 1000
SEED = 42


def load_daily_ohlcv(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    daily = pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()
    return daily


def simulate_short_with_sl(daily: pd.DataFrame, entry_idx: int,
                           sl_level: float, hold_days: int) -> dict:
    """Short at daily[entry_idx].close, exit on:
       (a) price > entry × (1 + sl_level), OR
       (b) day == entry_idx + hold_days.
    Return pnl (return on entry capital, after round-trip fee), exit reason, exit day.
    """
    if entry_idx >= len(daily):
        return None
    entry_price = daily.iloc[entry_idx]["close"]
    if entry_price <= 0:
        return None
    sl_trigger = entry_price * (1.0 + sl_level)
    max_idx = min(entry_idx + hold_days, len(daily) - 1)
    exit_idx = max_idx
    exit_price = daily.iloc[max_idx]["close"]
    exit_reason = "time"
    # Check intra-day SL: any day where daily high > sl_trigger
    for i in range(entry_idx + 1, max_idx + 1):
        if daily.iloc[i]["high"] >= sl_trigger:
            exit_idx = i
            exit_price = sl_trigger  # filled at SL trigger
            exit_reason = "sl"
            break
    ret_gross = (entry_price - exit_price) / entry_price  # short PnL
    ret_net = ret_gross - FEE_ROUND_TRIP
    return {
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "ret_gross": float(ret_gross),
        "ret_net": float(ret_net),
        "exit_reason": exit_reason,
        "hold_days_actual": int(exit_idx - entry_idx),
    }


def cohort_stats(returns: list[float]) -> dict:
    if not returns:
        return {"n": 0}
    arr = np.array(returns)
    return {
        "n": len(arr),
        "mean_pct": round(float(arr.mean()) * 100, 2),
        "median_pct": round(float(np.median(arr)) * 100, 2),
        "std_pct": round(float(arr.std(ddof=1)) * 100, 2) if len(arr) > 1 else None,
        "t_stat": round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2) if len(arr) > 1 and arr.std() > 0 else None,
        "win_rate_positive": round(float((arr > 0).mean()), 3),
        "p25_pct": round(float(np.percentile(arr, 25)) * 100, 2),
        "p75_pct": round(float(np.percentile(arr, 75)) * 100, 2),
        "max_pct": round(float(arr.max()) * 100, 2),
        "min_pct": round(float(arr.min()) * 100, 2),
    }


def bootstrap_ci(values: list[float], n_resample: int, ci: float = 0.95) -> dict:
    arr = np.array(values)
    rng = np.random.default_rng(SEED)
    medians = []
    means = []
    for _ in range(n_resample):
        sample = rng.choice(arr, size=len(arr), replace=True)
        medians.append(np.median(sample))
        means.append(np.mean(sample))
    lo, hi = (1 - ci) / 2, 1 - (1 - ci) / 2
    return {
        "median_ci_lo_pct": round(float(np.quantile(medians, lo)) * 100, 2),
        "median_ci_hi_pct": round(float(np.quantile(medians, hi)) * 100, 2),
        "mean_ci_lo_pct": round(float(np.quantile(means, lo)) * 100, 2),
        "mean_ci_hi_pct": round(float(np.quantile(means, hi)) * 100, 2),
    }


def permutation_test(symbol_daily: dict, listing_dates: dict,
                     hold_days: int, sl_level: float, n_perm: int) -> dict:
    """Null: 30d return from random non-listing-anchored entry day.
    For each symbol, pick random entry_idx in [60, len-hold_days-1] uniformly,
    apply same short-with-SL strategy. Repeat n_perm times. Compute null
    distribution of cohort median return. Compare to actual."""
    rng = np.random.default_rng(SEED)
    actual_rets = []
    for sym, daily in symbol_daily.items():
        ld = listing_dates[sym]
        try:
            entry_pos = daily.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0]
        except Exception:
            continue
        if entry_pos < 0 or entry_pos >= len(daily) - hold_days:
            continue
        sim = simulate_short_with_sl(daily, entry_pos, sl_level, hold_days)
        if sim is None:
            continue
        actual_rets.append(sim["ret_net"])
    if not actual_rets:
        return {"skip": "no_actual_rets"}
    actual_median = float(np.median(actual_rets))

    null_medians = []
    for _ in range(n_perm):
        perm_rets = []
        for sym, daily in symbol_daily.items():
            if len(daily) < hold_days + 70:
                continue
            entry_pos = int(rng.integers(60, len(daily) - hold_days - 1))
            sim = simulate_short_with_sl(daily, entry_pos, sl_level, hold_days)
            if sim is None:
                continue
            perm_rets.append(sim["ret_net"])
        if perm_rets:
            null_medians.append(np.median(perm_rets))

    null_arr = np.array(null_medians)
    # One-sided test: actual median should be HIGHER (better for short) than null
    p_one_sided = float((null_arr >= actual_median).mean())
    return {
        "actual_median_pct": round(actual_median * 100, 2),
        "null_median_mean_pct": round(float(null_arr.mean()) * 100, 2),
        "null_median_std_pct": round(float(null_arr.std()) * 100, 2),
        "null_n_draws": len(null_arr),
        "p_value_one_sided": round(p_one_sided, 4),
        "sigma": round((actual_median - null_arr.mean()) / null_arr.std(), 2) if null_arr.std() > 0 else None,
    }


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    listings = json.loads(LISTINGS_PATH.read_text())
    log.info("loaded %d listings", len(listings))

    db = SessionLocal()
    try:
        syms_in_db = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
        )).fetchall()})
    finally:
        db.close()

    today = date.today()
    candidates = []
    for sym in syms_in_db:
        if sym not in listings:
            continue
        ld = datetime.strptime(listings[sym]["onboard_date"], "%Y-%m-%d").date()
        age = (today - ld).days
        if age < 30 or age > 365:
            continue
        candidates.append((sym, ld, age))
    log.info("cohort candidates: %d (age 30-365d)", len(candidates))

    # Load daily ohlcv and run simulations
    symbol_daily: dict[str, pd.DataFrame] = {}
    listing_ts: dict[str, str] = {}
    rows = []
    db = SessionLocal()
    try:
        for sym, ld, age in candidates:
            daily = load_daily_ohlcv(db, sym)
            if daily.empty or len(daily) < HOLD_DAYS + 2:
                continue
            ld_ts = pd.Timestamp(ld)
            if ld_ts > daily.index.max() - pd.Timedelta(days=HOLD_DAYS):
                continue
            # Find entry: listing date in daily index
            try:
                entry_pos = daily.index.get_indexer([ld_ts], method="nearest")[0]
                entry_actual = daily.index[entry_pos].date()
                if abs((entry_actual - ld).days) > 2:
                    continue  # listing day not in our data
            except Exception:
                continue

            # Day 1 (= listing day) metrics
            day1_row = daily.iloc[entry_pos]
            day1_open = day1_row["open"]
            day1_high = day1_row["high"]
            day1_close = day1_row["close"]
            if day1_open <= 0:
                continue
            day1_high_ret = day1_high / day1_open - 1
            day1_close_ret = day1_close / day1_open - 1
            pumped = day1_high_ret >= PUMP_THRESHOLD

            # Strategy: short Day 1 close (= daily[entry_pos]["close"])
            sim = simulate_short_with_sl(daily, entry_pos, SL_LEVEL, HOLD_DAYS)
            if sim is None:
                continue

            rows.append({
                "symbol": sym,
                "listing_date": str(ld),
                "year_quarter": f"{ld.year}Q{(ld.month-1)//3+1}",
                "age_days": age,
                "day1_high_ret": day1_high_ret,
                "day1_close_ret": day1_close_ret,
                "pumped": pumped,
                "entry_price": sim["entry_price"],
                "exit_price": sim["exit_price"],
                "ret_gross": sim["ret_gross"],
                "ret_net": sim["ret_net"],
                "exit_reason": sim["exit_reason"],
                "hold_days_actual": sim["hold_days_actual"],
            })
            symbol_daily[sym] = daily
            listing_ts[sym] = str(ld)
    finally:
        db.close()

    if not rows:
        log.error("no rows produced")
        OUT_PATH.write_text(json.dumps({"error": "empty"}, indent=2))
        return 1

    df = pd.DataFrame(rows)
    log.info("simulated trades: %d cohort symbols", len(df))

    pumped_df = df[df["pumped"]]
    not_pumped_df = df[~df["pumped"]]

    results = {
        "config": {
            "pump_threshold": PUMP_THRESHOLD,
            "sl_level": SL_LEVEL,
            "hold_days": HOLD_DAYS,
            "fee_round_trip": FEE_ROUND_TRIP,
            "perm_n": PERM_N,
            "bootstrap_n": BOOTSTRAP_N,
            "seed": SEED,
        },
        "cohort_summary": {
            "n_total": len(df),
            "n_pumped": int(df["pumped"].sum()),
            "n_not_pumped": int((~df["pumped"]).sum()),
            "n_sl_hit": int((df["exit_reason"] == "sl").sum()),
            "n_time_exit": int((df["exit_reason"] == "time").sum()),
            "mean_hold_days": round(float(df["hold_days_actual"].mean()), 1),
        },
        "all_cohort_short_30d_ret_net": cohort_stats(df["ret_net"].tolist()),
        "pumped_short_30d_ret_net": cohort_stats(pumped_df["ret_net"].tolist()),
        "not_pumped_short_30d_ret_net": cohort_stats(not_pumped_df["ret_net"].tolist()),
        "all_bootstrap_ci_95": bootstrap_ci(df["ret_net"].tolist(), BOOTSTRAP_N),
        "pumped_bootstrap_ci_95": bootstrap_ci(pumped_df["ret_net"].tolist(), BOOTSTRAP_N) if len(pumped_df) else None,
    }

    # Quarterly folds
    q_folds = {}
    for q in sorted(df["year_quarter"].unique()):
        q_df = df[df["year_quarter"] == q]
        q_folds[q] = {
            "n": len(q_df),
            **{k: v for k, v in cohort_stats(q_df["ret_net"].tolist()).items()
               if k in ("mean_pct", "median_pct", "win_rate_positive")},
        }
    results["quarterly_folds"] = q_folds

    # Permutation test
    log.info("running permutation test (n=%d)...", PERM_N)
    perm = permutation_test(symbol_daily, listing_ts, HOLD_DAYS, SL_LEVEL, PERM_N)
    results["permutation_test"] = perm

    # Sample row details (top 15 by return + bottom 5)
    df_sorted = df.sort_values("ret_net", ascending=False)
    results["top_15_winners"] = df_sorted.head(15)[
        ["symbol", "listing_date", "day1_high_ret", "ret_net", "exit_reason", "hold_days_actual"]
    ].to_dict(orient="records")
    results["bottom_5_losers"] = df_sorted.tail(5)[
        ["symbol", "listing_date", "day1_high_ret", "ret_net", "exit_reason", "hold_days_actual"]
    ].to_dict(orient="records")

    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    log.info("\n%s", json.dumps({k: v for k, v in results.items()
                                  if k not in ("top_15_winners", "bottom_5_losers", "config")},
                                 indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
