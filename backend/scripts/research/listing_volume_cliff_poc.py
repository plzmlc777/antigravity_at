"""paradigm-architect generated R-1 PoC — listing_volume_cliff.

Hypothesis: Listings whose Day 7-14 average daily volume drops below 30% of
Day 1 volume have been "abandoned" by traders. Remaining holders face
thinner bid depth and dump into next-30-day decay disproportionately
harder than non-abandoned listings.

Two strategy variants are tested:

  VARIANT-LF (LIFECYCLE AMPLIFIER):
    Same trade as lifecycle_pump_decay (short Day 1 close, exit Day 30
    OR SL +50%), BUT condition entry on Day 14 vol_cliff measurement.
    Note: in real-time, Day 14 measurement is NOT available at Day 1
    entry — this variant is RETROSPECTIVE only, to test whether
    vol_cliff is a useful predictor.

  VARIANT-D14 (REAL-TIME):
    Wait until Day 14. Compute vol_cliff = mean(daily_vol[7:14]) / day1_vol.
    If vol_cliff < threshold (0.30): short Day 14 close, exit Day 30 OR
    SL +50%. Hold ~16 days.
    This is the TRADEABLE strategy — Day 14 entry uses observable data.

Sub-hypotheses:

  (a) RETROSPECTIVE strat-LF vs baseline lifecycle:
      Does filtering lifecycle cohort by vol_cliff < 0.30 increase median
      return / win rate? OR does it decrease them (signal is uniform)?
      → tests whether vol_cliff is a meaningful predictor.

  (b) STRATIFICATION: cohort split by vol_cliff buckets:
      {<0.15, 0.15-0.30, 0.30-0.60, >0.60}
      Each bucket's lifecycle Day1→Day30 short return distribution.

  (c) REAL-TIME strat-D14 cohort statistics:
      Median return + win rate of "short at Day 14 if vol_cliff < 0.30,
      exit Day 30" trades. Compared to fee floor.

  (d) Permutation test on (c): is vol_cliff < 0.30 SIGNAL non-trivial
      vs random listings shorted at Day 14?

Cohort: same 167-symbol listing pool (age 30-365 days) with ≥30 days
of post-listing 1m ohlcv.

Output: backend/runs/research_track/listing_volume_cliff/poc__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("listing_volume_cliff_poc")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "listing_volume_cliff" / "poc__metrics.json"

FEE_ROUND_TRIP = 0.0008
SL_LEVEL = 0.50
VOL_CLIFF_THRESHOLD = 0.30   # < 30% = abandoned
VOL_CLIFF_BUCKETS = [(-np.inf, 0.15), (0.15, 0.30), (0.30, 0.60), (0.60, np.inf)]


def load_daily(db, sym: str) -> pd.DataFrame:
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
    return pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()


def simulate_short(daily: pd.DataFrame, entry_idx: int, hold_days: int,
                   sl_level: float) -> dict | None:
    if entry_idx >= len(daily) - 1:
        return None
    entry_price = float(daily.iloc[entry_idx]["close"])
    if entry_price <= 0:
        return None
    sl_trigger = entry_price * (1.0 + sl_level)
    max_idx = min(entry_idx + hold_days, len(daily) - 1)
    exit_idx, exit_price, exit_reason = max_idx, float(daily.iloc[max_idx]["close"]), "time"
    for i in range(entry_idx + 1, max_idx + 1):
        if float(daily.iloc[i]["high"]) >= sl_trigger:
            exit_idx, exit_price, exit_reason = i, sl_trigger, "sl"
            break
    ret_gross = (entry_price - exit_price) / entry_price
    return {
        "ret_net": float(ret_gross - FEE_ROUND_TRIP),
        "ret_gross": float(ret_gross),
        "exit_reason": exit_reason,
        "hold_days_actual": int(exit_idx - entry_idx),
    }


def cohort_stats(rets: list[float]) -> dict:
    if not rets:
        return {"n": 0}
    arr = np.array(rets)
    return {
        "n": len(arr),
        "mean_pct": round(float(arr.mean()) * 100, 2),
        "median_pct": round(float(np.median(arr)) * 100, 2),
        "std_pct": round(float(arr.std(ddof=1)) * 100, 2) if len(arr) > 1 else None,
        "t_stat": round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2) if len(arr) > 1 and arr.std() > 0 else None,
        "win_rate_positive": round(float((arr > 0).mean()), 3),
        "p25_pct": round(float(np.percentile(arr, 25)) * 100, 2),
        "p75_pct": round(float(np.percentile(arr, 75)) * 100, 2),
    }


def permutation_test(cohort_rets: dict, target_rets: list[float], n_perm: int = 500,
                     subset_size: int = None) -> dict:
    """Null: from same cohort, randomly sample subset_size trades and compute median.
    Test whether the vol_cliff-filtered cohort's median is extreme vs random subsets
    of equal size from the full cohort."""
    if subset_size is None:
        subset_size = len(target_rets)
    full_pool = list(cohort_rets.values())
    if subset_size > len(full_pool):
        return {"skip": "subset_too_large"}
    rng = np.random.default_rng(42)
    actual_median = float(np.median(target_rets))
    null_medians = []
    for _ in range(n_perm):
        sample = rng.choice(full_pool, size=subset_size, replace=False)
        null_medians.append(float(np.median(sample)))
    null_arr = np.array(null_medians)
    p_one = float((null_arr >= actual_median).mean())
    return {
        "actual_median_pct": round(actual_median * 100, 2),
        "null_median_mean_pct": round(float(null_arr.mean()) * 100, 2),
        "null_median_std_pct": round(float(null_arr.std()) * 100, 2),
        "p_value_one_sided": round(p_one, 4),
        "sigma": round((actual_median - null_arr.mean()) / null_arr.std(), 2) if null_arr.std() > 0 else None,
    }


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    listings = json.loads(LISTINGS_PATH.read_text())
    today = date.today()
    db = SessionLocal()
    try:
        syms = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
        )).fetchall()})

        records = []
        for sym in syms:
            if sym not in listings:
                continue
            ld = datetime.strptime(listings[sym]["onboard_date"], "%Y-%m-%d").date()
            age = (today - ld).days
            if age < 30 or age > 365:
                continue
            daily = load_daily(db, sym)
            if daily.empty or len(daily) < 31:
                continue
            ld_ts = pd.Timestamp(ld)
            entry_pos = daily.index.get_indexer([ld_ts], method="nearest")[0]
            entry_actual = daily.index[entry_pos].date()
            if abs((entry_actual - ld).days) > 2:
                continue
            # Need at least 30 days post-listing
            if entry_pos + 30 >= len(daily):
                continue

            day1_vol = float(daily.iloc[entry_pos]["volume"])
            if day1_vol <= 0:
                continue
            day7_14_vol = daily.iloc[entry_pos + 7:entry_pos + 14]["volume"].astype(float)
            if len(day7_14_vol) < 5:
                continue
            mean_vol_7_14 = float(day7_14_vol.mean())
            vol_cliff = mean_vol_7_14 / day1_vol if day1_vol > 0 else None
            if vol_cliff is None:
                continue

            # Lifecycle Day1 → Day30 short
            sim_d1 = simulate_short(daily, entry_pos, 30, SL_LEVEL)
            # Day14 → Day30 short (16-day hold)
            sim_d14 = simulate_short(daily, entry_pos + 14, 16, SL_LEVEL)
            if sim_d1 is None or sim_d14 is None:
                continue

            records.append({
                "symbol": sym,
                "listing_date": str(ld),
                "year_quarter": f"{ld.year}Q{(ld.month-1)//3+1}",
                "vol_cliff": vol_cliff,
                "day1_vol": day1_vol,
                "mean_vol_7_14": mean_vol_7_14,
                "ret_d1_30": sim_d1["ret_net"],
                "exit_reason_d1": sim_d1["exit_reason"],
                "ret_d14_30": sim_d14["ret_net"],
                "exit_reason_d14": sim_d14["exit_reason"],
            })
    finally:
        db.close()

    if not records:
        OUT_PATH.write_text(json.dumps({"error": "no records"}, indent=2))
        return 1

    df = pd.DataFrame(records)
    log.info("cohort: %d listings", len(df))
    log.info("vol_cliff distribution: p25=%.3f median=%.3f p75=%.3f mean=%.3f",
             df["vol_cliff"].quantile(0.25), df["vol_cliff"].median(),
             df["vol_cliff"].quantile(0.75), df["vol_cliff"].mean())

    # ─── (a) Baseline lifecycle vs vol_cliff filtered ───
    baseline = cohort_stats(df["ret_d1_30"].tolist())
    low_cliff_df = df[df["vol_cliff"] < VOL_CLIFF_THRESHOLD]
    high_cliff_df = df[df["vol_cliff"] >= VOL_CLIFF_THRESHOLD]
    low_lf = cohort_stats(low_cliff_df["ret_d1_30"].tolist())
    high_lf = cohort_stats(high_cliff_df["ret_d1_30"].tolist())

    # ─── (b) Vol cliff bucket stratification ───
    bucket_stats = {}
    for lo, hi in VOL_CLIFF_BUCKETS:
        sub = df[(df["vol_cliff"] >= lo) & (df["vol_cliff"] < hi)]
        label = f"vol_cliff_{lo:.2f}_{hi:.2f}" if not np.isinf(hi) else f"vol_cliff_ge_{lo:.2f}"
        if np.isinf(lo):
            label = f"vol_cliff_lt_{hi:.2f}"
        bucket_stats[label] = cohort_stats(sub["ret_d1_30"].tolist())

    # ─── (c) Real-time D14 strat — short at Day 14 IF vol_cliff < threshold ───
    d14_filtered = df[df["vol_cliff"] < VOL_CLIFF_THRESHOLD]
    d14_strat = cohort_stats(d14_filtered["ret_d14_30"].tolist())
    d14_all = cohort_stats(df["ret_d14_30"].tolist())

    # ─── (d) Permutation test on D14 strat ───
    cohort_d14_dict = {r["symbol"]: r["ret_d14_30"] for r in records}
    perm = permutation_test(cohort_d14_dict, d14_filtered["ret_d14_30"].tolist(), n_perm=500)

    # ─── Bonus: quarterly fold of D14 strat ───
    quarterly = {}
    for q in sorted(d14_filtered["year_quarter"].unique()):
        q_df = d14_filtered[d14_filtered["year_quarter"] == q]
        if len(q_df) < 5:
            continue
        quarterly[q] = {
            "n": len(q_df),
            **{k: v for k, v in cohort_stats(q_df["ret_d14_30"].tolist()).items()
               if k in ("median_pct", "mean_pct", "win_rate_positive")}
        }

    # Correlation: vol_cliff vs ret_d1_30 (lower cliff = stronger decay?)
    vc_corr = float(df[["vol_cliff", "ret_d1_30"]].corr().iloc[0, 1])

    out = {
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP,
            "sl_level": SL_LEVEL,
            "vol_cliff_threshold": VOL_CLIFF_THRESHOLD,
        },
        "cohort": {
            "n_total": len(df),
            "vol_cliff_distribution": {
                "p25": round(float(df["vol_cliff"].quantile(0.25)), 4),
                "median": round(float(df["vol_cliff"].median()), 4),
                "p75": round(float(df["vol_cliff"].quantile(0.75)), 4),
                "mean": round(float(df["vol_cliff"].mean()), 4),
                "n_low": int((df["vol_cliff"] < VOL_CLIFF_THRESHOLD).sum()),
                "n_high": int((df["vol_cliff"] >= VOL_CLIFF_THRESHOLD).sum()),
            },
        },
        "vol_cliff_vs_ret_d1_30_corr": round(vc_corr, 4),
        "hyp_a_baseline_vs_filter": {
            "baseline_all_listings_short_d1_30": baseline,
            "filtered_low_cliff_short_d1_30": low_lf,
            "filtered_high_cliff_short_d1_30": high_lf,
        },
        "hyp_b_vol_cliff_buckets": bucket_stats,
        "hyp_c_d14_realtime_strat": {
            "filtered_only_low_cliff": d14_strat,
            "all_listings_for_compare": d14_all,
        },
        "hyp_d_perm_test_d14_filtered": perm,
        "quarterly_folds_d14_filtered": quarterly,
        "top_5_winners_d14_filtered": d14_filtered.nlargest(5, "ret_d14_30")[
            ["symbol", "vol_cliff", "ret_d14_30", "exit_reason_d14"]
        ].to_dict(orient="records"),
        "bottom_5_losers_d14_filtered": d14_filtered.nsmallest(5, "ret_d14_30")[
            ["symbol", "vol_cliff", "ret_d14_30", "exit_reason_d14"]
        ].to_dict(orient="records"),
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
