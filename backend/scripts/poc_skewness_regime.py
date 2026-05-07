#!/usr/bin/env python3
"""Phase R-1 PoC: Skewness Regime paradigm.

Hypothesis: when the rolling 3rd-moment (skewness) of recent 5m returns reaches
extreme percentile (bottom 10% = strongly negative skew = recent large down
move dominating distribution), that move is likely exhausted — capitulation
flush — and a mean-reverting bounce LONG entry is profitable. Symmetric for
extreme positive skew (euphoria flush) → SHORT.

Distinct from all 9 graveyard paradigms:
  - mean_reversion (z-score on returns) uses 1st-2nd moments
  - vol_regime_breakout uses 2nd moment (variance) percentile
  - volume_absorption uses single-bar pattern (volume + body)
  - funding_window/flip/carry use funding rate
  → skewness is the **3rd moment** = distributional asymmetry, an
    untested signal dimension in this track.

Pipeline:
  1. Load 1m → resample to 5m bars.
  2. Compute rolling SKEW_WINDOW skewness of 5m log returns.
  3. Compute REGIME_WINDOW percentile rank of skewness.
  4. Entry:
     - skew_pctl < SKEW_LOW_PCTL (extreme negative skew, capitulation):
       → LONG (default) | SHORT (--reverse-sign)
     - skew_pctl > SKEW_HIGH_PCTL (extreme positive skew, euphoria):
       → SHORT (default) | LONG (--reverse-sign)
  5. Exit at HOLD bars, SL hit.
  6. PnL = price PnL − 2 × fee.

Usage:
  python -m scripts.poc_skewness_regime --symbols SOLUSDT
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
log = logging.getLogger("poc_skewness_regime")

PARADIGM = "skewness_regime"
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


def simulate_skewness_regime(df: pd.DataFrame, *, skew_window: int, regime_window: int,
                              skew_low_pctl: float, skew_high_pctl: float,
                              hold_bars: int, sl_pct: float, fee_rate: float,
                              capital: float, train_frac: float,
                              reverse_sign: bool = False) -> dict:
    df = df.copy()
    df["ret"] = np.log(df["close"] / df["close"].shift(1))
    df["skew"] = df["ret"].rolling(skew_window).skew()
    df["skew_pctl"] = df["skew"].rolling(regime_window).rank(pct=True)
    df = df.dropna(subset=["skew", "skew_pctl"])

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
            pctl = float(row["skew_pctl"])
            if not math.isnan(pctl):
                if pctl < skew_low_pctl:
                    in_pos = True
                    side = (-1 if reverse_sign else 1)  # default: LONG on neg skew
                elif pctl > skew_high_pctl:
                    in_pos = True
                    side = (1 if reverse_sign else -1)  # default: SHORT on pos skew
                if in_pos:
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
    long_trades = sum(1 for t in trades if t["side"] == 1)
    short_trades = sum(1 for t in trades if t["side"] == -1)

    return {
        "n_trades": len(trades),
        "n_long": long_trades,
        "n_short": short_trades,
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
    p.add_argument("--skew-window", type=int, default=60)        # 5h skew window
    p.add_argument("--regime-window", type=int, default=8640)    # 30d percentile
    p.add_argument("--skew-low-pctl", type=float, default=0.10)
    p.add_argument("--skew-high-pctl", type=float, default=0.90)
    p.add_argument("--hold-bars", type=int, default=24)          # 2h hold
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true",
                   help="Continuation hypothesis (panic → SHORT, euphoria → LONG)")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    direction = "cont" if args.reverse_sign else "rev"
    tag = args.tag or (
        f"poc_{direction}_sw{args.skew_window}_p{args.skew_low_pctl}-{args.skew_high_pctl}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_skewness_regime(
                df, skew_window=args.skew_window, regime_window=args.regime_window,
                skew_low_pctl=args.skew_low_pctl, skew_high_pctl=args.skew_high_pctl,
                hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, reverse_sign=args.reverse_sign,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d S=%d)",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_long", 0), sim.get("n_short", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_long", "n_short", "alpha_pct",
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
