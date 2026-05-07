#!/usr/bin/env python3
"""Phase R-1 PoC: Hurst Exponent Regime paradigm.

Hypothesis: Hurst exponent of recent log-price series identifies the
**long-memory regime** of the market:
  - H > 0.5 + ε: persistent / trending regime → momentum entry
  - H < 0.5 - ε: anti-persistent / mean-reverting regime → reversion entry
  - H near 0.5: random walk → no signal (skip)

Distinct from `autocorr_regime` (the prior R-5 seed paradigm):
  - autocorr_regime uses lag-1 short-term dependency (rolling 24h window)
  - hurst_regime measures multi-scale long-memory persistence
  - Different time-scales of dependence → independent regime detection
  - Works on absolute price-level series (or returns), unlike autocorr
    which requires log-returns

Pipeline:
  1. Load 1m → resample to 5m bars.
  2. Compute rolling Hurst exponent on log-close over WINDOW bars.
  3. Compute DIR_LOOKBACK-bar return for direction.
  4. Entry:
     - H > 0.5 + thresh AND dir > 0 → LONG (trend continues up)
     - H > 0.5 + thresh AND dir < 0 → SHORT (trend continues down)
     - H < 0.5 - thresh AND dir > 0 → SHORT (recent up will revert)
     - H < 0.5 - thresh AND dir < 0 → LONG (recent down will revert)
  5. Exit at HOLD bars or SL.

Hurst computation: rescaled range (R/S) method with log-log fit over
multiple sub-window sizes.

Usage:
  python -m scripts.poc_hurst_regime --symbols SOLUSDT
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
log = logging.getLogger("poc_hurst_regime")

PARADIGM = "hurst_regime"
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


def _hurst_rs(arr: np.ndarray) -> float:
    """R/S method Hurst exponent. arr is log-price series (1D)."""
    n = len(arr)
    if n < 20:
        return np.nan
    # increments
    incs = np.diff(arr)
    if len(incs) < 10 or np.std(incs) == 0:
        return np.nan
    # window sizes: log-spaced, min 8, max n//2
    sizes = np.unique(np.geomspace(8, max(n // 4, 16), num=8).astype(int))
    sizes = sizes[(sizes >= 8) & (sizes <= len(incs))]
    if len(sizes) < 4:
        return np.nan
    rs_vals = []
    for s in sizes:
        n_chunks = len(incs) // s
        if n_chunks < 1:
            continue
        rs_chunk = []
        for k in range(n_chunks):
            chunk = incs[k * s:(k + 1) * s]
            mu = chunk.mean()
            dev = np.cumsum(chunk - mu)
            R = dev.max() - dev.min()
            S = chunk.std()
            if S > 0:
                rs_chunk.append(R / S)
        if rs_chunk:
            rs_vals.append(np.mean(rs_chunk))
        else:
            rs_vals.append(np.nan)
    rs_vals = np.array(rs_vals[:len(sizes)])
    valid = ~np.isnan(rs_vals)
    if valid.sum() < 4:
        return np.nan
    log_n = np.log(sizes[valid])
    log_rs = np.log(rs_vals[valid])
    slope, _ = np.polyfit(log_n, log_rs, 1)
    return float(slope)


def _rolling_hurst(s: pd.Series, window: int) -> pd.Series:
    """Compute rolling Hurst exponent. SLOW — use sparingly."""
    log_s = np.log(s.values)
    out = np.full(len(s), np.nan)
    for i in range(window, len(s) + 1):
        out[i - 1] = _hurst_rs(log_s[i - window:i])
    return pd.Series(out, index=s.index)


def simulate_hurst_regime(df: pd.DataFrame, *, hurst_window: int, hurst_thresh: float,
                          dir_lookback: int, hold_bars: int, sl_pct: float,
                          fee_rate: float, capital: float, train_frac: float,
                          regime_filter: str = "both") -> dict:
    df = df.copy()
    df["hurst"] = _rolling_hurst(df["close"], hurst_window)
    df["dir_ret"] = df["close"].pct_change(dir_lookback).shift(1)
    df = df.dropna(subset=["hurst", "dir_ret"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_h = 0.0; entry_regime = ""; target_hold = 0
    n_trend = 0; n_rev = 0

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
                    "side": side, "entry_h": entry_h, "regime": entry_regime,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            h = float(row["hurst"]); dr = float(row["dir_ret"])
            if not math.isnan(h) and not math.isnan(dr) and dr != 0:
                if h > 0.5 + hurst_thresh and regime_filter in ("both", "trend_only"):
                    side = 1 if dr > 0 else -1
                    entry_regime = "trend"
                    n_trend += 1
                elif h < 0.5 - hurst_thresh and regime_filter in ("both", "rev_only"):
                    side = -1 if dr > 0 else 1
                    entry_regime = "rev"
                    n_rev += 1
                if side != 0:
                    in_pos = True
                    entry_px = px; entry_ts = str(ts); entry_h = h
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
        trend_rs = np.array([t["return_pct"] for t in trades if t["regime"] == "trend"])
        rev_rs = np.array([t["return_pct"] for t in trades if t["regime"] == "rev"])
        trend_alpha = float(trend_rs.sum() * 100) if len(trend_rs) else 0.0
        rev_alpha = float(rev_rs.sum() * 100) if len(rev_rs) else 0.0
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0
        trend_alpha = rev_alpha = 0.0

    oos_days = int((test.index[-1] - test.index[0]).total_seconds() // 86400)

    return {
        "n_trades": len(trades),
        "n_trend_entries": n_trend,
        "n_rev_entries": n_rev,
        "alpha_pct": round(alpha_pct, 2),
        "trend_alpha_sum": round(trend_alpha, 2),
        "rev_alpha_sum": round(rev_alpha, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--hurst-window", type=int, default=288)   # 24h window
    p.add_argument("--hurst-thresh", type=float, default=0.10)
    p.add_argument("--dir-lookback", type=int, default=12)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--regime-filter", choices=["both", "trend_only", "rev_only"],
                   default="both")
    p.add_argument("--max-bars", type=int, default=0,
                   help="Truncate to last N bars for fast iteration (0 = use all)")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_{args.regime_filter}_hw{args.hurst_window}_t{args.hurst_thresh}"
        f"_dl{args.dir_lookback}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            if args.max_bars > 0 and len(df) > args.max_bars:
                df = df.iloc[-args.max_bars:]
                log.info("[%s] truncated to last %d bars", sym, len(df))
            sim = simulate_hurst_regime(
                df, hurst_window=args.hurst_window, hurst_thresh=args.hurst_thresh,
                dir_lookback=args.dir_lookback, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                regime_filter=args.regime_filter,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (T=%d R=%d) trend_a=%.1f rev_a=%.1f",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_trend_entries", 0), sim.get("n_rev_entries", 0),
                     sim.get("trend_alpha_sum", 0), sim.get("rev_alpha_sum", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_trend_entries", "n_rev_entries",
            "alpha_pct", "trend_alpha_sum", "rev_alpha_sum",
            "total_return_pct", "buy_hold_pct", "sharpe_ann", "max_dd_pct",
            "win_rate_pct", "profit_factor", "oos_days"]
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
