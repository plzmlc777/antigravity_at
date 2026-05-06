#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Partial Autocorrelation Regime (lag-2 PACF) paradigm.

Hypothesis: rolling lag-2 PARTIAL autocorrelation of 5m returns isolates the
direct lag-2 dependence after controlling for lag-1 effects. AR(1) effects
(captured by autocorr_regime, R-3 perm 0.000 PASS, seeded LINK/UNI) are
subtracted. The residual structure measures whether shocks at t-2 reverse or
persist into t — orthogonal to lag-1 dynamics.

Closed-form (assuming AR(2)-equivalent generating process at the window):
  PACF[1] = ρ_1
  PACF[2] = (ρ_2 - ρ_1²) / (1 - ρ_1²)
where ρ_k = rolling lag-k autocorrelation.

Distinct from prior paradigms:
  - autocorr_regime (seeded): uses lag-1 PACF = ρ_1 directly
  - skewness_regime / kurtosis_regime (graveyard): higher-order moments of
    return distribution shape (single-time-point)
  - partial_autocorr_regime: lag-2 PACF — TIME-axis dependence at lag-2
    BEYOND what's explained by lag-1

Pipeline:
  1. Load 1m → resample 5m, log returns.
  2. Compute rolling W-bar acf1 and acf2 → pacf2 = (acf2-acf1²)/(1-acf1²).
  3. Direction signal: recent DIR_LOOKBACK-bar pct change.
  4. Entry per `regime_filter` (rev_only / trend_only / both):
     - pacf2 < -REV_THRESH → AR(2) reversal: fade recent direction
     - pacf2 > +TREND_THRESH → AR(2) trend: follow recent direction
  5. Exit at HOLD bars or SL.

Anti-pattern checks:
  - rare-event (Hurst trap): threshold sweep at R-1 mandatory
  - in-sample optimization §3-F: PACF rolling estimated in real-time, NOT
    train-period table-lookup — paradigm SAFE on this dimension
  - multi-symbol consistency §3-E: R-3 perm test required regardless of R-2

Usage:
  python -m scripts.poc_partial_autocorr_regime --symbols SOLUSDT
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
log = logging.getLogger("poc_partial_autocorr_regime")

PARADIGM = "partial_autocorr_regime"
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


def compute_pacf2(ret: pd.Series, window: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (acf1, acf2, pacf2). pacf2 clipped to [-2, 2] to avoid blowup
    when |acf1| ≈ 1."""
    acf1 = ret.rolling(window).corr(ret.shift(1))
    acf2 = ret.rolling(window).corr(ret.shift(2))
    denom = (1 - acf1 ** 2).where(lambda x: x.abs() > 1e-3, np.nan)
    pacf2 = (acf2 - acf1 ** 2) / denom
    pacf2 = pacf2.clip(-2.0, 2.0)
    return acf1, acf2, pacf2


def simulate_pacf2_regime(df: pd.DataFrame, *, pacf_window: int,
                           trend_thresh: float, rev_thresh: float,
                           dir_lookback: int, hold_bars: int, sl_pct: float,
                           fee_rate: float, capital: float, train_frac: float,
                           regime_filter: str = "rev_only") -> dict:
    df = df.copy()
    df["ret"] = np.log(df["close"] / df["close"].shift(1))
    acf1, acf2, pacf2 = compute_pacf2(df["ret"], pacf_window)
    df["acf1"] = acf1
    df["acf2"] = acf2
    df["pacf2"] = pacf2
    df["dir_ret"] = df["close"].pct_change(dir_lookback).shift(1)
    df = df.dropna(subset=["pacf2", "dir_ret"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; entry_pacf = 0.0; target_hold = 0; entry_regime_kind = ""

    n_trend = 0; n_rev = 0

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
                    "side": side, "entry_pacf": entry_pacf,
                    "regime": entry_regime_kind,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            pacf = float(row["pacf2"]); dr = float(row["dir_ret"])
            if math.isnan(pacf) or math.isnan(dr) or dr == 0:
                equity_curve.append((ts, equity)); continue

            if pacf > trend_thresh and regime_filter in ("trend_only", "both"):
                side = 1 if dr > 0 else -1
                entry_regime_kind = "trend"
                n_trend += 1
            elif pacf < -rev_thresh and regime_filter in ("rev_only", "both"):
                side = -1 if dr > 0 else 1
                entry_regime_kind = "rev"
                n_rev += 1
            else:
                equity_curve.append((ts, equity)); continue

            in_pos = True
            entry_px = cpx; entry_ts = str(ts); entry_pacf = pacf
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

    return {
        "n_trades": len(trades),
        "n_trend_entries": n_trend,
        "n_rev_entries": n_rev,
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
        "pacf2_q10": round(float(test["pacf2"].quantile(0.10)), 3),
        "pacf2_q50": round(float(test["pacf2"].quantile(0.50)), 3),
        "pacf2_q90": round(float(test["pacf2"].quantile(0.90)), 3),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--pacf-window", type=int, default=288)
    p.add_argument("--trend-thresh", type=float, default=0.10)
    p.add_argument("--rev-thresh", type=float, default=0.10)
    p.add_argument("--dir-lookback", type=int, default=12)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--regime-filter", choices=["both", "trend_only", "rev_only"],
                   default="rev_only")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_w{args.pacf_window}_t{args.trend_thresh}_r{args.rev_thresh}"
        f"_dl{args.dir_lookback}_h{args.hold_bars}_{args.regime_filter}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_pacf2_regime(
                df, pacf_window=args.pacf_window,
                trend_thresh=args.trend_thresh, rev_thresh=args.rev_thresh,
                dir_lookback=args.dir_lookback, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                regime_filter=args.regime_filter,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (T=%d R=%d) pacf2 q[10,50,90]=[%.2f,%.2f,%.2f]",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_trend_entries", 0), sim.get("n_rev_entries", 0),
                     sim.get("pacf2_q10", 0), sim.get("pacf2_q50", 0),
                     sim.get("pacf2_q90", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_trend_entries", "n_rev_entries",
            "alpha_pct", "total_return_pct", "buy_hold_pct", "sharpe_ann",
            "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days",
            "pacf2_q10", "pacf2_q50", "pacf2_q90"]
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
