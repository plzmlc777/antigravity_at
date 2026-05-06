#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Cross-Symbol Correlation Regime paradigm.

Hypothesis: rolling pairwise correlation across the paper-pool universe defines
a market dispersion regime that conditions per-symbol return continuation:
  - High avg pairwise correlation (e.g., > 0.65): "all together" — market is
    risk-on/off in unison; idiosyncratic alpha low; recent moves more likely
    to mean-revert as macro pressure releases.
  - Low avg pairwise correlation (e.g., < 0.35): "idiosyncratic" — symbols
    move on own fundamentals; persistent momentum likely to continue.
  - Mid: neutral, no entry.

Distinct from all 13 graveyard + 2 seeded paradigms:
  - All single-symbol moment/autocorr/funding paradigms operate on one series
  - This is pool-wide cross-section dispersion — orthogonal dimension
  - Market microstructure question: "are all symbols co-moving?" — captured
    by average off-diagonal correlation across N×N matrix

Pipeline:
  1. Load 1m OHLCV for universe → resample 5m, log returns wide df.
  2. Rolling window W: pairwise corr matrix → average upper-triangle = regime.
  3. Direction signal: target symbol's recent DIR_LOOKBACK-bar pct change.
  4. Entry per target symbol:
       hi_corr regime AND regime_filter ∈ {both, hi_only}:
         direction='fade'   → SHORT if recent_up else LONG
         direction='follow' → LONG  if recent_up else SHORT
       lo_corr regime AND regime_filter ∈ {both, lo_only}:
         direction='fade'   → SHORT if recent_up else LONG
         direction='follow' → LONG  if recent_up else SHORT
  5. Exit at HOLD bars or SL.

Usage:
  # R-1 single symbol, default paper-pool universe
  python -m scripts.poc_cross_symbol_correlation_regime --symbols SOLUSDT
  # R-2 multi-symbol all paper-pool
  python -m scripts.poc_cross_symbol_correlation_regime \
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
log = logging.getLogger("poc_xs_corr_regime")

PARADIGM = "cross_symbol_correlation_regime"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

DEFAULT_UNIVERSE = [
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "LDOUSDT",
    "SOLUSDT", "AVAXUSDT", "LINKUSDT", "UNIUSDT", "ETCUSDT",
]


