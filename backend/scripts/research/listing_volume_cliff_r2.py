"""Direction architect R-2 — listing_volume_cliff promotion analysis.

R-1 confirmed vol_cliff < 0.30 is powerful retrospective amplifier of
lifecycle_pump_decay (median +21.6 → +34.9, win 58 → 69). R-2 extends:

1. ENTRY GRID — test Day 1 / Day 3 / Day 7 / Day 10 / Day 14 entries with
   vol_cliff filter applied (when observable). For each entry, hold to
   Day 30 OR SL +50%.

2. THRESHOLD GRID — vol_cliff ∈ {0.10, 0.15, 0.20, 0.25, 0.30, 0.40}.
   Find robust plateau.

3. FORECASTER — try predicting Day 7-14 vol_cliff from Day 1-3 features:
   - day1_close / day1_high
   - day1_volume_frontload (first 4h vol / day1 vol)
   - day2_3_avg_volume / day1_volume (early decay rate)
   - day1_3_close_range (volatility)
   - day1_close / day1_open (pump retention)
   Simple linear regression. R² > 0.30 = useful forecaster.

4. AMPLIFIER PERMUTATION — bootstrap test: re-sample lifecycle cohort
   1000 times with random vol_cliff subset of size 85; compute median
   distribution. If actual amplified median (+34.9) is in extreme tail,
   vol_cliff info IS additive.

5. QUARTERLY ROBUSTNESS — vol_cliff filter applied at each quarter,
   compare to baseline lifecycle's quarterly results.

Output: backend/runs/research_track/listing_volume_cliff/r2__metrics.json
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
log = logging.getLogger("listing_volume_cliff_r2")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "listing_volume_cliff" / "r2__metrics.json"

FEE_ROUND_TRIP = 0.0008
SL_LEVEL = 0.50
HOLD_DAYS_END = 30
ENTRY_DAYS_GRID = [1, 3, 7, 10, 14]
THRESHOLD_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]


def load_daily_with_intraday(db, sym: str):
    """Returns (daily_df, intraday_day1_df) — intraday is first 1440 minutes."""
    rows = db.execute(text(
        "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp LIMIT 100000"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.DataFrame(), pd.DataFrame()
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
    # Day 1 intraday (first 1440 minutes from earliest ts)
    day1_intra = df.iloc[:1440] if len(df) >= 1440 else df
    return daily, day1_intra


def short_sim(daily: pd.DataFrame, entry_idx: int, end_idx_target: int,
              sl_level: float) -> dict | None:
    """Short at entry_idx close, exit at end_idx_target close OR SL +sl_level."""
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
    }


def compute_day1_3_features(intraday: pd.DataFrame, daily: pd.DataFrame, entry_pos: int) -> dict:
    """Day 1-3 microstructure features for predicting vol_cliff."""
    if entry_pos + 3 >= len(daily):
        return {}
    day1 = daily.iloc[entry_pos]
    day1_open = float(day1["open"])
    day1_high = float(day1["high"])
    day1_low = float(day1["low"])
    day1_close = float(day1["close"])
    day1_vol = float(day1["volume"])
    if day1_open <= 0 or day1_high <= 0:
        return {}

    day1_close_to_high = day1_close / day1_high if day1_high > 0 else None
    day1_pump_ratio = day1_close / day1_open - 1 if day1_open > 0 else None
    day1_range = (day1_high - day1_low) / day1_open if day1_open > 0 else None

    # Day 1 intraday volume frontload: first 4h of trading
    vol_first_4h = float(intraday.iloc[:240]["volume"].sum()) if len(intraday) >= 240 else 0
    vol_frontload = vol_first_4h / day1_vol if day1_vol > 0 else None

    day2_vol = float(daily.iloc[entry_pos + 1]["volume"])
    day3_vol = float(daily.iloc[entry_pos + 2]["volume"])
    day2_3_avg = (day2_vol + day3_vol) / 2
    early_decay = day2_3_avg / day1_vol if day1_vol > 0 else None

    return {
        "day1_close_to_high": day1_close_to_high,
        "day1_pump_ratio": day1_pump_ratio,
        "day1_range_pct": day1_range,
        "day1_vol_frontload_4h": vol_frontload,
        "day2_3_vs_day1_vol": early_decay,
    }


def amplifier_permutation(all_d1_rets: list[float], filtered_d1_rets: list[float],
                          n_perm: int = 1000, seed: int = 42) -> dict:
    """Null: random subset of size len(filtered) from all cohort. Compare
    actual filtered median to null distribution."""
    rng = np.random.default_rng(seed)
    actual_median = float(np.median(filtered_d1_rets))
    subset_size = len(filtered_d1_rets)
    null_medians = []
    for _ in range(n_perm):
        idx = rng.choice(len(all_d1_rets), size=subset_size, replace=False)
        null_medians.append(float(np.median([all_d1_rets[i] for i in idx])))
    null_arr = np.array(null_medians)
    p_one = float((null_arr >= actual_median).mean())
    return {
        "actual_median_pct": round(actual_median * 100, 2),
        "null_median_mean_pct": round(float(null_arr.mean()) * 100, 2),
        "null_median_std_pct": round(float(null_arr.std()) * 100, 2),
        "n_null_draws": n_perm,
        "p_value_one_sided": round(p_one, 4),
        "sigma": round((actual_median - null_arr.mean()) / null_arr.std(), 2) if null_arr.std() > 0 else None,
    }


def fit_forecaster(records: list[dict]) -> dict:
    """Linear regression: predict vol_cliff from Day 1-3 features."""
    df = pd.DataFrame(records).dropna()
    feat_cols = ["day1_close_to_high", "day1_pump_ratio", "day1_range_pct",
                 "day1_vol_frontload_4h", "day2_3_vs_day1_vol"]
    for c in feat_cols:
        if c not in df.columns:
            return {"skip": f"missing feature {c}"}
    df = df.dropna(subset=feat_cols + ["vol_cliff"])
    if len(df) < 30:
        return {"skip": "n<30 for fit"}
    X = df[feat_cols].values
    y = df["vol_cliff"].values
    # Solve OLS via normal equations
    X_aug = np.column_stack([np.ones(len(X)), X])
    coefs, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    y_pred = X_aug @ coefs
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None

    # In-sample: classify forecasted vol_cliff < 0.30 vs actual
    pred_low = y_pred < 0.30
    actual_low = y < 0.30
    if pred_low.sum() > 0:
        precision = float((pred_low & actual_low).sum() / pred_low.sum())
    else:
        precision = None
    if actual_low.sum() > 0:
        recall = float((pred_low & actual_low).sum() / actual_low.sum())
    else:
        recall = None

    return {
        "n_fit": len(df),
        "features": feat_cols,
        "coefs_intercept": round(float(coefs[0]), 4),
        "coefs_by_feature": {c: round(float(coef), 4) for c, coef in zip(feat_cols, coefs[1:])},
        "r_squared": round(float(r2), 4) if r2 is not None else None,
        "in_sample_precision_low_cliff": round(precision, 3) if precision is not None else None,
        "in_sample_recall_low_cliff": round(recall, 3) if recall is not None else None,
        "pred_low_actual_low_lift": round((precision / (actual_low.mean()) - 1), 3)
            if precision is not None and actual_low.mean() > 0 else None,
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
            daily, intra = load_daily_with_intraday(db, sym)
            if daily.empty or len(daily) < 31 or intra.empty:
                continue
            ld_ts = pd.Timestamp(ld)
            entry_pos = daily.index.get_indexer([ld_ts], method="nearest")[0]
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
            vol_cliff = float(day7_14_vol.mean()) / day1_vol

            feats = compute_day1_3_features(intra, daily, entry_pos)

            # Simulate short at each entry day point, exit Day 30
            entry_sims = {}
            for ed in ENTRY_DAYS_GRID:
                ep = entry_pos + (ed - 1)  # Day 1 entry = entry_pos
                target = entry_pos + HOLD_DAYS_END - 1
                sim = short_sim(daily, ep, target, SL_LEVEL)
                if sim:
                    entry_sims[f"d{ed}"] = sim["ret_net"]

            rec = {
                "symbol": sym,
                "listing_date": str(ld),
                "year_quarter": f"{ld.year}Q{(ld.month-1)//3+1}",
                "vol_cliff": vol_cliff,
                **{f"ret_{k}": v for k, v in entry_sims.items()},
                **feats,
            }
            records.append(rec)
    finally:
        db.close()

    df = pd.DataFrame(records)
    log.info("cohort: %d listings, features computed", len(df))

    # ─── 1. ENTRY × THRESHOLD GRID ───
    entry_threshold_grid = []
    for ed in ENTRY_DAYS_GRID:
        ret_col = f"ret_d{ed}"
        if ret_col not in df.columns:
            continue
        for th in THRESHOLD_GRID:
            sub = df[df["vol_cliff"] < th][ret_col].dropna()
            if len(sub) < 10:
                continue
            entry_threshold_grid.append({
                "entry_day": ed,
                "vol_cliff_threshold": th,
                **cohort_stats(sub.tolist()),
            })

    # ─── 2. FORECASTER (vol_cliff from Day 1-3 features) ───
    forecaster = fit_forecaster(records)

    # ─── 3. AMPLIFIER PERM TEST (Day 1 filter) ───
    all_d1 = df["ret_d1"].dropna().tolist()
    filt_d1 = df[df["vol_cliff"] < 0.30]["ret_d1"].dropna().tolist()
    perm = amplifier_permutation(all_d1, filt_d1, n_perm=1000)

    # ─── 4. QUARTERLY × ENTRY × FILTER ───
    quarterly_eval = {}
    for q in sorted(df["year_quarter"].unique()):
        q_df = df[df["year_quarter"] == q]
        if len(q_df) < 5:
            continue
        q_data = {"n_total": len(q_df)}
        for ed in [1, 7, 14]:
            ret_col = f"ret_d{ed}"
            if ret_col not in df.columns:
                continue
            # Filter low cliff
            sub_filt = q_df[q_df["vol_cliff"] < 0.30][ret_col].dropna()
            sub_all = q_df[ret_col].dropna()
            if len(sub_filt) >= 3:
                q_data[f"d{ed}_filtered"] = cohort_stats(sub_filt.tolist())
            if len(sub_all) >= 3:
                q_data[f"d{ed}_all"] = cohort_stats(sub_all.tolist())
        quarterly_eval[q] = q_data

    # ─── 5. BEST CELL identification ───
    plateau = [c for c in entry_threshold_grid if c["median_pct"] >= 20.0 and c["win_rate_positive"] >= 0.60]
    plateau_sorted = sorted(plateau, key=lambda c: (-c["median_pct"], -c["win_rate_positive"]))

    out = {
        "config": {
            "fee_round_trip": FEE_ROUND_TRIP,
            "sl_level": SL_LEVEL,
            "hold_days_end": HOLD_DAYS_END,
            "entry_days_grid": ENTRY_DAYS_GRID,
            "threshold_grid": THRESHOLD_GRID,
        },
        "cohort": {
            "n_total": len(df),
            "vol_cliff_distribution": {
                "p25": round(float(df["vol_cliff"].quantile(0.25)), 4),
                "median": round(float(df["vol_cliff"].median()), 4),
                "p75": round(float(df["vol_cliff"].quantile(0.75)), 4),
            },
        },
        "entry_x_threshold_grid": entry_threshold_grid,
        "plateau_cells_median_ge_20_win_ge_60": plateau_sorted,
        "n_plateau_cells": len(plateau),
        "amplifier_permutation_d1_lt_030": perm,
        "forecaster_vol_cliff_from_day1_3_features": forecaster,
        "quarterly_breakdown_d1_d7_d14": quarterly_eval,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    # Print key results
    log.info("amplifier perm: %s", json.dumps(perm))
    log.info("forecaster: %s", json.dumps({k: v for k, v in forecaster.items() if k != "features"}))
    log.info("top 5 plateau cells:")
    for c in plateau_sorted[:5]:
        log.info("  entry_day=%d thresh=%.2f n=%d median=%+.2f%% win=%.0f%%",
                 c["entry_day"], c["vol_cliff_threshold"], c["n"], c["median_pct"], c["win_rate_positive"]*100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
