"""R-2-bis — Day-14 early-exit variant for lifecycle_pump_decay.

Tests an EXIT-modifier policy (not entry filter). Entry: Day 1 close short
(same as R-4 PASS baseline). Exit:
  - At Day 14, compute vol_cliff = mean(daily_vol[7:14]) / day1_vol.
  - If vol_cliff >= threshold (decay invalidated): exit at Day 14 close.
  - Else (decay confirmed): hold to Day 30 close OR SL +50%.

Compares:
  baseline      ret_d1_30 (or SL hit between Day 1 and Day 30)
  early_exit    ret_d1_14 if vol_cliff>=thresh else ret_d1_30

For each threshold ∈ {0.30, 0.35, 0.40, 0.50, 0.70}, reports:
  - cohort split (n_invalidated / n_confirmed)
  - baseline cohort stats (R-2 baseline reference)
  - early_exit cohort stats
  - difference: median uplift_pct, win_rate change
  - subcohort-level analysis on invalidated listings only:
      baseline_invalidated ret_d1_30   (what we WOULD have gotten holding)
      ee_invalidated       ret_d1_14   (what we get exiting early)

Output: backend/runs/research_track/listing_volume_cliff/r2bis_early_exit_metrics.json

Uses the EXACT same cohort + price data as R-2 (162 listings, fee 8bps).
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
log = logging.getLogger("r2bis_early_exit")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "listing_volume_cliff" / "r2bis_early_exit_metrics.json"

FEE_ROUND_TRIP = 0.0008
SL_LEVEL = 0.50
HOLD_DAYS_END = 30
EARLY_EXIT_DAY = 14
THRESHOLD_GRID = [0.30, 0.35, 0.40, 0.50, 0.70]


def load_daily(db, sym: str) -> pd.DataFrame:
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp LIMIT 100000"
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


def short_sim(daily: pd.DataFrame, entry_idx: int, end_idx_target: int,
              sl_level: float) -> dict | None:
    """Short at entry_idx close, exit at end_idx_target close OR SL +sl_level intra-bar."""
    if entry_idx >= len(daily) or end_idx_target >= len(daily):
        return None
    entry_price = float(daily.iloc[entry_idx]["close"])
    if entry_price <= 0:
        return None
    sl_trigger = entry_price * (1.0 + sl_level)
    exit_idx, exit_price, exit_reason = end_idx_target, float(daily.iloc[end_idx_target]["close"]), "time"
    for i in range(entry_idx + 1, end_idx_target + 1):
        if float(daily.iloc[i]["high"]) >= sl_trigger:
            exit_idx, exit_price, exit_reason = i, sl_trigger, "sl"
            break
    ret_gross = (entry_price - exit_price) / entry_price
    return {
        "ret_net": float(ret_gross - FEE_ROUND_TRIP),
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
        "win_rate_positive": round(float((arr > 0).mean()), 3),
        "t_stat": round(float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), 2) if len(arr) > 1 and arr.std() > 0 else None,
        "std_pct": round(float(arr.std(ddof=1)) * 100, 2) if len(arr) > 1 else None,
    }


def main() -> int:
    listings = json.loads(LISTINGS_PATH.read_text())
    db = SessionLocal()
    today = date.today()
    records = []
    skipped = 0

    for sym, meta in listings.items():
        try:
            if meta.get("contract_type") != "PERPETUAL":
                continue
            ld = datetime.strptime(meta["onboard_date"], "%Y-%m-%d").date()
            age = (today - ld).days
            if age < 30 or age > 365:
                continue
            daily = load_daily(db, sym)
            if daily.empty or len(daily) < 31:
                skipped += 1
                continue
            entry_pos = daily.index.get_indexer([pd.Timestamp(ld)], method="nearest")[0]
            entry_actual = daily.index[entry_pos].date()
            if abs((entry_actual - ld).days) > 2:
                continue
            if entry_pos + HOLD_DAYS_END >= len(daily):
                continue

            day1_vol = float(daily.iloc[entry_pos]["volume"])
            if day1_vol <= 0:
                continue
            day7_14_vol = daily.iloc[entry_pos + 7:entry_pos + 14]["volume"].astype(float)
            if len(day7_14_vol) < 5:
                continue
            vol_cliff = float(day7_14_vol.mean()) / day1_vol if day1_vol > 0 else None
            if vol_cliff is None:
                continue

            sim_d1_30 = short_sim(daily, entry_pos, entry_pos + HOLD_DAYS_END, SL_LEVEL)
            sim_d1_14 = short_sim(daily, entry_pos, entry_pos + EARLY_EXIT_DAY, SL_LEVEL)
            if sim_d1_30 is None or sim_d1_14 is None:
                continue

            records.append({
                "symbol": sym,
                "vol_cliff": vol_cliff,
                "ret_d1_30": sim_d1_30["ret_net"],
                "ret_d1_14": sim_d1_14["ret_net"],
                "d1_30_exit_reason": sim_d1_30["exit_reason"],
                "d1_14_exit_reason": sim_d1_14["exit_reason"],
                "listing_date": meta["onboard_date"],
            })
        except Exception as exc:
            log.warning("[%s] %s", sym, exc)
            skipped += 1

    log.info("cohort: %d records (skipped %d)", len(records), skipped)
    if not records:
        log.error("empty cohort — aborting")
        return 1

    df = pd.DataFrame(records)
    df["quarter"] = pd.to_datetime(df["listing_date"]).dt.to_period("Q").astype(str)

    baseline_stats = cohort_stats(df["ret_d1_30"].tolist())
    log.info("baseline (hold-30 all): %s", baseline_stats)

    threshold_results = {}
    for thresh in THRESHOLD_GRID:
        invalidated = df["vol_cliff"] >= thresh
        n_inv = int(invalidated.sum())
        n_conf = int((~invalidated).sum())

        # Early-exit variant: use ret_d1_14 for invalidated, ret_d1_30 for confirmed
        ee_rets = np.where(invalidated, df["ret_d1_14"], df["ret_d1_30"])
        ee_stats = cohort_stats(ee_rets.tolist())

        # Sub-cohort analysis: what did invalidated listings do under each policy?
        sub_baseline = cohort_stats(df.loc[invalidated, "ret_d1_30"].tolist()) if n_inv > 0 else {"n": 0}
        sub_ee = cohort_stats(df.loc[invalidated, "ret_d1_14"].tolist()) if n_inv > 0 else {"n": 0}
        # Confirmed sub-cohort (same under both policies)
        sub_confirmed = cohort_stats(df.loc[~invalidated, "ret_d1_30"].tolist()) if n_conf > 0 else {"n": 0}

        threshold_results[f"{thresh:.2f}"] = {
            "threshold": thresh,
            "n_invalidated": n_inv,
            "n_confirmed": n_conf,
            "early_exit_full_cohort": ee_stats,
            "baseline_full_cohort_reference": baseline_stats,
            "invalidated_subcohort_baseline_hold30": sub_baseline,
            "invalidated_subcohort_early_exit_d14": sub_ee,
            "confirmed_subcohort": sub_confirmed,
            "uplift_median_pct": (
                round(ee_stats.get("median_pct", 0) - baseline_stats.get("median_pct", 0), 2)
                if ee_stats.get("median_pct") is not None else None
            ),
            "uplift_mean_pct": (
                round(ee_stats.get("mean_pct", 0) - baseline_stats.get("mean_pct", 0), 2)
                if ee_stats.get("mean_pct") is not None else None
            ),
            "uplift_win_rate": (
                round(ee_stats.get("win_rate_positive", 0) - baseline_stats.get("win_rate_positive", 0), 3)
                if ee_stats.get("win_rate_positive") is not None else None
            ),
            "subcohort_invalidated_avoid_loss_pct": (
                round(sub_ee.get("mean_pct", 0) - sub_baseline.get("mean_pct", 0), 2)
                if n_inv > 0 else None
            ),
        }

    # Quarterly breakdown at threshold 0.40 (default)
    quarterly = {}
    default_thresh = 0.40
    for q, g in df.groupby("quarter"):
        invalidated_q = g["vol_cliff"] >= default_thresh
        ee_q = np.where(invalidated_q, g["ret_d1_14"], g["ret_d1_30"])
        quarterly[q] = {
            "n_total": len(g),
            "n_invalidated": int(invalidated_q.sum()),
            "baseline_hold30": cohort_stats(g["ret_d1_30"].tolist()),
            "early_exit_d14_thresh040": cohort_stats(ee_q.tolist()),
        }

    out = {
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP,
            "sl_level": SL_LEVEL,
            "hold_days_end": HOLD_DAYS_END,
            "early_exit_day": EARLY_EXIT_DAY,
            "threshold_grid": THRESHOLD_GRID,
            "vol_cliff_formula": "mean(daily_vol[7:14]) / day1_vol",
        },
        "cohort": {
            "n_total": len(records),
            "skipped_data_issues": skipped,
        },
        "baseline_reference_hold30": baseline_stats,
        "threshold_grid_results": threshold_results,
        "quarterly_breakdown_thresh040": quarterly,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    log.info("written %s", OUT_PATH)

    # Headline summary
    log.info("\n=== SUMMARY (early exit at Day 14 if vol_cliff>=threshold) ===")
    log.info("baseline hold-30: median=%.2f%% win=%.3f n=%d",
             baseline_stats["median_pct"], baseline_stats["win_rate_positive"], baseline_stats["n"])
    for thresh in THRESHOLD_GRID:
        r = threshold_results[f"{thresh:.2f}"]
        ee = r["early_exit_full_cohort"]
        sub_b = r["invalidated_subcohort_baseline_hold30"]
        sub_e = r["invalidated_subcohort_early_exit_d14"]
        log.info("thresh=%.2f n_inv=%d/%d  full: med=%.2f%%(Δ%.2f%%) win=%.3f(Δ%+.3f)  inv-sub: hold30 med=%.2f%% / d14 med=%.2f%% (Δ%+.2f%%)",
                 thresh, r["n_invalidated"], r["n_invalidated"]+r["n_confirmed"],
                 ee["median_pct"], r["uplift_median_pct"],
                 ee["win_rate_positive"], r["uplift_win_rate"],
                 sub_b.get("median_pct", 0), sub_e.get("median_pct", 0),
                 (sub_e.get("median_pct", 0) - sub_b.get("median_pct", 0)) if sub_b.get("n", 0) > 0 else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