def load_universe_returns_5m(universe: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load 1m close for each symbol → resample to 5m → wide returns df.

    Returns (closes_wide, returns_wide) aligned on common index.
    """
    s = SessionLocal()
    try:
        frames = []
        for sym in universe:
            df = pd.read_sql(
                text("""
                    SELECT timestamp AS ts, close
                    FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                    ORDER BY timestamp
                """),
                s.connection(),
                params={"sym": sym},
                parse_dates=["ts"],
            )
            if df.empty:
                log.warning("No 1m ohlcv for %s — skipping", sym)
                continue
            ser = df.set_index("ts")["close"].astype(float)
            ser_5m = ser.resample("5min", label="right", closed="right").last().dropna()
            ser_5m.name = sym
            frames.append(ser_5m)
    finally:
        s.close()
    if not frames:
        raise ValueError("No symbols loaded")
    closes = pd.concat(frames, axis=1).sort_index()
    closes = closes.dropna(how="any")
    rets = np.log(closes / closes.shift(1)).dropna(how="any")
    log.info("Universe %d symbols, common 5m bars: %d (%s → %s)",
             len(closes.columns), len(rets), rets.index[0], rets.index[-1])
    return closes, rets


def rolling_avg_pairwise_corr(rets: pd.DataFrame, window: int) -> pd.Series:
    """Compute rolling average upper-triangular pairwise correlation across all
    columns of `rets`, vectorized.

    For each window of size W, the correlation matrix C is N×N (N=len(cols)).
    Off-diagonal upper triangle has K=N*(N-1)/2 entries. Their mean is the
    market dispersion regime indicator.

    Implementation note: pandas DataFrame.rolling().corr() returns a multi-
    index df of pairwise correlations per timestamp. We extract only the upper
    triangle pairs (i<j) and average.
    """
    cols = list(rets.columns)
    n = len(cols)
    pair_idx = [(i, j) for i in range(n) for j in range(i + 1, n)]

    # Vectorized using rolling on each pair via rets.rolling(window).corr(other)
    # but that's O(N^2) iterations. For N=10 that's 45 pairs — fine.
    # Compute each pair's rolling correlation series, then average.
    pair_series = []
    for i, j in pair_idx:
        a = rets.iloc[:, i]
        b = rets.iloc[:, j]
        # Rolling Pearson correlation
        pc = a.rolling(window).corr(b)
        pair_series.append(pc)
    df_pairs = pd.concat(pair_series, axis=1)
    avg = df_pairs.mean(axis=1)
    avg.name = "avg_pairwise_corr"
    return avg


def simulate_xs_corr_regime(
    closes: pd.DataFrame,
    rets: pd.DataFrame,
    avg_corr: pd.Series,
    target_symbol: str,
    *,
    hi_thresh: float,
    lo_thresh: float,
    dir_lookback: int,
    hold_bars: int,
    sl_pct: float,
    fee_rate: float,
    capital: float,
    train_frac: float,
    direction: str = "fade",  # 'fade' | 'follow'
    regime_filter: str = "both",  # 'both' | 'hi_only' | 'lo_only'
) -> dict:
    """Simulate per-target-symbol entries based on market regime."""
    px = closes[target_symbol]
    df = pd.DataFrame({"close": px, "regime": avg_corr}).dropna()
    df["dir_ret"] = df["close"].pct_change(dir_lookback).shift(1)
    df = df.dropna()

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_regime = 0.0; target_hold = 0; entry_regime_kind = ""

    n_hi = 0; n_lo = 0

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
                    "side": side, "entry_regime": entry_regime,
                    "regime_kind": entry_regime_kind,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            r = float(row["regime"]); dr = float(row["dir_ret"])
            if math.isnan(r) or math.isnan(dr) or dr == 0:
                equity_curve.append((ts, equity)); continue

            chosen_kind = ""
            if r >= hi_thresh and regime_filter in ("both", "hi_only"):
                chosen_kind = "hi"
                n_hi += 1
            elif r <= lo_thresh and regime_filter in ("both", "lo_only"):
                chosen_kind = "lo"
                n_lo += 1

            if chosen_kind:
                up = dr > 0
                if direction == "fade":
                    side = -1 if up else 1
                else:  # follow
                    side = 1 if up else -1
                in_pos = True
                entry_px = cpx; entry_ts = str(ts)
                entry_regime = r; entry_regime_kind = chosen_kind
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
        hi_rs = np.array([t["return_pct"] for t in trades if t["regime_kind"] == "hi"])
        lo_rs = np.array([t["return_pct"] for t in trades if t["regime_kind"] == "lo"])
        hi_alpha = float(hi_rs.sum() * 100) if len(hi_rs) else 0.0
        lo_alpha = float(lo_rs.sum() * 100) if len(lo_rs) else 0.0
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0
        hi_alpha = lo_alpha = 0.0

    oos_days = int((test.index[-1] - test.index[0]).total_seconds() // 86400)

    return {
        "symbol": target_symbol,
        "n_trades": len(trades),
        "n_hi_entries": n_hi,
        "n_lo_entries": n_lo,
        "alpha_pct": round(alpha_pct, 2),
        "hi_alpha_sum": round(hi_alpha, 2),
        "lo_alpha_sum": round(lo_alpha, 2),
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
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"],
                   help="Target symbols to backtest (entries on each).")
    p.add_argument("--universe", nargs="+", default=DEFAULT_UNIVERSE,
                   help="Universe for cross-correlation matrix.")
    p.add_argument("--corr-window", type=int, default=288)  # 24h
    p.add_argument("--hi-thresh", type=float, default=0.65)
    p.add_argument("--lo-thresh", type=float, default=0.35)
    p.add_argument("--dir-lookback", type=int, default=12)  # 1h
    p.add_argument("--hold-bars", type=int, default=24)     # 2h
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--direction", choices=["fade", "follow"], default="fade")
    p.add_argument("--regime-filter", choices=["both", "hi_only", "lo_only"],
                   default="both")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_w{args.corr_window}_hi{args.hi_thresh}_lo{args.lo_thresh}"
        f"_dl{args.dir_lookback}_h{args.hold_bars}_{args.direction}_{args.regime_filter}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    closes, rets = load_universe_returns_5m(args.universe)
    log.info("Computing rolling avg pairwise corr (window=%d, %d pairs)",
             args.corr_window, len(args.universe) * (len(args.universe) - 1) // 2)
    avg_corr = rolling_avg_pairwise_corr(rets, args.corr_window).dropna()
    # Distribution sanity
    log.info("avg_corr stats: mean=%.3f std=%.3f q[10,50,90]=[%.3f, %.3f, %.3f]",
             avg_corr.mean(), avg_corr.std(),
             avg_corr.quantile(0.10), avg_corr.quantile(0.50), avg_corr.quantile(0.90))

    rows = []
    for sym in args.symbols:
        if sym not in closes.columns:
            log.warning("%s not in universe — skipping", sym)
            continue
        try:
            sim = simulate_xs_corr_regime(
                closes, rets, avg_corr, sym,
                hi_thresh=args.hi_thresh, lo_thresh=args.lo_thresh,
                dir_lookback=args.dir_lookback, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                direction=args.direction, regime_filter=args.regime_filter,
            )
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (HI=%d LO=%d) hi_a=%.1f lo_a=%.1f",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_hi_entries", 0), sim.get("n_lo_entries", 0),
                     sim.get("hi_alpha_sum", 0), sim.get("lo_alpha_sum", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_hi_entries", "n_lo_entries",
            "alpha_pct", "hi_alpha_sum", "lo_alpha_sum",
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
            "hi_alpha_mean": round(float(df_out["hi_alpha_sum"].mean()), 2),
            "lo_alpha_mean": round(float(df_out["lo_alpha_sum"].mean()), 2),
            "trades_total": int(df_out["n_trades"].sum()),
            "avg_corr_global_mean": round(float(avg_corr.mean()), 3),
            "avg_corr_global_q10": round(float(avg_corr.quantile(0.10)), 3),
            "avg_corr_global_q90": round(float(avg_corr.quantile(0.90)), 3),
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
