#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Funding Rate Acceleration paradigm.

Hypothesis: the FIRST DIFFERENCE of per-symbol funding rate (Δfunding =
funding[t] - funding[t-1] across 8h periods) measures positioning ramp speed.
A z-score of Δfunding over rolling N periods identifies acceleration spikes:
  - z(Δfunding) > +ENTRY_Z → rate spiking UP rapidly = long crowd accumulating
    at speed → likely squeeze imminent → SHORT entry
  - z(Δfunding) < -ENTRY_Z → rate spiking DOWN rapidly = short crowd
    accumulating → likely squeeze imminent → LONG entry
  - exit when |z(Δfunding)| < EXIT_Z (acceleration normalizes)

Distinct from prior funding paradigms:
  - funding_carry (seeded HBAR/AXS/COMP): rate LEVEL z-score (extreme positioning)
  - funding_dispersion (seeded ETC): cross-section rate z (peer-relative)
  - funding_window_anomaly (graveyard): 5min seasonality at 8h boundaries
  - funding_flip (graveyard): rate sign change event continuation
  - **funding_acceleration**: rate CHANGE z (positioning ramp SPEED)

ANTI-PATTERN risk §3-G (family-extension):
  funding_carry already captures level extremes. Acceleration may be a
  weak residual (level extremes are typically PRECEDED by high acceleration,
  so signals overlap in time). R-3 perm test mandatory.

Pipeline:
  1. Load 14 paper-pool funding_rate from binance_funding_rate (1y).
  2. Compute Δfunding = funding.diff() per symbol.
  3. Compute rolling N-period z-score of Δfunding.
  4. Entry: z > +ENTRY_Z → SHORT; z < -ENTRY_Z → LONG.
  5. Exit at |z| < EXIT_Z, SL, or max_hold.
  6. PnL = price-PnL + accumulated funding − fees.

Usage:
  python -m scripts.poc_funding_acceleration --symbols SOLUSDT
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
log = logging.getLogger("poc_funding_acceleration")

PARADIGM = "funding_acceleration"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


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
    return df


def simulate_acceleration(df: pd.DataFrame, *, lookback: int, entry_z: float,
                           exit_z: float, max_hold: int, sl_pct: float,
                           fee_rate: float, capital: float, train_frac: float
                           ) -> dict:
    df = df.copy()
    df["delta_f"] = df["funding_rate"].diff()
    df["mean_lb"] = df["delta_f"].rolling(lookback).mean()
    df["std_lb"] = df["delta_f"].rolling(lookback).std()
    df["z"] = (df["delta_f"] - df["mean_lb"]) / df["std_lb"]
    df = df.dropna(subset=["z"])

    n = len(df)
    if n < 50:
        return {"error": f"too few periods ({n})", "n_trades": 0}
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
        funding_now = fundings[i]

        if in_pos:
            bars_held += 1
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
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0

    oos_days = int((timestamps[-1] - timestamps[0]).total_seconds() // 86400)

    return {
        "n_trades": len(trades),
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "oos_days": oos_days,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+",
                   default=["HBARUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "LDOUSDT",
                            "SOLUSDT", "AVAXUSDT", "LINKUSDT", "UNIUSDT", "ETCUSDT"])
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--exit-z", type=float, default=0.5)
    p.add_argument("--max-hold", type=int, default=15)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_lb{args.lookback}_ez{args.entry_z}_xz{args.exit_z}_mh{args.max_hold}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_funding(sym)
            if df.empty:
                log.warning("No funding for %s", sym); continue
            sim = simulate_acceleration(
                df, lookback=args.lookback, entry_z=args.entry_z,
                exit_z=args.exit_z, max_hold=args.max_hold,
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
