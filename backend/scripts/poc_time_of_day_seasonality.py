#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Time-of-Day Seasonality paradigm.

Hypothesis: certain UTC hours-of-day exhibit persistent forward-return bias
across multi-year OHLCV data — a residual from regional flow imbalance
(Asian/EU/US sessions overlap effects, exchange margin call hours, funding
boundaries adjacent to liquidity gaps, retail-vs-institutional cycles).
If real, this bias generalizes to the OOS test window.

Distinct from prior 14 graveyard + 3 seeded paradigms:
  - All single-symbol moment / autocorr / funding-rate paradigms ignore time
  - funding_window_anomaly (graveyard) used ONLY 8h funding boundaries with a
    z-score reversal hypothesis — distinct from 24h-cycle hour bias
  - cross_symbol_correlation_regime (graveyard) used 5min returns dispersion
    with no time-of-day awareness
  - time_of_day_seasonality is the time-axis effect dimension, orthogonal

Pipeline:
  1. Load 1m → resample to 5m, log returns + UTC hour-of-day.
  2. Train period (train_frac=0.5): for each hour h in 0..23, compute mean
     forward N-bar log return (the IS bias estimate). bias[h] = mean_h.
  3. Test period: at each bar, look up current hour h, decide entry side
     based on bias[h]:
       bias[h] > +entry_thresh → LONG
       bias[h] < -entry_thresh → SHORT
       else → no entry
  4. Exit at HOLD bars or SL.

ANTI-PATTERN risk: in-sample bias can capture noise in train period and
fail OOS. R-3 perm test is mandatory regardless of R-2 multi-symbol
consistency.

Usage:
  python -m scripts.poc_time_of_day_seasonality --symbols SOLUSDT
  python -m scripts.poc_time_of_day_seasonality \
      --symbols HBARUSDT AXSUSDT COMPUSDT DOGEUSDT LDOUSDT SOLUSDT \
                AVAXUSDT LINKUSDT UNIUSDT ETCUSDT
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_time_of_day_seasonality")

PARADIGM = "time_of_day_seasonality"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlcv_5m(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp AS ts, close
                FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                ORDER BY timestamp
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["ts"],
        )
    finally:
        s.close()
    if df.empty:
        raise ValueError(f"No 1m ohlcv for {symbol}")
    df = df.set_index("ts")["close"].astype(float)
    df_5m = df.resample("5min", label="right", closed="right").last().dropna().to_frame("close")
    log.info("Loaded %s 5m: %d bars (%s → %s)",
             symbol, len(df_5m), df_5m.index[0], df_5m.index[-1])
    return df_5m


