#!/usr/bin/env python3
"""Phase R-1 PoC: Mean-reversion paradigm.

Hypothesis: every current paper-pool spec is trend-following in nature
(KR Flow accumulation, Smart Money positioning, Taker Flow, OI dynamics —
all amplify directional moves). A pure mean-reversion paradigm should be
strictly orthogonal: enter against extreme moves and harvest the snapback.

Pipeline (rule-based, no ML — paradigm itself IS the rule):
  1. Load 1m OHLCV, resample to 1h.
  2. Compute z_score_t = (close_t - rolling_mean) / rolling_std on lookback bars.
  3. Entry: z_score crosses below -ENTRY_Z (oversold) → long
            z_score crosses above +ENTRY_Z (overbought) → short
  4. Exit: z_score returns to 0 (mean), OR max_hold timeout, OR SL.
  5. Per-symbol simulation, then aggregate equal-weighted across 14.

Usage:
  python -m scripts.poc_mean_reversion
  python -m scripts.poc_mean_reversion --entry-z 2.0 --lookback 24 --max-hold 24
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
log = logging.getLogger("poc_mean_reversion")

PARADIGM = "mean_reversion"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

DEFAULT_SYMBOLS = [
    "SOLUSDT", "HBARUSDT", "AXSUSDT", "DOGEUSDT", "UNIUSDT",
    "PYTHUSDT", "TONUSDT", "ICPUSDT", "ETCUSDT", "JUPUSDT",
    "COMPUSDT", "WLDUSDT", "LDOUSDT", "1000LUNCUSDT",
]


def load_hourly(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT
                  date_trunc('hour', timestamp) AS ts,
                  (ARRAY_AGG(open ORDER BY timestamp ASC))[1] AS open,
                  MAX(high) AS high,
                  MIN(low) AS low,
                  (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
                  SUM(volume) AS volume,
                  COUNT(*) AS bar_count
                FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                GROUP BY date_trunc('hour', timestamp)
                ORDER BY ts
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["ts"],
        )
    finally:
        s.close()
    df = df[df["bar_count"] >= 50]  # filter bars with <83% of 60 minutes
    df = df.set_index("ts").astype({"open": float, "high": float, "low": float,
                                     "close": float, "volume": float})
    log.info("Loaded %s 1h: %d bars (%s → %s)",
             symbol, len(df), df.index[0], df.index[-1])
    return df


def simulate_mean_reversion(df: pd.DataFrame, *, lookback: int, entry_z: float,
                            max_hold: int, sl_pct: float, fee_rate: float,
                            train_frac: float, capital: float) -> dict:
    """Z-score based mean-reversion: enter contra-extreme, exit at mean."""
    df = df.copy()
    df["close"] = df["close"].astype(float)
    df["mean_lb"] = df["close"].rolling(lookback).mean()
    df["std_lb"] = df["close"].rolling(lookback).std()
    df["zscore"] = (df["close"] - df["mean_lb"]) / df["std_lb"]
    df = df.dropna(subset=["zscore"])

    n = len(df)
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    closes = test["close"].values
    highs = test["high"].values
    lows = test["low"].values
    zscores = test["zscore"].values
    means = test["mean_lb"].values
    timestamps = test.index

    equity = capital
    equity_curve = [(timestamps[0], equity)]
    trades: list[dict] = []
    in_pos = False
    side = 0
    entry_px = sl_px = entry_zscore = 0.0
    bars_held = 0
    entry_ts = ""

    prev_z = zscores[0]
    for i in range(1, len(test)):
        px = closes[i]; hi = highs[i]; lo = lows[i]
        z = zscores[i]; mean_px = means[i]
        ts = timestamps[i]

        if in_pos:
            bars_held += 1
            exit_reason = None
            exit_px = px

            if side == 1:  # long, exit when z >= 0 or SL
                if lo <= sl_px:
                    exit_reason = "sl"; exit_px = sl_px
                elif z >= 0:
                    exit_reason = "mean"; exit_px = px
                elif bars_held >= max_hold:
                    exit_reason = "time"; exit_px = px
            else:  # short, exit when z <= 0 or SL
                if hi >= sl_px:
                    exit_reason = "sl"; exit_px = sl_px
                elif z <= 0:
                    exit_reason = "mean"; exit_px = px
                elif bars_held >= max_hold:
                    exit_reason = "time"; exit_px = px

            if exit_reason:
                gross = (exit_px - entry_px) / entry_px * side
                ret_pct = gross - 2 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(ts),
                    "side": side, "entry_px": entry_px, "exit_px": exit_px,
                    "entry_z": entry_zscore, "exit_z": float(z),
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        elif not in_pos and not math.isnan(z):
            # cross-down below -entry_z → long; cross-up above +entry_z → short
            if prev_z >= -entry_z and z < -entry_z:
                in_pos = True; side = 1
                entry_px = px; entry_zscore = float(z); entry_ts = str(ts)
                sl_px = px * (1 - sl_pct); bars_held = 0
            elif prev_z <= entry_z and z > entry_z:
                in_pos = True; side = -1
                entry_px = px; entry_zscore = float(z); entry_ts = str(ts)
                sl_px = px * (1 + sl_pct); bars_held = 0

        prev_z = z
        equity_curve.append((ts, equity))

    bh_pct = (closes[-1] / closes[0]) - 1
    total_return_pct = (equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    if trades:
        rs = np.array([t["return_pct"] for t in trades])
        mu = rs.mean(); sd = rs.std(ddof=1) if len(rs) > 1 else 0.0
        oos_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
        trades_per_year = len(trades) / oos_hours * 8760.0 if oos_hours > 0 else 0
        sharpe_ann = (float(mu / sd * math.sqrt(max(trades_per_year, 1)))
                      if sd > 0 else 0.0)
        wins = rs[rs > 0]; losses = rs[rs < 0]
        win_rate_pct = float(len(wins) / len(rs) * 100)
        gw = float(wins.sum()) if len(wins) else 0.0
        gl = float(-losses.sum()) if len(losses) else 0.0
        profit_factor = (float(gw / gl) if gl > 0 else
                         (float("inf") if gw > 0 else 0.0))
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0

    oos_days = int((timestamps[-1] - timestamps[0]).total_seconds() // 86400)
    exit_reasons: dict[str, int] = {}
    for t in trades:
        exit_reasons[t["exit_reason"]] = exit_reasons.get(t["exit_reason"], 0) + 1

    return {
        "n_trades": len(trades),
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "oos_days": oos_days,
        "exit_reasons": exit_reasons,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--lookback", type=int, default=24,
                   help="Z-score rolling window in 1h bars. Default 24 (1 day).")
    p.add_argument("--entry-z", type=float, default=2.0,
                   help="Z-score entry threshold. Default 2.0σ.")
    p.add_argument("--max-hold", type=int, default=24,
                   help="Max hold in 1h bars. Default 24 (1 day).")
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default="all14_1h_z2.0_lb24")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_hourly(sym)
            sim = simulate_mean_reversion(
                df, lookback=args.lookback, entry_z=args.entry_z,
                max_hold=args.max_hold, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, train_frac=args.train_frac,
                capital=args.capital,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s trades=%d",
                     sym, sim["alpha_pct"], sim["sharpe_ann"], sim["max_dd_pct"],
                     sim["win_rate_pct"], sim["profit_factor"], sim["n_trades"])
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days"]
    df_out = df_out.reindex(columns=[c for c in cols if c in df_out.columns])
    out_csv = OUT_DIR / f"{args.tag}__per_symbol.csv"
    df_out.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    # Aggregate equal-weighted across symbols (simple average of metrics)
    if len(rows) > 0:
        agg = {
            "spec_name": args.tag,
            "n_symbols": len(rows),
            "alpha_pct_mean": round(float(df_out["alpha_pct"].mean()), 2),
            "alpha_pct_median": round(float(df_out["alpha_pct"].median()), 2),
            "alpha_pos_count": int((df_out["alpha_pct"] > 0).sum()),
            "sharpe_ann_mean": round(float(df_out["sharpe_ann"].mean()), 3),
            "sharpe_pos_count": int((df_out["sharpe_ann"] > 0).sum()),
            "mdd_mean": round(float(df_out["max_dd_pct"].mean()), 2),
            "wr_mean": round(float(df_out["win_rate_pct"].mean()), 2),
            "trades_total": int(df_out["n_trades"].sum()),
            "trades_per_symbol_mean": round(float(df_out["n_trades"].mean()), 1),
        }
        out_meta = {
            "paradigm": PARADIGM,
            "phase": "R-1_PoC",
            "spec_name": args.tag,
            "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            "config": {
                "lookback": args.lookback, "entry_z": args.entry_z,
                "max_hold": args.max_hold, "sl_pct": args.sl_pct,
                "fee_rate": args.fee_rate, "train_frac": args.train_frac,
                "capital": args.capital,
            },
            "aggregate": agg,
            "per_symbol": rows,
        }
        out_meta_path = OUT_DIR / f"{args.tag}__metrics.json"
        out_meta_path.write_text(json.dumps(out_meta, indent=2, default=str))

        print("\n=== Aggregate ===")
        print(json.dumps(agg, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
