"""Direction 1 PoC — Listing lifecycle phase study.

Three sub-hypotheses tested as event studies on cohort of recently-listed
Binance Futures USDT perpetuals (age 30-365 days):

  (b) LISTING PUMP DECAY — for symbols whose Day 1 (first 24h) high return
      from open exceeds PUMP_THRESHOLD, what is the Day 7-30 forward
      return from Day 1 close?  Null: zero. Alternative: significantly
      negative (pump decays).

  (a) POST-DAY-60 ATR COMPRESSION BREAKOUT — for each symbol, scan days
      60+. Trigger: ATR_14d below ATR_60d percentile-25, AND volume_today
      > 3x median_30d. Forward return: 5-day direction = sign(today close
      - today open). If hypothesis holds, trigger-forward returns are
      direction-consistent (Sharpe > 1).

  (c) Reserved for OI data — needs additional joblib backfill.

Cohort selection: from listing_dates.json, take symbols with age 30-365
days (current data window) where we have at least 60 days of 1m ohlcv.

Backfill scope: this script ONLY analyzes symbols already in DB. To
expand cohort, run scripts.backfill_ohlcv_archive --symbols ... --days N
for the desired listings first.

Output: backend/runs/research_track/lifecycle_phase/poc__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_phase_poc")

LISTINGS_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
OUT_PATH = ROOT / "runs" / "research_track" / "lifecycle_phase" / "poc__metrics.json"

# Hypothesis-b parameters
DAY1_HOURS = 24
PUMP_THRESHOLD_PCT = 0.30  # ≥30% Day-1 high-from-open = pumped listing
DAY7_CLOSE_HOURS = 7 * 24
DAY30_CLOSE_HOURS = 30 * 24

# Hypothesis-a parameters
ATR_FAST = 14   # days
ATR_SLOW = 60
VOL_LOOKBACK = 30
VOL_SPIKE = 3.0
ATR_COMPRESS_PCTILE = 25  # ATR_FAST <= ATR_SLOW p25 = compressed
FORWARD_DAYS = 5
MIN_AGE_FOR_TRIGGER = 60


def load_listings() -> dict:
    return json.loads(LISTINGS_PATH.read_text())


def load_ohlcv_1d(db, sym: str) -> pd.DataFrame:
    """Load all 1m and resample to 1d (we only have 1m, no native 1d for these)."""
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
    # Resample 1m → 1d (UTC day boundaries)
    daily = pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()
    return daily


def hyp_b_pump_decay(db, listings: dict) -> dict:
    """Day 1 pump → Day 7-30 forward return cohort study."""
    rows = []
    today = date.today()
    syms_in_db = [r[0] for r in db.execute(text("SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()]
    candidates = []
    for sym in syms_in_db:
        if sym not in listings:
            continue
        ld = pd.to_datetime(listings[sym]["onboard_date"]).date()
        age = (today - ld).days
        if age < 30:
            continue
        candidates.append((sym, ld, age))

    log.info("hyp_b: %d candidate symbols in DB with age>=30d", len(candidates))

    for sym, listing_date, age in candidates:
        daily = load_ohlcv_1d(db, sym)
        if daily.empty:
            continue
        ld_ts = pd.Timestamp(listing_date)
        # Need ohlcv from at least listing_date to listing_date + 30d
        first_data = daily.index.min().date()
        if first_data > listing_date + timedelta(days=2):
            # We don't have data near listing day — can't compute Day 1 metrics
            continue
        if daily.index.max() < ld_ts + pd.Timedelta(days=30):
            continue

        # Day 1 = listing_date day in UTC
        try:
            day1 = daily.loc[ld_ts:ld_ts + pd.Timedelta(days=0, hours=23, minutes=59)]
            if day1.empty:
                day1 = daily.iloc[[0]]  # fallback: first row
        except Exception:
            continue
        if day1.empty:
            continue
        day1_row = day1.iloc[0]
        day1_open = day1_row["open"]
        day1_high = day1_row["high"]
        day1_close = day1_row["close"]
        if day1_open == 0:
            continue
        day1_high_ret = day1_high / day1_open - 1
        day1_close_ret = day1_close / day1_open - 1

        # Day 7 / Day 30 close from Day 1 close
        try:
            d7_close = daily.iloc[min(7, len(daily) - 1)]["close"]
            d30_close = daily.iloc[min(30, len(daily) - 1)]["close"]
        except Exception:
            continue
        fwd_7d_ret = d7_close / day1_close - 1
        fwd_30d_ret = d30_close / day1_close - 1

        rows.append({
            "symbol": sym,
            "listing_date": str(listing_date),
            "age_days": age,
            "day1_high_ret": day1_high_ret,
            "day1_close_ret": day1_close_ret,
            "fwd_7d_ret": fwd_7d_ret,
            "fwd_30d_ret": fwd_30d_ret,
            "pumped": day1_high_ret >= PUMP_THRESHOLD_PCT,
        })

    if not rows:
        return {"n": 0, "skip_reason": "no_candidates_with_data"}

    df = pd.DataFrame(rows)
    pumped = df[df["pumped"]]
    not_pumped = df[~df["pumped"]]

    def _stats(s):
        if len(s) == 0:
            return {"n": 0}
        return {
            "n": len(s),
            "mean": round(float(s.mean()) * 100, 2),
            "median": round(float(s.median()) * 100, 2),
            "std": round(float(s.std()) * 100, 2),
            "t_stat_vs_zero": round(float(s.mean() / (s.std() / np.sqrt(len(s)))), 2) if len(s) > 1 and s.std() > 0 else None,
            "win_rate_negative": round(float((s < 0).mean()), 3),
        }

    return {
        "n_total": len(df),
        "n_pumped": int(df["pumped"].sum()),
        "n_not_pumped": int((~df["pumped"]).sum()),
        "pumped_day1_high_ret_pct": _stats(pumped["day1_high_ret"]),
        "pumped_fwd_7d_ret_pct": _stats(pumped["fwd_7d_ret"]),
        "pumped_fwd_30d_ret_pct": _stats(pumped["fwd_30d_ret"]),
        "not_pumped_fwd_7d_ret_pct": _stats(not_pumped["fwd_7d_ret"]),
        "not_pumped_fwd_30d_ret_pct": _stats(not_pumped["fwd_30d_ret"]),
        "rows": df.sort_values("day1_high_ret", ascending=False).head(20).to_dict(orient="records"),
    }


def hyp_a_atr_compression(db, listings: dict) -> dict:
    """Post-day-60 ATR compression + volume spike → 5d forward direction."""
    syms_in_db = [r[0] for r in db.execute(text("SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()]
    candidates = []
    today = date.today()
    for sym in syms_in_db:
        if sym not in listings:
            continue
        ld = pd.to_datetime(listings[sym]["onboard_date"]).date()
        age = (today - ld).days
        if age < MIN_AGE_FOR_TRIGGER + 10:  # need some data after age=60
            continue
        candidates.append((sym, ld, age))

    log.info("hyp_a: %d candidate symbols", len(candidates))

    triggers = []
    for sym, listing_date, _ in candidates:
        daily = load_ohlcv_1d(db, sym)
        if daily.empty or len(daily) < 80:
            continue
        daily["tr"] = pd.concat([
            daily["high"] - daily["low"],
            (daily["high"] - daily["close"].shift(1)).abs(),
            (daily["low"] - daily["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        daily["atr_fast"] = daily["tr"].rolling(ATR_FAST).mean()
        daily["atr_slow"] = daily["tr"].rolling(ATR_SLOW).mean()
        daily["atr_slow_p25"] = daily["atr_slow"].rolling(ATR_SLOW).quantile(0.25)
        daily["vol_median"] = daily["volume"].rolling(VOL_LOOKBACK).median()
        daily["day_age"] = (daily.index - pd.Timestamp(listing_date)).days

        for i in range(MIN_AGE_FOR_TRIGGER, len(daily) - FORWARD_DAYS):
            row = daily.iloc[i]
            if pd.isna(row["atr_fast"]) or pd.isna(row["atr_slow_p25"]) or pd.isna(row["vol_median"]):
                continue
            if row["atr_fast"] >= row["atr_slow_p25"]:
                continue
            if row["volume"] < VOL_SPIKE * row["vol_median"]:
                continue
            if row["open"] == 0:
                continue
            direction = 1 if row["close"] > row["open"] else -1
            entry_close = row["close"]
            exit_close = daily.iloc[i + FORWARD_DAYS]["close"]
            if entry_close == 0:
                continue
            fwd_ret = exit_close / entry_close - 1
            signed_fwd = direction * fwd_ret
            triggers.append({
                "symbol": sym,
                "trigger_date": str(daily.index[i].date()),
                "day_age": int(row["day_age"]),
                "direction": direction,
                "fwd_ret": float(fwd_ret),
                "signed_fwd_ret": float(signed_fwd),
            })

    if not triggers:
        return {"n_triggers": 0, "skip_reason": "no_triggers_fired"}

    df = pd.DataFrame(triggers)
    s = df["signed_fwd_ret"]
    t_stat = float(s.mean() / (s.std() / np.sqrt(len(s)))) if len(s) > 1 and s.std() > 0 else 0
    fee = 0.0008
    pnl_after_fee = s - fee
    pnl_sharpe_per = pnl_after_fee.mean() / pnl_after_fee.std() if pnl_after_fee.std() > 0 else 0
    return {
        "n_triggers": len(df),
        "n_symbols_with_trigger": int(df["symbol"].nunique()),
        "signed_fwd_ret_mean_pct": round(float(s.mean()) * 100, 3),
        "signed_fwd_ret_median_pct": round(float(s.median()) * 100, 3),
        "signed_fwd_ret_std_pct": round(float(s.std()) * 100, 3),
        "signed_fwd_ret_t_stat": round(t_stat, 2),
        "win_rate": round(float((s > 0).mean()), 3),
        "pnl_after_fee_sharpe_per_trigger": round(float(pnl_sharpe_per), 3),
        "top_5_triggers": df.sort_values("signed_fwd_ret", ascending=False).head(5).to_dict(orient="records"),
        "bottom_5_triggers": df.sort_values("signed_fwd_ret", ascending=True).head(5).to_dict(orient="records"),
    }


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    listings = load_listings()
    log.info("loaded %d listings", len(listings))

    db = SessionLocal()
    try:
        log.info("=== Hypothesis B: Listing pump decay ===")
        b = hyp_b_pump_decay(db, listings)
        log.info("HYP_B: %s", json.dumps({k: v for k, v in b.items() if k != "rows"}, indent=2))

        log.info("=== Hypothesis A: Post-day-60 ATR compression breakout ===")
        a = hyp_a_atr_compression(db, listings)
        log.info("HYP_A: %s", json.dumps({k: v for k, v in a.items() if k not in ("top_5_triggers", "bottom_5_triggers")}, indent=2))
    finally:
        db.close()

    out = {"hyp_b_pump_decay": b, "hyp_a_atr_compression": a}
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
