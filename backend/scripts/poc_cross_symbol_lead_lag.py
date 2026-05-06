#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Cross-Symbol Lead-Lag (BTC spillover) paradigm.

Hypothesis: BTCUSDT acts as the market leader at 5m granularity. When BTC
makes a strong directional move within the past N bars (LEAD_LOOKBACK), but
the target altcoin has NOT yet followed proportionally (catch-up gap >
GAP_THRESHOLD), the alt is more likely to catch up to BTC's direction in the
next K bars (HOLD_BARS) than to revert.

Distinct from prior paradigms (17 graveyard + 3 seeded):
  - cross_symbol_correlation_regime (graveyard): CONTEMPORANEOUS corr regime,
    direction fade. This paradigm: LAGGED info flow with catch-up direction.
  - autocorr_regime (lag-1 seeded LINK/UNI): INTRA-symbol time dependence
  - All funding-domain paradigms: orthogonal data domain
  - Distinct dimension: cross-symbol asymmetric directional spillover

Entry rule (per target alt symbol):
  1. Compute BTC's lookback return: R_btc = sum(log_returns[-LEAD_LOOKBACK:])
  2. Compute alt's lookback return: R_alt = sum(log_returns[-LEAD_LOOKBACK:])
  3. If |R_btc| > LEAD_THRESH AND sign(R_btc) == intended direction AND
     R_alt has lagged: |R_alt| < FOLLOW_RATIO * |R_btc|
     → enter alt in sign(R_btc) direction
  4. Hold HOLD_BARS or stop on SL

Anti-pattern checks:
  - rare-event: R-1 threshold sweep mandatory (lower threshold → check sharpe)
  - in-sample §3-F: real-time, no train-table lookup
  - family-extension §3-G: not within autocorr/cross_symbol_correlation family
    (those are contemporaneous; this is lagged spillover)
  - multi-symbol consistency §3-E: R-3 perm test mandatory

WARNING: BTC spillover is well-known systematic risk; alpha may be a
crowded-trade artifact rather than tradable edge. perm test will arbitrate.

Usage:
  python -m scripts.poc_cross_symbol_lead_lag --symbols SOLUSDT
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
log = logging.getLogger("poc_cross_symbol_lead_lag")

PARADIGM = "cross_symbol_lead_lag"
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
    return df_5m


def simulate_lead_lag(close_alt: pd.Series, close_btc: pd.Series, *,
                       lead_lookback: int, lead_thresh: float,
                       follow_ratio: float, hold_bars: int, sl_pct: float,
                       fee_rate: float, capital: float, train_frac: float,
                       ) -> dict:
    """Per-alt-symbol simulation given aligned alt and BTC close series."""
    df = pd.DataFrame({"alt": close_alt, "btc": close_btc}).dropna()
    df["log_ret_alt"] = np.log(df["alt"] / df["alt"].shift(1))
    df["log_ret_btc"] = np.log(df["btc"] / df["btc"].shift(1))
    df["R_alt"] = df["log_ret_alt"].rolling(lead_lookback).sum()
    df["R_btc"] = df["log_ret_btc"].rolling(lead_lookback).sum()
    df = df.dropna(subset=["R_alt", "R_btc"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; target_hold = 0

    for i in range(1, len(test)):
        ts = test.index[i]
        cpx = float(test["alt"].iloc[i])

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
                    "side": side,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            r_btc = float(row["R_btc"]); r_alt = float(row["R_alt"])
            if math.isnan(r_btc) or math.isnan(r_alt):
                equity_curve.append((ts, equity)); continue
            if abs(r_btc) > lead_thresh and (
                # alt has lagged BTC's move (catch-up gap)
                # condition: alt's recent return is in same direction but
                # smaller than follow_ratio * |btc| OR opposite direction
                (np.sign(r_alt) != np.sign(r_btc))
                or (abs(r_alt) < follow_ratio * abs(r_btc))
            ):
                side = 1 if r_btc > 0 else -1
                in_pos = True
                entry_px = cpx; entry_ts = str(ts)
                bars_held = 0; target_hold = hold_bars
            else:
                equity_curve.append((ts, equity)); continue
        equity_curve.append((ts, equity))

    bh_pct = (test["alt"].iloc[-1] / test["alt"].iloc[0]) - 1
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
        "alpha_pct": round(alpha_pct, 2),
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
    p.add_argument("--leader", default="BTCUSDT")
    p.add_argument("--lead-lookback", type=int, default=3)  # 15min
    p.add_argument("--lead-thresh", type=float, default=0.005)  # 0.5%
    p.add_argument("--follow-ratio", type=float, default=0.5)
    p.add_argument("--hold-bars", type=int, default=12)  # 1h
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_lb{args.lead_lookback}_lt{args.lead_thresh}_fr{args.follow_ratio}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading leader %s 5m ohlcv...", args.leader)
    leader_df = load_ohlcv_5m(args.leader)
    log.info("Leader loaded: %d bars (%s → %s)",
             len(leader_df), leader_df.index[0], leader_df.index[-1])

    rows = []
    for sym in args.symbols:
        if sym == args.leader:
            continue
        try:
            alt_df = load_ohlcv_5m(sym)
            # Inner-join close series
            joined = pd.concat({"alt": alt_df["close"],
                                "btc": leader_df["close"]}, axis=1).dropna()
            sim = simulate_lead_lag(
                joined["alt"], joined["btc"],
                lead_lookback=args.lead_lookback, lead_thresh=args.lead_thresh,
                follow_ratio=args.follow_ratio, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
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
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct",
            "buy_hold_pct", "sharpe_ann", "max_dd_pct", "win_rate_pct",
            "profit_factor", "oos_days"]
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
