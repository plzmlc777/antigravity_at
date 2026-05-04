#!/usr/bin/env python3
"""Phase R-1 PoC: Funding rate carry / mean-reversion paradigm.

Hypothesis: when perpetual futures funding rate is in an extreme regime (e.g.,
+3σ above its rolling mean), one side of the market is paying the other to keep
its position. The crowded side typically reverses — both because the funding
flow drains the crowd's edge and because extreme positioning precedes squeezes.
A pure funding-driven strategy should be orthogonal to every paper-pool spec
(none of which use funding rate directionally, beyond the discarded F source).

Pipeline (per-symbol z-score reversal on funding_rate):
  1. Load 8h funding_rate + mark_price from binance_funding_rate (1y, 6 symbols).
  2. Compute funding z-score on rolling LOOKBACK funding periods.
  3. Entry: z > +ENTRY_Z → SHORT (crowd is long, pays funding; expect reversal)
            z < -ENTRY_Z → LONG (crowd is short, pays funding; expect reversal)
  4. Hold: accumulate funding income each 8h period (short collects on positive
     funding); exit when |z| < EXIT_Z, or SL hit, or max_hold timeout.
  5. PnL = price-PnL + accumulated funding − fees.
  6. Per-symbol metrics + aggregate.

Usage:
  python -m scripts.poc_funding_carry
  python -m scripts.poc_funding_carry --entry-z 2.5 --lookback 30
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
log = logging.getLogger("poc_funding_carry")

PARADIGM = "funding_carry"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT"]


def load_funding(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT funding_time AS ts, funding_rate, mark_price
                FROM binance_funding_rate WHERE symbol=:sym
                ORDER BY funding_time
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["ts"],
        )
    finally:
        s.close()
    df = df.set_index("ts")
    df["funding_rate"] = df["funding_rate"].astype(float)
    df["mark_price"] = df["mark_price"].astype(float)
    log.info("Loaded %s funding: %d periods (%s → %s)",
             symbol, len(df), df.index[0], df.index[-1])
    return df


def simulate_funding_reversal(df: pd.DataFrame, *, lookback: int, entry_z: float,
                              exit_z: float, max_hold: int, sl_pct: float,
                              fee_rate: float, capital: float, train_frac: float
                              ) -> dict:
    df = df.copy()
    df["mean_lb"] = df["funding_rate"].rolling(lookback).mean()
    df["std_lb"] = df["funding_rate"].rolling(lookback).std()
    df["z"] = (df["funding_rate"] - df["mean_lb"]) / df["std_lb"]
    df = df.dropna(subset=["z"])

    n = len(df)
    split = int(n * train_frac)
    test = df.iloc[split:]

    prices = test["mark_price"].values
    fundings = test["funding_rate"].values
    zs = test["z"].values
    timestamps = test.index

    equity = capital
    equity_curve = [(timestamps[0], equity)]
    trades: list[dict] = []
    in_pos = False
    side = 0
    entry_px = 0.0
    bars_held = 0
    accum_funding = 0.0
    entry_ts = ""
    entry_z_value = 0.0

    prev_z = zs[0]
    for i in range(1, len(test)):
        px = prices[i]; z = zs[i]; t = timestamps[i]
        # Funding paid/received THIS period (short receives positive funding)
        funding_now = fundings[i]

        if in_pos:
            bars_held += 1
            # short: receives funding when funding>0 (longs pay shorts)
            # long:  receives funding when funding<0 (shorts pay longs)
            accum_funding += -side * funding_now
            price_pnl = side * (px - entry_px) / entry_px
            unrealized = price_pnl + accum_funding

            exit_reason = None
            if abs(z) < exit_z:
                exit_reason = "mean"
            elif unrealized < -sl_pct:
                exit_reason = "sl"
            elif bars_held >= max_hold:
                exit_reason = "time"

            if exit_reason:
                ret_pct = unrealized - 2 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(t),
                    "side": side, "entry_z": entry_z_value, "exit_z": float(z),
                    "price_pnl": round(price_pnl, 5),
                    "accum_funding": round(accum_funding, 5),
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0; accum_funding = 0.0

        elif not in_pos and not math.isnan(z):
            if prev_z <= entry_z and z > entry_z:
                in_pos = True; side = -1
                entry_px = px; entry_ts = str(t); entry_z_value = float(z)
                bars_held = 0; accum_funding = 0.0
            elif prev_z >= -entry_z and z < -entry_z:
                in_pos = True; side = 1
                entry_px = px; entry_ts = str(t); entry_z_value = float(z)
                bars_held = 0; accum_funding = 0.0

        prev_z = z if not math.isnan(z) else prev_z
        equity_curve.append((t, equity))

    bh_pct = (prices[-1] / prices[0]) - 1
    total_return_pct = (equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    if trades:
        rs = np.array([t["return_pct"] for t in trades])
        mu = rs.mean(); sd = rs.std(ddof=1) if len(rs) > 1 else 0.0
        oos_seconds = (timestamps[-1] - timestamps[0]).total_seconds()
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
        avg_funding_per_trade = float(
            np.mean([t["accum_funding"] for t in trades]) * 100)
        funding_share_of_pnl = (avg_funding_per_trade / (mu * 100)
                                if mu != 0 else 0.0)
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0
        avg_funding_per_trade = funding_share_of_pnl = 0.0

    oos_days = int((timestamps[-1] - timestamps[0]).total_seconds() // 86400)
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
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "avg_funding_per_trade_pct": round(avg_funding_per_trade, 4),
        "funding_share_of_pnl": round(funding_share_of_pnl, 3),
        "oos_days": oos_days,
        "exit_reasons": exit_reasons,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--exit-z", type=float, default=0.5)
    p.add_argument("--max-hold", type=int, default=15)  # 15 × 8h = 5 days
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or f"6sym_z{args.entry_z}_lb{args.lookback}_mh{args.max_hold}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_funding(sym)
            if len(df) < 100:
                log.warning("Skip %s: only %d funding periods", sym, len(df))
                continue
            sim = simulate_funding_reversal(
                df, lookback=args.lookback, entry_z=args.entry_z,
                exit_z=args.exit_z, max_hold=args.max_hold,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                train_frac=args.train_frac, capital=args.capital,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d funding_share=%.2f",
                     sym, sim["alpha_pct"], sim["sharpe_ann"], sim["max_dd_pct"],
                     sim["win_rate_pct"], sim["profit_factor"],
                     sim["n_trades"], sim["funding_share_of_pnl"])
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor",
            "avg_funding_per_trade_pct", "funding_share_of_pnl", "oos_days"]
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
            "funding_share_mean": round(float(df_out["funding_share_of_pnl"].mean()), 3),
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
