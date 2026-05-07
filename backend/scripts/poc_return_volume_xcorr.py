#!/usr/bin/env python3
"""Phase R-1 PoC: Return × Volume Cross-Correlation paradigm.

Hypothesis: rolling cross-correlation between return[t] and volume[t-k]
identifies informed-flow regimes:
  - xcorr > +threshold: high past volume preceded high current return →
    informed buying detected → continuation LONG (if recent up)
  - xcorr < -threshold: high past volume preceded low current return →
    informed selling detected → continuation SHORT (if recent down)
  - |xcorr| near 0: random — no signal

Distinct from existing seeded paradigms (funding_carry, autocorr_regime):
  - autocorr_regime: lag-1 autocorrelation of returns (single time series)
  - this paradigm: cross-correlation of TWO series (return, volume)
  - Different information dimension: price-volume relationship (microstructure-flavored)
  - volume_absorption (graveyard) was single-bar pattern; this is multi-bar dependency

Pipeline:
  1. Load 1m → resample to 5m bars (close, sum-volume).
  2. Compute log return and log-volume change.
  3. Rolling W-bar cross-correlation: corr(ret[t-W+1:t+1], vol_chg[t-W+1-k:t+1-k]).
  4. Compute DIR_LOOKBACK-bar return for direction.
  5. Entry:
     - xcorr > +XCORR_THRESH AND dir > 0 → LONG (default) / SHORT (reverse)
     - xcorr > +XCORR_THRESH AND dir < 0 → SHORT (default) / LONG (reverse)
     - xcorr < -XCORR_THRESH AND dir > 0 → SHORT (default) / LONG (reverse)
     - xcorr < -XCORR_THRESH AND dir < 0 → LONG (default) / SHORT (reverse)
  6. Exit at HOLD bars or SL.

Usage:
  python -m scripts.poc_return_volume_xcorr --symbols SOLUSDT
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
log = logging.getLogger("poc_return_volume_xcorr")

PARADIGM = "return_volume_xcorr"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlcv_5m(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp AS ts, close, volume
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
    df = df.set_index("ts").astype({"close": float, "volume": float})
    df_5m = pd.DataFrame({
        "close": df["close"].resample("5min", label="right", closed="right").last(),
        "volume": df["volume"].resample("5min", label="right", closed="right").sum(),
    }).dropna()
    log.info("Loaded %s 5m: %d bars (%s → %s)",
             symbol, len(df_5m), df_5m.index[0], df_5m.index[-1])
    return df_5m


def simulate_xcorr_regime(df: pd.DataFrame, *, xcorr_window: int, lag: int,
                          xcorr_thresh: float, dir_lookback: int,
                          hold_bars: int, sl_pct: float, fee_rate: float,
                          capital: float, train_frac: float,
                          reverse_sign: bool = False) -> dict:
    df = df.copy()
    df["ret"] = np.log(df["close"] / df["close"].shift(1))
    # log-volume change to remove level effect
    df["vol_chg"] = np.log(df["volume"].replace(0, np.nan)).diff()
    # rolling xcorr: corr(ret[t-W+1:t+1], vol_chg[t-W+1-lag:t+1-lag])
    # = ret.rolling(W).corr(vol_chg.shift(lag))
    df["xcorr"] = df["ret"].rolling(xcorr_window).corr(df["vol_chg"].shift(lag))
    df["dir_ret"] = df["close"].pct_change(dir_lookback).shift(1)
    df = df.dropna(subset=["xcorr", "dir_ret"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_xc = 0.0; target_hold = 0; entry_regime = ""
    n_pos = 0; n_neg = 0

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
                    "side": side, "entry_xc": entry_xc, "regime": entry_regime,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            xc = float(row["xcorr"]); dr = float(row["dir_ret"])
            if not math.isnan(xc) and not math.isnan(dr) and dr != 0:
                if xc > xcorr_thresh:
                    # informed buying detected → trend continuation
                    side = 1 if dr > 0 else -1
                    if reverse_sign:
                        side = -side
                    entry_regime = "pos_xcorr"
                    n_pos += 1
                elif xc < -xcorr_thresh:
                    # informed selling detected → continuation in -direction
                    side = -1 if dr > 0 else 1
                    if reverse_sign:
                        side = -side
                    entry_regime = "neg_xcorr"
                    n_neg += 1
                if side != 0:
                    in_pos = True
                    entry_px = px; entry_ts = str(ts); entry_xc = xc
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
        pos_rs = np.array([t["return_pct"] for t in trades if t["regime"] == "pos_xcorr"])
        neg_rs = np.array([t["return_pct"] for t in trades if t["regime"] == "neg_xcorr"])
        pos_alpha = float(pos_rs.sum() * 100) if len(pos_rs) else 0.0
        neg_alpha = float(neg_rs.sum() * 100) if len(neg_rs) else 0.0
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0
        pos_alpha = neg_alpha = 0.0

    oos_days = int((test.index[-1] - test.index[0]).total_seconds() // 86400)

    return {
        "n_trades": len(trades),
        "n_pos_xcorr": n_pos,
        "n_neg_xcorr": n_neg,
        "alpha_pct": round(alpha_pct, 2),
        "pos_alpha_sum": round(pos_alpha, 2),
        "neg_alpha_sum": round(neg_alpha, 2),
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
    p.add_argument("--xcorr-window", type=int, default=288)   # 24h window
    p.add_argument("--lag", type=int, default=3)              # 15min lag (3 × 5m)
    p.add_argument("--xcorr-thresh", type=float, default=0.20)
    p.add_argument("--dir-lookback", type=int, default=12)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true",
                   help="Reversal hypothesis (xcorr extreme + recent up → SHORT)")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    direction = "rev" if args.reverse_sign else "cont"
    tag = args.tag or (
        f"poc_{direction}_xw{args.xcorr_window}_l{args.lag}_t{args.xcorr_thresh}"
        f"_dl{args.dir_lookback}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_xcorr_regime(
                df, xcorr_window=args.xcorr_window, lag=args.lag,
                xcorr_thresh=args.xcorr_thresh, dir_lookback=args.dir_lookback,
                hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, reverse_sign=args.reverse_sign,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (P=%d N=%d) pos_a=%.1f neg_a=%.1f",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_pos_xcorr", 0), sim.get("n_neg_xcorr", 0),
                     sim.get("pos_alpha_sum", 0), sim.get("neg_alpha_sum", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_pos_xcorr", "n_neg_xcorr",
            "alpha_pct", "pos_alpha_sum", "neg_alpha_sum",
            "total_return_pct", "buy_hold_pct", "sharpe_ann", "max_dd_pct",
            "win_rate_pct", "profit_factor", "oos_days"]
    df_out = df_out.reindex(columns=[c for c in cols if c in df_out.columns])
    out_csv = OUT_DIR / f"{tag}__per_symbol.csv"
    df_out.to_csv(out_csv, index=False)

    if len(rows) > 0:
        agg = {
            "spec_name": tag, "n_symbols": len(rows),
            "direction": direction,
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
