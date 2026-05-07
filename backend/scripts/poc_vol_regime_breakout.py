#!/usr/bin/env python3
"""Phase R-1 PoC: Vol Regime Breakout paradigm.

Hypothesis: when 24h realized volatility drops to the bottom percentile of its
30-day distribution (volatility compression regime), subsequent directional
breakouts tend to follow through with momentum. This is the "Bollinger squeeze"
effect — coiled energy releases directionally.

Distinct from graveyard paradigms:
  - mean_reversion: z-score REVERSAL (this is BREAKOUT continuation)
  - volume_absorption: single-bar pattern (this is regime + breakout)
  - ai_native_raw_1m: ML on flattened OHLCV (this is rule-based regime gate)
  - funding_window: funding boundary timing (this is OHLCV-only)

Pipeline:
  1. Load 1m → resample to 5m bars.
  2. Compute rolling 24h (288 bars) realized vol = std of 5m returns × √288.
  3. Compute 30d (8640 bars) percentile rank of current vol.
  4. When percentile < VOL_PCTL (compression):
     - if close > rolling N-bar high → LONG (breakout up)
     - if close < rolling N-bar low → SHORT (breakout down)
  5. Exit at HOLD bars, SL hit, or vol regime exits compression.
  6. PnL = price PnL − 2 × fee.

Usage:
  python -m scripts.poc_vol_regime_breakout --symbols SOLUSDT
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
log = logging.getLogger("poc_vol_regime_breakout")

PARADIGM = "vol_regime_breakout"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlcv_5m(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp AS ts, open, high, low, close
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
    df = df.set_index("ts").astype({"open": float, "high": float, "low": float, "close": float})
    df_5m = pd.DataFrame({
        "open": df["open"].resample("5min", label="right", closed="right").first(),
        "high": df["high"].resample("5min", label="right", closed="right").max(),
        "low": df["low"].resample("5min", label="right", closed="right").min(),
        "close": df["close"].resample("5min", label="right", closed="right").last(),
    }).dropna()
    log.info("Loaded %s 5m: %d bars (%s → %s)",
             symbol, len(df_5m), df_5m.index[0], df_5m.index[-1])
    return df_5m


def simulate_vol_regime_breakout(df: pd.DataFrame, *, vol_window: int, regime_window: int,
                                  vol_pctl: float, breakout_lookback: int,
                                  hold_bars: int, sl_pct: float, fee_rate: float,
                                  capital: float, train_frac: float,
                                  reverse_sign: bool = False) -> dict:
    df = df.copy()
    df["ret"] = df["close"].pct_change()
    df["vol"] = df["ret"].rolling(vol_window).std() * math.sqrt(vol_window)
    # percentile rank over regime_window (long horizon, e.g. 8640 bars = 30d)
    df["vol_pctl"] = df["vol"].rolling(regime_window).rank(pct=True)
    df["range_high"] = df["high"].rolling(breakout_lookback).max().shift(1)
    df["range_low"] = df["low"].rolling(breakout_lookback).min().shift(1)
    df = df.dropna(subset=["vol", "vol_pctl", "range_high", "range_low"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_pctl = 0.0; target_hold = 0

    for i in range(1, len(test)):
        ts = test.index[i]
        px = float(test["close"].iloc[i])
        hi = float(test["high"].iloc[i])
        lo = float(test["low"].iloc[i])
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
                    "side": side, "entry_pctl": entry_pctl,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            pctl = float(row["vol_pctl"])
            rhi = float(row["range_high"])
            rlo = float(row["range_low"])
            if not math.isnan(pctl) and pctl < vol_pctl:
                if hi > rhi:  # breakout up
                    in_pos = True; side = (-1 if reverse_sign else 1)
                    entry_px = px; entry_ts = str(ts); entry_pctl = pctl
                    bars_held = 0; target_hold = hold_bars
                elif lo < rlo:  # breakout down
                    in_pos = True; side = (1 if reverse_sign else -1)
                    entry_px = px; entry_ts = str(ts); entry_pctl = pctl
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
    exit_reasons: dict[str, int] = {}
    for tr in trades:
        exit_reasons[tr["exit_reason"]] = exit_reasons.get(tr["exit_reason"], 0) + 1

    return {
        "n_trades": len(trades),
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
    p.add_argument("--vol-window", type=int, default=288)       # 24h realized vol
    p.add_argument("--regime-window", type=int, default=8640)   # 30d percentile
    p.add_argument("--vol-pctl", type=float, default=0.20)      # bottom 20%
    p.add_argument("--breakout-lookback", type=int, default=24) # 2h range
    p.add_argument("--hold-bars", type=int, default=24)         # 2h hold
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true",
                   help="Fade breakout: compression+breakout → reversal entry")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_vw{args.vol_window}_rw{args.regime_window}_p{args.vol_pctl}"
        f"_bl{args.breakout_lookback}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_vol_regime_breakout(
                df, vol_window=args.vol_window, regime_window=args.regime_window,
                vol_pctl=args.vol_pctl, breakout_lookback=args.breakout_lookback,
                hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, reverse_sign=args.reverse_sign,
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
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days"]
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
            "mdd_mean": round(float(df_out["max_dd_pct"].mean()), 2),
            "wr_mean": round(float(df_out["win_rate_pct"].mean()), 2),
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
