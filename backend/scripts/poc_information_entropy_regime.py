#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Information Entropy Regime paradigm.

Hypothesis: Shannon entropy of binned 5m log returns over a rolling W-bar
window measures the *information content* / uncertainty of the recent return
distribution. Low entropy regime = compressed / quiet market (returns
clustered near a few values). High entropy regime = chaotic / dispersive
market (returns spread across many bins).

The percentile rank of entropy within a 30d backwards window normalizes for
symbol-specific vol levels. Entry hypothesis:
  - low_pct (< P_LOW) regime + recent dir → CONTINUATION (compressed market
    breakouts: small movements persist before vol expansion)
  - high_pct (> P_HIGH) regime + recent dir → REVERSAL (chaotic overshoots
    revert as participants exhaust)

Distinct from prior paradigms (16 graveyard + 3 seeded):
  - Moments family (mean/std/skew/kurt — all graveyard or vol_regime_breakout):
    single distribution-shape statistic
  - autocorr/partial_autocorr (lag-1 seeded, lag-2 graveyard): time-axis
    dependence
  - **entropy**: distribution UNCERTAINTY/INFORMATION dimension (multi-modal
    or non-normal shape registers differently from std). For Gaussian,
    differential entropy ∝ log(σ); but discrete (binned) entropy diverges
    from log(σ) for skewed/multi-modal returns — so this is genuinely a
    different orthogonal angle from vol_regime_breakout (graveyard).

Anti-pattern checks:
  - rare-event (Hurst): R-1 threshold sweep mandatory
  - in-sample §3-F: percentile rank computed in real-time, not train table
  - family-extension §3-G: not within moments family — entropy uses bin
    histogram, not power moments
  - multi-symbol consistency §3-E: R-3 perm test required regardless of R-2

Pipeline:
  1. Load 1m → resample 5m, log returns.
  2. Rolling W-bar bin returns into K equal-width bins → compute Shannon
     entropy H_t = -Σ p_i log(p_i) (using window's min/max as bin range).
  3. Percentile rank of H within prior PCT_WINDOW bars.
  4. Direction signal: recent DIR_LOOKBACK-bar pct change.
  5. Entry per regime_filter:
     low_pct (<P_LOW) regime: continuation (LONG if dir up, SHORT if down)
     high_pct (>P_HIGH) regime: reversal (SHORT if dir up, LONG if down)
  6. Exit at HOLD bars or SL.

Usage:
  python -m scripts.poc_information_entropy_regime --symbols SOLUSDT
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
log = logging.getLogger("poc_information_entropy_regime")

PARADIGM = "information_entropy_regime"
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


def compute_rolling_entropy(returns: pd.Series, window: int, n_bins: int) -> pd.Series:
    """Shannon entropy of binned returns over rolling window.

    Uses each window's min/max as bin range (so window-specific scaling).
    Returns NaN until window is full.
    """
    arr = returns.values
    n = len(arr)
    out = np.full(n, np.nan)

    for i in range(window - 1, n):
        w = arr[i - window + 1: i + 1]
        # Discard NaN
        w = w[~np.isnan(w)]
        if len(w) < window // 2:
            continue
        wmin, wmax = w.min(), w.max()
        if wmax <= wmin:
            out[i] = 0.0
            continue
        # K equal-width bins
        edges = np.linspace(wmin, wmax, n_bins + 1)
        counts, _ = np.histogram(w, bins=edges)
        p = counts / counts.sum()
        p = p[p > 0]  # avoid log(0)
        H = -np.sum(p * np.log(p))
        out[i] = H

    return pd.Series(out, index=returns.index)


def simulate_entropy_regime(df: pd.DataFrame, *, entropy_window: int, n_bins: int,
                             pct_window: int, p_low: float, p_high: float,
                             dir_lookback: int, hold_bars: int, sl_pct: float,
                             fee_rate: float, capital: float, train_frac: float,
                             regime_filter: str = "both") -> dict:
    """regime_filter: 'low_only' (compression cont) / 'high_only' (chaos rev) / 'both'"""
    df = df.copy()
    df["ret"] = np.log(df["close"] / df["close"].shift(1))
    df["entropy"] = compute_rolling_entropy(df["ret"], entropy_window, n_bins)
    df["entropy_pct"] = df["entropy"].rolling(pct_window, min_periods=pct_window // 2).rank(pct=True)
    df["dir_ret"] = df["close"].pct_change(dir_lookback).shift(1)
    df = df.dropna(subset=["entropy_pct", "dir_ret"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_pct = 0.0; target_hold = 0; entry_regime_kind = ""

    n_low = 0; n_high = 0

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
                    "side": side, "entry_pct": entry_pct,
                    "regime_kind": entry_regime_kind,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            pct = float(row["entropy_pct"]); dr = float(row["dir_ret"])
            if math.isnan(pct) or math.isnan(dr) or dr == 0:
                equity_curve.append((ts, equity)); continue

            chosen = ""
            if pct < p_low and regime_filter in ("low_only", "both"):
                # compression continuation
                side = 1 if dr > 0 else -1
                chosen = "low"
                n_low += 1
            elif pct > p_high and regime_filter in ("high_only", "both"):
                # chaos reversal
                side = -1 if dr > 0 else 1
                chosen = "high"
                n_high += 1
            else:
                equity_curve.append((ts, equity)); continue

            in_pos = True
            entry_px = cpx; entry_ts = str(ts); entry_pct = pct
            bars_held = 0; target_hold = hold_bars
            entry_regime_kind = chosen
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

    return {
        "n_trades": len(trades),
        "n_low_entries": n_low,
        "n_high_entries": n_high,
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
        "entropy_q10": round(float(test["entropy"].quantile(0.10)), 3),
        "entropy_q50": round(float(test["entropy"].quantile(0.50)), 3),
        "entropy_q90": round(float(test["entropy"].quantile(0.90)), 3),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--entropy-window", type=int, default=288)  # 24h
    p.add_argument("--n-bins", type=int, default=10)
    p.add_argument("--pct-window", type=int, default=8640)  # 30d
    p.add_argument("--p-low", type=float, default=0.20)
    p.add_argument("--p-high", type=float, default=0.80)
    p.add_argument("--dir-lookback", type=int, default=12)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--regime-filter", choices=["both", "low_only", "high_only"],
                   default="both")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_w{args.entropy_window}_b{args.n_bins}_pl{args.p_low}_ph{args.p_high}"
        f"_dl{args.dir_lookback}_h{args.hold_bars}_{args.regime_filter}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_entropy_regime(
                df, entropy_window=args.entropy_window, n_bins=args.n_bins,
                pct_window=args.pct_window, p_low=args.p_low, p_high=args.p_high,
                dir_lookback=args.dir_lookback, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                regime_filter=args.regime_filter,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d H=%d) entropy q[10,50,90]=[%.2f,%.2f,%.2f]",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_low_entries", 0), sim.get("n_high_entries", 0),
                     sim.get("entropy_q10", 0), sim.get("entropy_q50", 0),
                     sim.get("entropy_q90", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_low_entries", "n_high_entries",
            "alpha_pct", "total_return_pct", "buy_hold_pct", "sharpe_ann",
            "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days",
            "entropy_q10", "entropy_q50", "entropy_q90"]
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