def simulate_tod_seasonality(df: pd.DataFrame, *, fwd_bars: int, hold_bars: int,
                              entry_thresh_bps: float, sl_pct: float,
                              fee_rate: float, capital: float, train_frac: float,
                              tod_unit: str = "hour",
                              ) -> dict:
    """Simulate time-of-day seasonality strategy.

    bias[unit] = mean forward fwd_bars log return in train period.
    Test entry: bias[current_unit] vs entry_thresh_bps.

    tod_unit: 'hour' (24 bins) or 'hour_dow' (24 × 7 = 168 bins).
    """
    df = df.copy()
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["fwd_ret"] = df["log_ret"].shift(-1).rolling(fwd_bars).sum().shift(-(fwd_bars - 1))
    df["hour"] = df.index.hour
    df["dow"] = df.index.dayofweek
    if tod_unit == "hour":
        df["unit"] = df["hour"].astype(int)
    elif tod_unit == "hour_dow":
        df["unit"] = df["hour"].astype(int) * 7 + df["dow"].astype(int)
    else:
        raise ValueError(f"invalid tod_unit: {tod_unit}")
    df = df.dropna(subset=["log_ret"])

    n = len(df)
    if n < 5000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    train = df.iloc[:split].dropna(subset=["fwd_ret"])
    test = df.iloc[split:]

    # Compute bias map from train period (mean forward log return per unit)
    bias_map = train.groupby("unit")["fwd_ret"].mean().to_dict()
    bias_std_map = train.groupby("unit")["fwd_ret"].std().to_dict()
    n_units = len(bias_map)

    # Convert entry threshold from bps to log-return scale
    entry_thresh = entry_thresh_bps / 10000.0  # 1 bps = 0.0001

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_unit = -1; target_hold = 0

    n_long_attempts = 0; n_short_attempts = 0

    for i in range(1, len(test)):
        ts = test.index[i]
        cpx = float(test["close"].iloc[i])

        if in_pos:
            bars_held += 1
            price_pnl = side * (cpx - entry_px) / entry_px
            unrealized = price_pnl
            exit_reason = None
            if unrealized < -sl_pct:
                exit_reason = "sl"
            elif bars_held >= target_hold:
                exit_reason = "time"
            if exit_reason:
                ret_pct = unrealized - 2 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(ts),
                    "side": side, "entry_unit": entry_unit,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            unit_now = int(test["unit"].iloc[i])
            b = bias_map.get(unit_now, 0.0)
            if math.isnan(b):
                equity_curve.append((ts, equity)); continue
            if b > entry_thresh:
                side = 1; n_long_attempts += 1
            elif b < -entry_thresh:
                side = -1; n_short_attempts += 1
            else:
                equity_curve.append((ts, equity)); continue
            in_pos = True
            entry_px = cpx; entry_ts = str(ts); entry_unit = unit_now
            bars_held = 0; target_hold = hold_bars

        equity_curve.append((ts, equity))

    bh_pct = (test["close"].iloc[-1] / test["close"].iloc[0]) - 1
    total_return_pct = (equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    if trades:
        rs = np.array([t["return_pct"] for t in trades])
        mu = rs.mean(); sd = rs.std(ddof=1) if len(rs) > 1 else 0.0
        oos_seconds = (test.index[-1] - test.index[0]).total_seconds()
        trades_per_year = (len(trades) / oos_seconds * 31536000.0
                           if oos_seconds > 0 else 0)
        sharpe_ann = (float(mu / sd * math.sqrt(max(trades_per_year, 1)))
                      if sd > 0 else 0.0)
        wins = rs[rs > 0]; losses = rs[rs < 0]
        win_rate_pct = float(len(wins) / len(rs) * 100)
        gw = float(wins.sum()) if len(wins) else 0.0
        gl = float(-losses.sum()) if len(losses) else 0.0
        profit_factor = (float(gw / gl) if gl > 0
                         else (float("inf") if gw > 0 else 0.0))
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0

    oos_days = int((test.index[-1] - test.index[0]).total_seconds() // 86400)

    # Bias map summary stats
    biases = np.array([v for v in bias_map.values() if not math.isnan(v)])
    bias_max_bps = float(np.max(np.abs(biases)) * 10000) if len(biases) else 0.0
    bias_mean_abs_bps = float(np.mean(np.abs(biases)) * 10000) if len(biases) else 0.0

    return {
        "n_trades": len(trades),
        "n_long_attempts": n_long_attempts,
        "n_short_attempts": n_short_attempts,
        "n_units": n_units,
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
        "bias_max_abs_bps": round(bias_max_bps, 3),
        "bias_mean_abs_bps": round(bias_mean_abs_bps, 3),
        "tod_unit": tod_unit,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--fwd-bars", type=int, default=12)  # 1h forward
    p.add_argument("--hold-bars", type=int, default=12)  # 1h hold
    p.add_argument("--entry-thresh-bps", type=float, default=2.0)  # 2 bps
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tod-unit", choices=["hour", "hour_dow"], default="hour")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_{args.tod_unit}_fwd{args.fwd_bars}_h{args.hold_bars}"
        f"_t{args.entry_thresh_bps}bps"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_tod_seasonality(
                df, fwd_bars=args.fwd_bars, hold_bars=args.hold_bars,
                entry_thresh_bps=args.entry_thresh_bps, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, tod_unit=args.tod_unit,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d S=%d) bias_max=%.2fbps",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_long_attempts", 0), sim.get("n_short_attempts", 0),
                     sim.get("bias_max_abs_bps", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_long_attempts", "n_short_attempts", "n_units",
            "alpha_pct", "total_return_pct", "buy_hold_pct", "sharpe_ann",
            "max_dd_pct", "win_rate_pct", "profit_factor",
            "bias_max_abs_bps", "bias_mean_abs_bps", "oos_days", "tod_unit"]
    df_out = df_out.reindex(columns=[c for c in cols if c in df_out.columns])
    out_csv = OUT_DIR / f"{tag}__per_symbol.csv"
    df_out.to_csv(out_csv, index=False)

    if len(rows) > 0:
        agg = {
            "spec_name": tag, "n_symbols": len(rows),
            "alpha_pct_mean": round(float(df_out["alpha_pct"].mean()), 2),
            "alpha_pos_count": int((df_out["alpha_pct"] > 0).sum()),
            "sharpe_mean": round(float(df_out["sharpe_ann"].mean()), 3),
            "sharpe_pos_count": int((df_out["sharpe_ann"] > 0).sum()),
            "trades_total": int(df_out["n_trades"].sum()),
        }
        out_meta = {
            "paradigm": PARADIGM, "phase": "R-1_PoC", "spec_name": tag,
            "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            "config": vars(args), "aggregate": agg, "per_symbol": rows,
        }
        out_meta_path = OUT_DIR / f"{tag}__metrics.json"
        out_meta_path.write_text(json.dumps(out_meta, indent=2, default=str))
        print("\n=== Aggregate ===")
        print(json.dumps(agg, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
