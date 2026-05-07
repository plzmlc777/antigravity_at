#!/usr/bin/env python3
"""Phase R-1 PoC: Funding Flip paradigm.

Hypothesis: when Binance perpetual funding rate flips sign (positive →
negative, or negative → positive), the underlying positioning regime has
shifted. The crowded side that was paying funding has been squeezed out, and a
new positioning regime is forming. This event-based signal is fundamentally
distinct from funding_carry (which uses rolling z-score of funding LEVEL).

Two competing hypotheses (test both via --reverse-sign):
  - REVERSAL (default): the flip is overshoot, price will revert opposite
                        to the new funding side. flip pos→neg → LONG.
  - CONTINUATION (reverse-sign): the flip reflects new directional flow,
                                 ride it. flip pos→neg → SHORT.

Distinct from graveyard paradigms:
  - mean_reversion: z-score of returns (not funding event)
  - funding_window_anomaly: funding TIMING seasonality (not sign flip)
  - funding_carry: funding level z-score (not flip event)

Pipeline (per-symbol):
  1. Load 8h funding_rate + mark_price (1y, ~1095 funding periods).
  2. Detect flip events: sign(funding[t]) != sign(funding[t-1])
     AND |funding[t] - funding[t-1]| > MAGNITUDE threshold
  3. Entry at flip period t:
       - REVERSAL: pos→neg flip → LONG; neg→pos flip → SHORT
       - CONTINUATION: pos→neg flip → SHORT; neg→pos flip → LONG
  4. Exit after HOLD funding periods or SL hit.
  5. PnL = price PnL + accumulated funding (held side receives funding when
     crowd direction matches received-funding direction) - 2 × fee.

Usage:
  python -m scripts.poc_funding_flip --symbols SOLUSDT
  python -m scripts.poc_funding_flip --symbols HBARUSDT AXSUSDT --reverse-sign
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
log = logging.getLogger("poc_funding_flip")

PARADIGM = "funding_flip"
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
    log.info("Loaded %s funding: %d periods (%s → %s)",
             symbol, len(df), df.index[0], df.index[-1])
    return df


def simulate_funding_flip(df: pd.DataFrame, *, magnitude: float, hold_periods: int,
                          sl_pct: float, fee_rate: float, capital: float,
                          train_frac: float, reverse_sign: bool) -> dict:
    df = df.copy()
    df["prev_funding"] = df["funding_rate"].shift(1)
    df["delta"] = df["funding_rate"] - df["prev_funding"]
    df["sign"] = np.sign(df["funding_rate"])
    df["prev_sign"] = np.sign(df["prev_funding"])
    df["flip"] = ((df["sign"] != df["prev_sign"]) &
                  (df["sign"] != 0) & (df["prev_sign"] != 0) &
                  (df["delta"].abs() > magnitude))
    df = df.dropna(subset=["funding_rate", "prev_funding"])

    n = len(df)
    if n < 200:
        return {"error": f"too few periods ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    prices = test["mark_price"].values
    fundings = test["funding_rate"].values
    flips = test["flip"].values
    signs = test["sign"].values
    timestamps = test.index

    equity = capital
    equity_curve = [(timestamps[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    accum_funding = 0.0; entry_ts = ""

    for i in range(1, len(test)):
        px = prices[i]; ts = timestamps[i]; funding_now = fundings[i]
        if in_pos:
            bars_held += 1
            accum_funding += -side * funding_now
            price_pnl = side * (px - entry_px) / entry_px
            unrealized = price_pnl + accum_funding
            exit_reason = None
            if unrealized < -sl_pct:
                exit_reason = "sl"
            elif bars_held >= hold_periods:
                exit_reason = "time"
            if exit_reason:
                ret_pct = unrealized - 2 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(ts),
                    "side": side, "price_pnl": round(price_pnl, 5),
                    "accum_funding": round(accum_funding, 5),
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0; accum_funding = 0.0

        if not in_pos and flips[i]:
            new_sign = signs[i]   # sign of current funding (positive or negative)
            # REVERSAL: pos→neg flip (sign=-1) → LONG; neg→pos flip (sign=+1) → SHORT
            # CONTINUATION: pos→neg flip → SHORT; neg→pos flip → LONG
            if new_sign < 0:
                side = (-1 if reverse_sign else 1)
            elif new_sign > 0:
                side = (1 if reverse_sign else -1)
            in_pos = True
            entry_px = px; entry_ts = str(ts); bars_held = 0; accum_funding = 0.0

        equity_curve.append((ts, equity))

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
    n_flips_test = int(test["flip"].sum())

    return {
        "n_trades": len(trades),
        "n_flips_test": n_flips_test,
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
    p.add_argument("--magnitude", type=float, default=0.0001)  # |Δfunding| > 0.01%
    p.add_argument("--hold-periods", type=int, default=3)      # 3 funding = 1 day
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true",
                   help="Continuation hypothesis instead of reversal")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    direction = "cont" if args.reverse_sign else "rev"
    tag = args.tag or (
        f"poc_{direction}_mag{args.magnitude}_hold{args.hold_periods}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_funding(sym)
            sim = simulate_funding_flip(
                df, magnitude=args.magnitude, hold_periods=args.hold_periods,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                reverse_sign=args.reverse_sign,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d flips=%d",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_flips_test", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_flips_test", "alpha_pct",
            "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days"]
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
            "trades_per_symbol_mean": round(float(df_out["n_trades"].mean()), 1),
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
