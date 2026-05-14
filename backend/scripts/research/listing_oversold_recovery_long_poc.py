"""R-1 PoC — listing_oversold_recovery_long

Hypothesis: Listings whose cumulative DD from Day 1 close to any Day in [1..30]
reaches >= 40% (decay-confirmed oversold cohort) exhibit a mean-reversion
LONG bounce in the Day 30 -> Day 60 window.

Strategy: at Day 30 close, enter LONG. Exit: Day 60 close OR -25% stop-loss.

R-1 fail-fast (5 random sample of DD>=40% cohort):
  if mean <= 0 OR win_rate < 45%  -> graveyard

This R-1 actually runs the full small-sample to give us a confident verdict.

Output: backend/runs/research_track/listing_oversold_recovery_long/poc__metrics.json
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
log = logging.getLogger("listing_oversold_recovery_long_poc")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_DIR = ROOT / "runs" / "research_track" / "listing_oversold_recovery_long"
OUT_PATH = OUT_DIR / "poc__metrics.json"

DD_THRESHOLD = 0.40    # 40% cumulative drawdown from Day 1 close, measured over Days 1..30
ENTRY_DAY = 30         # enter LONG at Day 30 close
EXIT_DAY = 60          # exit at Day 60 close (default time exit)
SL_LEVEL = 0.25        # -25% long SL from entry
FEE_ROUND_TRIP = 0.0008
SAMPLE_N = 5           # R-1 random sample size for fail-fast
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


def compute_day30_dd(daily: pd.DataFrame, entry_pos: int) -> dict | None:
    """Compute cumulative DD from Day 1 close to lowest low in [Day 1, Day 30].
    entry_pos = index of Day 1 (listing day) in daily df.
    Returns dict with day1_close, min_close_in_30d, dd_pct, day30_close.
    """
    day1_close = float(daily.iloc[entry_pos]["close"])
    if day1_close <= 0:
        return None
    end_pos = entry_pos + ENTRY_DAY
    if end_pos >= len(daily):
        return None
    window = daily.iloc[entry_pos: end_pos + 1]
    min_close = float(window["close"].min())
    min_low = float(window["low"].min())  # use low for true DD
    day30_close = float(daily.iloc[end_pos]["close"])
    dd_close = (day1_close - min_close) / day1_close
    dd_low = (day1_close - min_low) / day1_close
    return {
        "day1_close": day1_close,
        "min_close_in_30d": min_close,
        "min_low_in_30d": min_low,
        "day30_close": day30_close,
        "dd_close_pct": dd_close,
        "dd_low_pct": dd_low,
    }


def simulate_long_with_sl(daily: pd.DataFrame, entry_pos: int,
                          sl_level: float, hold_days: int) -> dict | None:
    """LONG at daily[entry_pos].close. Exit on:
       (a) intra-day low <= entry * (1 - sl_level)  [SL]
       (b) day == entry_pos + hold_days             [time]
    """
    if entry_pos >= len(daily) - 1:
        return None
    entry_price = float(daily.iloc[entry_pos]["close"])
    if entry_price <= 0:
        return None
    sl_trigger = entry_price * (1.0 - sl_level)
    max_idx = min(entry_pos + hold_days, len(daily) - 1)
    if max_idx <= entry_pos:
        return None
    exit_idx = max_idx
    exit_price = float(daily.iloc[max_idx]["close"])
    exit_reason = "time"
    for i in range(entry_pos + 1, max_idx + 1):
        if float(daily.iloc[i]["low"]) <= sl_trigger:
            exit_idx = i
            exit_price = sl_trigger
            exit_reason = "sl"
            break
    ret_gross = (exit_price - entry_price) / entry_price  # long PnL
    ret_net = ret_gross - FEE_ROUND_TRIP
    return {
        "entry_idx": int(entry_pos),
        "exit_idx": int(exit_idx),
        "entry_price": float(entry_price),
        "exit_price": float(exit_price),
        "ret_gross": float(ret_gross),
        "ret_net": float(ret_net),
        "exit_reason": exit_reason,
        "hold_days_actual": int(exit_idx - entry_pos),
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
        "t_stat": round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2)
                   if len(arr) > 1 and arr.std() > 0 else None,
        "win_rate_positive": round(float((arr > 0).mean()), 3),
        "p25_pct": round(float(np.percentile(arr, 25)) * 100, 2) if len(arr) >= 4 else None,
        "p75_pct": round(float(np.percentile(arr, 75)) * 100, 2) if len(arr) >= 4 else None,
        "max_pct": round(float(arr.max()) * 100, 2),
        "min_pct": round(float(arr.min()) * 100, 2),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
        # Need at least 60 days post-listing to evaluate Day 30 -> Day 60
        if age < 62 or age > 365:
            continue
        candidates.append((sym, ld, age))
    log.info("cohort candidates (age 62-365d): %d", len(candidates))

    # Pass 1: identify DD>=40% subcohort using Day 1..Day 30 close-DD
    db = SessionLocal()
    rows_all = []
    try:
        for sym, ld, age in candidates:
            daily = load_daily_ohlcv(db, sym)
            if daily.empty or len(daily) < ENTRY_DAY + 5:
                continue
            ld_ts = pd.Timestamp(ld)
            try:
                entry_pos = daily.index.get_indexer([ld_ts], method="nearest")[0]
                entry_actual = daily.index[entry_pos].date()
                if abs((entry_actual - ld).days) > 2:
                    continue
            except Exception:
                continue

            dd_info = compute_day30_dd(daily, entry_pos)
            if dd_info is None:
                continue
            day30_pos = entry_pos + ENTRY_DAY
            if day30_pos >= len(daily) - 1:
                continue

            # Simulate Day 30 -> Day 60 LONG with -25% SL (only meaningful for DD>=40 cohort)
            sim = simulate_long_with_sl(daily, day30_pos, SL_LEVEL, EXIT_DAY - ENTRY_DAY)
            if sim is None:
                continue

            rows_all.append({
                "symbol": sym,
                "listing_date": str(ld),
                "year_quarter": f"{ld.year}Q{(ld.month-1)//3+1}",
                "age_days": age,
                "dd_close_pct": dd_info["dd_close_pct"],
                "dd_low_pct": dd_info["dd_low_pct"],
                "day1_close": dd_info["day1_close"],
                "day30_close": dd_info["day30_close"],
                "ret_net": sim["ret_net"],
                "ret_gross": sim["ret_gross"],
                "exit_reason": sim["exit_reason"],
                "hold_days_actual": sim["hold_days_actual"],
            })
    finally:
        db.close()

    if not rows_all:
        log.error("no rows produced")
        OUT_PATH.write_text(json.dumps({"error": "empty_cohort"}, indent=2))
        return 1

    df = pd.DataFrame(rows_all)
    log.info("processed %d listings (Day1->Day60 viable)", len(df))

    # DD>=40% subcohort (close-based)
    confirmed = df[df["dd_close_pct"] >= DD_THRESHOLD]
    log.info("DD_close>=%.0f%% confirmed cohort: %d / %d (%.1f%%)",
             DD_THRESHOLD * 100, len(confirmed), len(df), 100 * len(confirmed) / len(df))

    # Random sample 5 for R-1 PoC verdict
    rng = np.random.default_rng(SEED)
    if len(confirmed) >= SAMPLE_N:
        sample_idx = rng.choice(confirmed.index, size=SAMPLE_N, replace=False)
        sample_df = confirmed.loc[sample_idx]
    else:
        sample_df = confirmed

    # Compute stats on sample (R-1 fail-fast) and full confirmed (advisory)
    results = {
        "config": {
            "dd_threshold": DD_THRESHOLD,
            "entry_day": ENTRY_DAY,
            "exit_day": EXIT_DAY,
            "sl_level": SL_LEVEL,
            "fee_round_trip": FEE_ROUND_TRIP,
            "sample_n_for_r1": SAMPLE_N,
            "seed": SEED,
        },
        "cohort_summary": {
            "n_candidates": len(candidates),
            "n_processed": len(df),
            "n_dd40_confirmed_close": int((df["dd_close_pct"] >= DD_THRESHOLD).sum()),
            "n_dd40_confirmed_low": int((df["dd_low_pct"] >= DD_THRESHOLD).sum()),
            "dd_close_distribution": {
                "min_pct": round(float(df["dd_close_pct"].min()) * 100, 2),
                "p25_pct": round(float(df["dd_close_pct"].quantile(0.25)) * 100, 2),
                "median_pct": round(float(df["dd_close_pct"].median()) * 100, 2),
                "p75_pct": round(float(df["dd_close_pct"].quantile(0.75)) * 100, 2),
                "max_pct": round(float(df["dd_close_pct"].max()) * 100, 2),
            },
        },
        "r1_random_sample_long_30d_ret_net": cohort_stats(sample_df["ret_net"].tolist()),
        "advisory_full_confirmed_long_30d_ret_net": cohort_stats(confirmed["ret_net"].tolist()),
        "advisory_full_processed_long_30d_ret_net": cohort_stats(df["ret_net"].tolist()),
    }

    # Sample symbols for transparency
    results["r1_sample_rows"] = sample_df[
        ["symbol", "listing_date", "dd_close_pct", "ret_net", "exit_reason", "hold_days_actual"]
    ].to_dict(orient="records")

    # Top/bottom of confirmed cohort
    if len(confirmed):
        c_sorted = confirmed.sort_values("ret_net", ascending=False)
        results["confirmed_top5_winners"] = c_sorted.head(5)[
            ["symbol", "listing_date", "dd_close_pct", "ret_net", "exit_reason"]
        ].to_dict(orient="records")
        results["confirmed_bottom5_losers"] = c_sorted.tail(5)[
            ["symbol", "listing_date", "dd_close_pct", "ret_net", "exit_reason"]
        ].to_dict(orient="records")

    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    log.info("saved -> %s", OUT_PATH)
    log.info("\n%s", json.dumps({k: v for k, v in results.items()
                                  if k not in ("r1_sample_rows", "confirmed_top5_winners",
                                              "confirmed_bottom5_losers", "config")},
                                 indent=2, default=str))

    # R-1 fail-fast verdict
    sample_stats = results["r1_random_sample_long_30d_ret_net"]
    if sample_stats.get("n", 0) < SAMPLE_N:
        log.warning("sample size %d < %d — verdict deferred to advisory full cohort",
                    sample_stats.get("n", 0), SAMPLE_N)
        # Use full confirmed cohort as fallback
        sample_stats = results["advisory_full_confirmed_long_30d_ret_net"]
    mean_pct = sample_stats.get("mean_pct", 0) or 0
    win_rate = sample_stats.get("win_rate_positive", 0) or 0
    if mean_pct <= 0 or win_rate < 0.45:
        log.warning("R-1 FAIL-FAST: mean=%.2f%% win_rate=%.3f -> graveyard candidate",
                    mean_pct, win_rate)
        results["r1_verdict"] = "FAIL"
    else:
        log.info("R-1 PASS: mean=%.2f%% win_rate=%.3f", mean_pct, win_rate)
        results["r1_verdict"] = "PASS"
    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    return 0 if results["r1_verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
