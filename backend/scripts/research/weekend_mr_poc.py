"""paradigm-architect generated R-1 PoC — weekend_mean_reversion.

Hypothesis: Crypto perpetuals show systematic mean reversion from Friday
close to Monday open. Friday close → Monday open return is negatively
correlated with the prior week's trend (= Friday close minus 5-day MA of
daily closes). Effect should strengthen when weekend volume is anomalously
low (less MM activity, retail-dominated flow).

Sub-hypotheses tested as event study across all symbols with sufficient
weekly history:

  (a) PURE MR — for each Friday-Monday transition event, compute:
        prior_trend = (friday_close - ma5_close) / ma5_close
        fri_to_mon_ret = (monday_open - friday_close) / friday_close
      H0: corr(prior_trend, fri_to_mon_ret) ≈ 0.
      H1: corr < 0 with t-stat |2|+ → mean reversion.

  (b) VOLUME-CONDITIONAL — stratify events by weekend volume:
        weekend_vol = sum(sat_volume + sun_volume) / 30d_median_daily_vol
      Low-vol cohort (ratio < 0.7) should show stronger MR than high-vol.

  (c) QUARTERLY FOLD — split events by year-quarter, check sign consistency.

  (d) DIRECTIONAL TRADE — simple strategy:
        enter at Friday close in OPPOSITE direction of prior_trend sign,
        exit at Monday open, no SL.
      Compute mean/median/sharpe/win rate per trade after 2x4bps fee.

Universe: all symbols in ohlcv table with time_frame='1m' and at least
12 weeks of data (need ≥10 weekly events for stable per-symbol stats; we
aggregate cross-sectionally).

Time anchor: UTC Friday 23:59 close, UTC Monday 00:00 open.
Output: backend/runs/research_track/weekend_mr/poc__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("weekend_mr_poc")

OUT_PATH = ROOT / "runs" / "research_track" / "weekend_mr" / "poc__metrics.json"
FEE_ROUND_TRIP = 0.0008
MIN_WEEKS_PER_SYMBOL = 12
MA_DAYS = 5
WEEKEND_VOL_LOW_THRESHOLD = 0.7  # < 70% of 30d median = low-vol weekend


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
    daily = pd.DataFrame({
        "open": df["open"].resample("1D").first(),
        "high": df["high"].resample("1D").max(),
        "low": df["low"].resample("1D").min(),
        "close": df["close"].resample("1D").last(),
        "volume": df["volume"].resample("1D").sum(),
    }).dropna()
    daily["dow"] = daily.index.dayofweek  # 0=Mon,...,4=Fri,5=Sat,6=Sun
    return daily


def extract_events(daily: pd.DataFrame, symbol: str) -> list[dict]:
    """For each Friday in the data, build event with prior_trend + fri_to_mon_ret + weekend_vol."""
    if len(daily) < MA_DAYS + 7:
        return []
    daily = daily.copy()
    daily["close_ma5"] = daily["close"].rolling(MA_DAYS).mean()
    daily["vol_med30"] = daily["volume"].rolling(30).median()
    events = []
    fridays = daily[daily["dow"] == 4]
    for fri_ts, fri_row in fridays.iterrows():
        if pd.isna(fri_row["close_ma5"]) or fri_row["close_ma5"] <= 0:
            continue
        # Next Monday: fri + 3 days
        mon_ts = fri_ts + pd.Timedelta(days=3)
        if mon_ts not in daily.index:
            continue
        mon_row = daily.loc[mon_ts]
        if mon_row["dow"] != 0:
            continue
        fri_close = float(fri_row["close"])
        mon_open = float(mon_row["open"])
        if fri_close <= 0 or mon_open <= 0:
            continue
        prior_trend = (fri_close - fri_row["close_ma5"]) / fri_row["close_ma5"]
        fri_to_mon_ret = (mon_open - fri_close) / fri_close

        # Weekend volume (Sat + Sun if present)
        sat_ts = fri_ts + pd.Timedelta(days=1)
        sun_ts = fri_ts + pd.Timedelta(days=2)
        weekend_vol = 0.0
        n_we_days = 0
        for ts in (sat_ts, sun_ts):
            if ts in daily.index:
                weekend_vol += float(daily.loc[ts, "volume"] or 0)
                n_we_days += 1
        weekend_vol_ratio = None
        if n_we_days > 0 and not pd.isna(fri_row["vol_med30"]) and fri_row["vol_med30"] > 0:
            # normalize by daily median × n_we_days
            weekend_vol_ratio = weekend_vol / (fri_row["vol_med30"] * n_we_days)

        events.append({
            "symbol": symbol,
            "friday_date": str(fri_ts.date()),
            "year_quarter": f"{fri_ts.year}Q{(fri_ts.month-1)//3+1}",
            "prior_trend": prior_trend,
            "fri_to_mon_ret": fri_to_mon_ret,
            "weekend_vol_ratio": weekend_vol_ratio,
        })
    return events


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        syms = sorted({r[0] for r in db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'"
        )).fetchall()})
        log.info("syms in DB: %d", len(syms))

        all_events = []
        n_syms_used = 0
        for sym in syms:
            daily = load_daily(db, sym)
            if daily.empty:
                continue
            n_weeks = (daily.index.max() - daily.index.min()).days // 7
            if n_weeks < MIN_WEEKS_PER_SYMBOL:
                continue
            events = extract_events(daily, sym)
            if events:
                n_syms_used += 1
                all_events.extend(events)
    finally:
        db.close()

    log.info("symbols passing filter: %d  |  total Fri→Mon events: %d", n_syms_used, len(all_events))
    if not all_events:
        OUT_PATH.write_text(json.dumps({"error": "no events"}, indent=2))
        return 1

    df = pd.DataFrame(all_events)
    df = df.dropna(subset=["prior_trend", "fri_to_mon_ret"])
    log.info("clean events: %d", len(df))

    # ─── (a) Pure mean reversion correlation ───
    corr = float(df[["prior_trend", "fri_to_mon_ret"]].corr().iloc[0, 1])
    n = len(df)
    # Fisher z-transform for t-stat: t = r * sqrt(n-2) / sqrt(1-r^2)
    t_stat = corr * np.sqrt(n - 2) / np.sqrt(max(1 - corr ** 2, 1e-12))

    # Permutation test: shuffle prior_trend, recompute correlation
    rng = np.random.default_rng(42)
    null_corrs = []
    for _ in range(500):
        shuffled = rng.permutation(df["prior_trend"].values)
        c = np.corrcoef(shuffled, df["fri_to_mon_ret"].values)[0, 1]
        null_corrs.append(c)
    null_arr = np.array(null_corrs)
    p_one_sided = float((null_arr <= corr).mean()) if corr < 0 else float((null_arr >= corr).mean())

    # ─── (b) Volume-conditional ───
    df_vol = df.dropna(subset=["weekend_vol_ratio"])
    low_vol = df_vol[df_vol["weekend_vol_ratio"] < WEEKEND_VOL_LOW_THRESHOLD]
    high_vol = df_vol[df_vol["weekend_vol_ratio"] >= WEEKEND_VOL_LOW_THRESHOLD]
    corr_low = float(low_vol[["prior_trend", "fri_to_mon_ret"]].corr().iloc[0, 1]) if len(low_vol) > 5 else None
    corr_high = float(high_vol[["prior_trend", "fri_to_mon_ret"]].corr().iloc[0, 1]) if len(high_vol) > 5 else None

    # ─── (c) Quarterly fold ───
    quarterly = {}
    for q in sorted(df["year_quarter"].unique()):
        q_df = df[df["year_quarter"] == q]
        if len(q_df) < 10:
            continue
        q_corr = float(q_df[["prior_trend", "fri_to_mon_ret"]].corr().iloc[0, 1])
        quarterly[q] = {
            "n": len(q_df),
            "corr": round(q_corr, 4),
            "median_fri_to_mon_ret_pct": round(float(q_df["fri_to_mon_ret"].median()) * 100, 3),
        }

    # ─── (d) Directional trade simulation ───
    # Enter at Friday close OPPOSITE prior_trend sign, exit Monday open.
    # ret_net = -sign(prior_trend) * fri_to_mon_ret - FEE
    df["trade_dir"] = -np.sign(df["prior_trend"])
    df["trade_ret_gross"] = df["trade_dir"] * df["fri_to_mon_ret"]
    df["trade_ret_net"] = df["trade_ret_gross"] - FEE_ROUND_TRIP

    trade_stats = {
        "n_trades": len(df),
        "mean_pct": round(float(df["trade_ret_net"].mean()) * 100, 3),
        "median_pct": round(float(df["trade_ret_net"].median()) * 100, 3),
        "std_pct": round(float(df["trade_ret_net"].std(ddof=1)) * 100, 3),
        "win_rate": round(float((df["trade_ret_net"] > 0).mean()), 3),
        "sharpe_per_trade": round(float(df["trade_ret_net"].mean() / df["trade_ret_net"].std()), 3) if df["trade_ret_net"].std() > 0 else 0,
        "sharpe_annualized": round(float(df["trade_ret_net"].mean() / df["trade_ret_net"].std() * np.sqrt(52)), 2) if df["trade_ret_net"].std() > 0 else 0,
    }

    out = {
        "config": {
            "ma_days": MA_DAYS,
            "min_weeks_per_symbol": MIN_WEEKS_PER_SYMBOL,
            "weekend_vol_low_threshold": WEEKEND_VOL_LOW_THRESHOLD,
            "fee_round_trip": FEE_ROUND_TRIP,
        },
        "cohort_summary": {
            "n_symbols_used": n_syms_used,
            "n_total_events": int(n),
        },
        "hyp_a_pure_mr_correlation": {
            "n": int(n),
            "corr": round(corr, 4),
            "t_stat": round(float(t_stat), 2),
            "perm_p_one_sided": round(p_one_sided, 4),
            "null_mean": round(float(null_arr.mean()), 4),
            "null_std": round(float(null_arr.std()), 4),
        },
        "hyp_b_volume_conditional": {
            "n_low_vol": len(low_vol),
            "corr_low_vol": round(corr_low, 4) if corr_low is not None else None,
            "n_high_vol": len(high_vol),
            "corr_high_vol": round(corr_high, 4) if corr_high is not None else None,
        },
        "hyp_c_quarterly_folds": quarterly,
        "hyp_d_directional_trade_stats": trade_stats,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("saved → %s", OUT_PATH)
    log.info("\n%s", json.dumps({k: v for k, v in out.items() if k != "config"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
