"""Direction 1 R-3 — Listing Pump Decay robustness analysis.

R-2 (lifecycle_phase_r2.py) found σ=6.8 / p=0.000 / median +21.6% on n=167
cohort, but quarterly folds showed 2025Q3 FAILED (median -3.5%, win 48%)
while other quarters strong. R-3 investigates:

1. REGIME ANALYSIS: for each listing, compute BTC 30-day log return BEFORE
   the listing date as proxy for market regime. Stratify cohort by BTC
   regime (bear / neutral / bull) at entry — does the paradigm work
   conditionally?

2. SL × HOLD GRID SEARCH: re-simulate cohort with all combinations of:
   - SL_level ∈ {0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 1.00}
   - hold_days ∈ {7, 14, 21, 30, 45, 60}
   Report median return, win rate, max DD per cell. Identify robust
   plateau (not single optimal — overfit risk).

3. CONTEMPORANEOUS BTC: also compute BTC return DURING each listing's hold
   period. Is paradigm's PnL correlated with BTC's PnL? If yes, paradigm
   may be a disguised "short alts during bear" play. If no, paradigm has
   independent edge.

4. INVESTIGATION PROFILE for 2025Q3: what was BTC doing? listing density?
   What % of 2025Q3 cohort had specific shared features?

Output: backend/runs/research_track/lifecycle_phase/r3__metrics.json
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
log = logging.getLogger("lifecycle_phase_r3")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "r3__metrics.json"

PUMP_THRESHOLD = 0.30
FEE_ROUND_TRIP = 0.0008
BTC_TREND_LOOKBACK = 30  # days before listing
REGIME_BEAR_THRESHOLD = -0.05   # BTC 30d ret < -5% = bear
REGIME_BULL_THRESHOLD = +0.05   # BTC 30d ret > +5% = bull


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
    }).dropna()


def simulate_short(daily: pd.DataFrame, entry_idx: int, sl_level: float, hold_days: int) -> dict | None:
    if entry_idx >= len(daily):
        return None
    entry_price = daily.iloc[entry_idx]["close"]
    if entry_price <= 0:
        return None
    sl_trigger = entry_price * (1.0 + sl_level)
    max_idx = min(entry_idx + hold_days, len(daily) - 1)
    exit_idx, exit_price, exit_reason = max_idx, daily.iloc[max_idx]["close"], "time"
    for i in range(entry_idx + 1, max_idx + 1):
        if daily.iloc[i]["high"] >= sl_trigger:
            exit_idx, exit_price, exit_reason = i, sl_trigger, "sl"
            break
    ret_gross = (entry_price - exit_price) / entry_price
    return {
        "ret_net": float(ret_gross - FEE_ROUND_TRIP),
        "exit_reason": exit_reason,
        "hold_days_actual": int(exit_idx - entry_idx),
    }


def regime_label(btc_30d_ret: float) -> str:
    if btc_30d_ret < REGIME_BEAR_THRESHOLD:
        return "bear"
    if btc_30d_ret > REGIME_BULL_THRESHOLD:
        return "bull"
    return "neutral"


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    listings = json.loads(LISTINGS_PATH.read_text())
    today = date.today()

    db = SessionLocal()
    try:
        syms_in_db = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
        )).fetchall()})

        # Build cohort (same as R-2)
        candidates = []
        for sym in syms_in_db:
            if sym not in listings:
                continue
            ld = datetime.strptime(listings[sym]["onboard_date"], "%Y-%m-%d").date()
            age = (today - ld).days
            if age < 30 or age > 365:
                continue
            candidates.append((sym, ld, age))
        log.info("R-3 cohort candidates: %d", len(candidates))

        # BTC daily ohlcv for regime classification
        btc_daily = load_daily(db, "BTCUSDT")
        if btc_daily.empty:
            log.error("BTCUSDT ohlcv missing")
            return 1
        log.info("BTC daily: %d days (%s ~ %s)", len(btc_daily), btc_daily.index[0].date(), btc_daily.index[-1].date())

        # Compute BTC trend at each candidate's entry
        cohort_records = []
        symbol_daily = {}
        for sym, ld, _ in candidates:
            daily = load_daily(db, sym)
            if daily.empty or len(daily) < 30:
                continue
            ld_ts = pd.Timestamp(ld)
            try:
                entry_pos = daily.index.get_indexer([ld_ts], method="nearest")[0]
            except Exception:
                continue
            entry_actual = daily.index[entry_pos].date()
            if abs((entry_actual - ld).days) > 2:
                continue
            if entry_pos >= len(daily) - 30:
                continue

            # BTC 30d return ending at ld_ts
            try:
                btc_idx = btc_daily.index.get_indexer([ld_ts], method="nearest")[0]
            except Exception:
                continue
            if btc_idx < BTC_TREND_LOOKBACK:
                continue
            btc_close_now = float(btc_daily.iloc[btc_idx]["close"])
            btc_close_then = float(btc_daily.iloc[btc_idx - BTC_TREND_LOOKBACK]["close"])
            btc_30d_ret = (btc_close_now / btc_close_then - 1) if btc_close_then > 0 else 0.0

            # BTC contemporaneous return (during 30d hold)
            btc_idx_exit = min(btc_idx + 30, len(btc_daily) - 1)
            btc_close_exit = float(btc_daily.iloc[btc_idx_exit]["close"])
            btc_hold_ret = (btc_close_exit / btc_close_now - 1) if btc_close_now > 0 else 0.0

            day1_open = daily.iloc[entry_pos]["open"]
            day1_high = daily.iloc[entry_pos]["high"]
            day1_high_ret = (day1_high / day1_open - 1) if day1_open > 0 else 0

            cohort_records.append({
                "symbol": sym,
                "listing_date": str(ld),
                "year_quarter": f"{ld.year}Q{(ld.month-1)//3+1}",
                "entry_pos": entry_pos,
                "day1_high_ret": day1_high_ret,
                "pumped": day1_high_ret >= PUMP_THRESHOLD,
                "btc_30d_pre_ret": btc_30d_ret,
                "btc_30d_post_ret": btc_hold_ret,
                "regime": regime_label(btc_30d_ret),
            })
            symbol_daily[sym] = daily
    finally:
        db.close()

    df = pd.DataFrame(cohort_records)
    log.info("cohort built: %d trades with BTC regime tagged", len(df))

    # ────────── 1. Regime analysis at default (SL 50%, hold 30) ──────────
    DEFAULT_SL, DEFAULT_HOLD = 0.50, 30
    rets = []
    for _, r in df.iterrows():
        sim = simulate_short(symbol_daily[r["symbol"]], r["entry_pos"], DEFAULT_SL, DEFAULT_HOLD)
        rets.append(sim["ret_net"] if sim else np.nan)
    df["ret_net_default"] = rets
    df = df.dropna(subset=["ret_net_default"])

    regime_bucket = {}
    for regime in ["bear", "neutral", "bull"]:
        sub = df[df["regime"] == regime]
        if len(sub) > 0:
            regime_bucket[regime] = {
                "n": len(sub),
                "median_pct": round(float(sub["ret_net_default"].median()) * 100, 2),
                "mean_pct": round(float(sub["ret_net_default"].mean()) * 100, 2),
                "win_rate_positive": round(float((sub["ret_net_default"] > 0).mean()), 3),
                "btc_30d_pre_mean": round(float(sub["btc_30d_pre_ret"].mean()) * 100, 2),
            }

    # ────────── 2. Correlation: strategy PnL vs contemporaneous BTC ──────────
    corr = float(df[["ret_net_default", "btc_30d_post_ret"]].corr().iloc[0, 1])

    # ────────── 3. Quarterly + regime cross-tab ──────────
    quarterly_regime = {}
    for q in sorted(df["year_quarter"].unique()):
        q_df = df[df["year_quarter"] == q]
        quarterly_regime[q] = {
            "n": len(q_df),
            "median_ret_pct": round(float(q_df["ret_net_default"].median()) * 100, 2),
            "win_rate": round(float((q_df["ret_net_default"] > 0).mean()), 3),
            "regime_counts": {r: int(c) for r, c in q_df["regime"].value_counts().items()},
            "btc_30d_pre_mean_pct": round(float(q_df["btc_30d_pre_ret"].mean()) * 100, 2),
            "btc_30d_post_mean_pct": round(float(q_df["btc_30d_post_ret"].mean()) * 100, 2),
        }

    # ────────── 4. SL × HOLD GRID SEARCH ──────────
    SL_GRID = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 1.00]
    HOLD_GRID = [7, 14, 21, 30, 45, 60]
    grid = []
    for sl in SL_GRID:
        for hd in HOLD_GRID:
            rets = []
            for _, r in df.iterrows():
                sim = simulate_short(symbol_daily[r["symbol"]], r["entry_pos"], sl, hd)
                if sim:
                    rets.append(sim["ret_net"])
            if not rets:
                continue
            arr = np.array(rets)
            grid.append({
                "sl": sl,
                "hold": hd,
                "n": len(arr),
                "median_pct": round(float(np.median(arr)) * 100, 2),
                "mean_pct": round(float(arr.mean()) * 100, 2),
                "win_rate": round(float((arr > 0).mean()), 3),
                "p25_pct": round(float(np.percentile(arr, 25)) * 100, 2),
                "p75_pct": round(float(np.percentile(arr, 75)) * 100, 2),
            })

    # Find robust plateau: cells where median > 15% AND win_rate > 0.55
    plateau = [g for g in grid if g["median_pct"] > 15.0 and g["win_rate"] > 0.55]
    plateau_sorted = sorted(plateau, key=lambda g: -g["median_pct"])

    # ────────── 5. Best regime + best params combined ──────────
    # Re-run on bear-regime cohort with best params
    bear_df = df[df["regime"] == "bear"]
    bear_results = {}
    if len(bear_df) > 0:
        for cfg in plateau_sorted[:3]:
            rets = []
            for _, r in bear_df.iterrows():
                sim = simulate_short(symbol_daily[r["symbol"]], r["entry_pos"], cfg["sl"], cfg["hold"])
                if sim:
                    rets.append(sim["ret_net"])
            if rets:
                arr = np.array(rets)
                bear_results[f"sl_{cfg['sl']}_hold_{cfg['hold']}"] = {
                    "n": len(arr),
                    "median_pct": round(float(np.median(arr)) * 100, 2),
                    "mean_pct": round(float(arr.mean()) * 100, 2),
                    "win_rate": round(float((arr > 0).mean()), 3),
                }

    out = {
        "n_cohort": len(df),
        "regime_thresholds": {"bear_below": REGIME_BEAR_THRESHOLD, "bull_above": REGIME_BULL_THRESHOLD},
        "default_params": {"sl": DEFAULT_SL, "hold_days": DEFAULT_HOLD},
        "regime_analysis_default": regime_bucket,
        "correlation_strategy_pnl_vs_btc_hold_ret": round(corr, 3),
        "quarterly_regime_breakdown": quarterly_regime,
        "grid_search_full": grid,
        "plateau_cells_top_10": plateau_sorted[:10],
        "n_plateau_cells": len(plateau),
        "bear_regime_with_best_params": bear_results,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)

    # Print key results
    log.info("\n=== REGIME ANALYSIS (SL=50%, hold=30) ===")
    for r, v in regime_bucket.items():
        log.info("  %s (n=%d): median=%+.1f%% mean=%+.1f%% win=%.0f%% btc_30d_pre=%+.1f%%",
                 r, v["n"], v["median_pct"], v["mean_pct"], v["win_rate_positive"] * 100, v["btc_30d_pre_mean"])
    log.info("\nstrategy PnL vs BTC contemporaneous return corr: %+.3f", corr)
    log.info("\n=== QUARTERLY × REGIME ===")
    for q, v in quarterly_regime.items():
        log.info("  %s (n=%d, btc_pre=%+.1f%%, btc_post=%+.1f%%): median=%+.1f%% win=%.0f%% %s",
                 q, v["n"], v["btc_30d_pre_mean_pct"], v["btc_30d_post_mean_pct"],
                 v["median_ret_pct"], v["win_rate"] * 100, v["regime_counts"])
    log.info("\n=== GRID PLATEAU (median>15%%, win>55%%): %d cells ===", len(plateau))
    for cfg in plateau_sorted[:8]:
        log.info("  sl=%.2f hold=%d  → median=%+.1f%% mean=%+.1f%% win=%.0f%%",
                 cfg["sl"], cfg["hold"], cfg["median_pct"], cfg["mean_pct"], cfg["win_rate"] * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
