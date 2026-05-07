#!/usr/bin/env python3
"""Phase R-1 PoC: Funding-window anomaly paradigm.

Hypothesis: Binance perpetual funding payments occur every 8h at 00:00 / 08:00 /
16:00 UTC. Around these boundaries, traders adjust positioning (hedging the
upcoming funding payment, retail closing crowded positions, MMs absorbing flow),
which creates a predictable intraday return pattern. Specifically, when the
pre-funding window shows an extreme directional move (z-score > threshold), the
post-funding window tends to revert — both because the move was driven by
funding-related flow exhaustion and because crowded positioning is unwinding.

Pipeline (per-symbol return-seasonality reversal at funding boundaries):
  1. Load 1m ohlcv → resample to 5m bars.
  2. Identify funding boundaries (UTC hour ∈ {0, 8, 16}, minute = 0).
  3. For each boundary t, compute pre-window return = (close[t] / close[t-Δpre]) - 1
     where Δpre is in 5m bars (default 12 = 1h).
  4. Compute rolling z-score of pre-window return over LOOKBACK funding cycles.
  5. Entry at t:
       z > +ENTRY_Z → SHORT (extreme up flow → expect reversal)
       z < -ENTRY_Z → LONG  (extreme down flow → expect reversal)
  6. Exit at t + Δhold bars (default 12 = 1h) or SL hit.
  7. PnL = price PnL - 2 × fee.

Distinct from funding_carry:
  - funding_carry: 8h funding rate level z-score, holds 1-5 days
  - funding_window: 5m return seasonality at funding TIME, holds 1h
  - Different signal source (return vs rate), different timeframe (intraday vs swing)
  - Both can coexist (orthogonal paradigms).

Usage:
  python -m scripts.poc_funding_window --symbols SOLUSDT
  python -m scripts.poc_funding_window --symbols HBARUSDT AXSUSDT COMPUSDT \
      --pre-bars 12 --hold-bars 12 --entry-z 1.5
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
log = logging.getLogger("poc_funding_window")

PARADIGM = "funding_window_anomaly"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

PAPER_POOL = [
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "LDOUSDT",
    "SOLUSDT", "WLDUSDT", "JUPUSDT", "AVAXUSDT", "LINKUSDT",
    "UNIUSDT", "ETCUSDT", "PYTHUSDT", "TONUSDT",
]


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
    # Resample to 5m bars (last close in window)
    df_5m = df.resample("5min", label="right", closed="right").last().dropna()
    log.info("Loaded %s 5m: %d bars (%s → %s)",
             symbol, len(df_5m), df_5m.index[0], df_5m.index[-1])
    return df_5m.to_frame("close")


def is_funding_boundary(ts: pd.Timestamp) -> bool:
    return (ts.hour in (0, 8, 16)) and (ts.minute == 0)


def simulate_funding_window(df: pd.DataFrame, *, pre_bars: int, hold_bars: int,
                            lookback: int, entry_z: float, sl_pct: float,
                            fee_rate: float, capital: float, train_frac: float
                            ) -> dict:
    df = df.copy()
    df["ret"] = df["close"].pct_change()

    # mark funding boundaries
    df["is_boundary"] = [is_funding_boundary(ts) for ts in df.index]

    # pre-window cumulative return at each boundary t: close[t] / close[t-pre_bars] - 1
    df["pre_ret"] = df["close"].pct_change(pre_bars)

    # collect boundary rows for z-score reference (per-symbol rolling stats)
    boundaries = df[df["is_boundary"]].copy()
    boundaries["pre_ret_mean"] = boundaries["pre_ret"].shift(1).rolling(lookback).mean()
    boundaries["pre_ret_std"] = boundaries["pre_ret"].shift(1).rolling(lookback).std()
    boundaries["z"] = (boundaries["pre_ret"] - boundaries["pre_ret_mean"]) / boundaries["pre_ret_std"]
    boundaries = boundaries.dropna(subset=["z"])

    # OOS split
    n_boundaries = len(boundaries)
    if n_boundaries < 50:
        return {"error": f"too few boundaries ({n_boundaries})", "n_trades": 0}
    split = int(n_boundaries * train_frac)
    test_boundaries = boundaries.iloc[split:]
    test_start_ts = test_boundaries.index[0]
    test_end_ts = test_boundaries.index[-1]

    test = df.loc[test_start_ts:test_end_ts].copy()
    if test.empty:
        return {"error": "empty test window", "n_trades": 0}

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False
    side = 0
    entry_px = 0.0
    bars_held = 0
    entry_ts = ""
    entry_z_value = 0.0
    target_hold = 0

    # iterate test bars
    for i in range(1, len(test)):
        ts = test.index[i]
        px = float(test["close"].iloc[i])

        if in_pos:
            bars_held += 1
            price_pnl = side * (px - entry_px) / entry_px
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
                    "side": side, "entry_z": entry_z_value,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        # boundary check
        if not in_pos and is_funding_boundary(ts) and ts in test_boundaries.index:
            row = test_boundaries.loc[ts]
            z = float(row["z"]) if not isinstance(row["z"], pd.Series) else float(row["z"].iloc[0])
            if not math.isnan(z):
                if z > entry_z:
                    in_pos = True; side = -1
                    entry_px = px; entry_ts = str(ts); entry_z_value = z
                    bars_held = 0; target_hold = hold_bars
                elif z < -entry_z:
                    in_pos = True; side = 1
                    entry_px = px; entry_ts = str(ts); entry_z_value = z
                    bars_held = 0; target_hold = hold_bars

        equity_curve.append((ts, equity))

    # buy-hold benchmark
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
    exit_reasons: dict[str, int] = {}
    for tr in trades:
        exit_reasons[tr["exit_reason"]] = exit_reasons.get(tr["exit_reason"], 0) + 1

    return {
        "n_trades": len(trades),
        "n_boundaries_test": int(len(test_boundaries)),
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
        "exit_reasons": exit_reasons,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--pre-bars", type=int, default=12)   # 12 × 5m = 1h
    p.add_argument("--hold-bars", type=int, default=12)  # 12 × 5m = 1h
    p.add_argument("--lookback", type=int, default=90)   # 90 funding cycles = 30 days
    p.add_argument("--entry-z", type=float, default=1.5)
    p.add_argument("--sl-pct", type=float, default=0.03)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_pre{args.pre_bars}_hold{args.hold_bars}_z{args.entry_z}_lb{args.lookback}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_funding_window(
                df, pre_bars=args.pre_bars, hold_bars=args.hold_bars,
                lookback=args.lookback, entry_z=args.entry_z,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                train_frac=args.train_frac, capital=args.capital,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s trades=%d",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"])
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_boundaries_test", "alpha_pct",
            "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor",
            "oos_days"]
    df_out = df_out.reindex(columns=[c for c in cols if c in df_out.columns])
    out_csv = OUT_DIR / f"{tag}__per_symbol.csv"
    df_out.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    if len(rows) > 0:
        agg = {
            "spec_name": tag, "n_symbols": len(rows),
            "alpha_pct_mean": round(float(df_out["alpha_pct"].mean()), 2),
            "alpha_pct_median": round(float(df_out["alpha_pct"].median()), 2),
            "alpha_pos_count": int((df_out["alpha_pct"] > 0).sum()),
            "sharpe_mean": round(float(df_out["sharpe_ann"].mean()), 3),
            "sharpe_pos_count": int((df_out["sharpe_ann"] > 0).sum()),
            "mdd_mean": round(float(df_out["max_dd_pct"].mean()), 2),
            "wr_mean": round(float(df_out["win_rate_pct"].mean()), 2),
            "trades_total": int(df_out["n_trades"].sum()),
            "trades_per_symbol_mean": round(float(df_out["n_trades"].mean()), 1),
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
