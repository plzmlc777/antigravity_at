#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Funding rate Cross-Section Dispersion paradigm.

Hypothesis: at each 8h funding boundary, the cross-section distribution of
funding rates across the universe reveals which symbols are over/under-
crowded RELATIVE to the rest of the market. A symbol whose funding rate is
many σ above the cross-section mean has disproportionate long-side pressure
versus peers — reversal candidate (SHORT). Symbol below the mean: oversold
shorts paying — LONG candidate.

Distinct from prior funding-domain paradigms:
  - funding_carry: per-symbol time-series z-score reversal (own history)
  - funding_window_anomaly: 5min seasonality at funding boundaries (intraday)
  - funding_flip: funding sign-change continuation event
  - funding_dispersion: cross-section z-score across universe at same instant
    (orthogonal to time-series; can fire when own history is mid-range but
    market-relative position is extreme)

Distinct from cross_symbol_correlation_regime (just-graveyard):
  - that paradigm used 5min returns universe correlation as regime gate +
    naive direction fade — fails perm test (downside-protection artifact)
  - funding_dispersion uses funding RATE cross-section (8h granularity, slow
    crowding signal), not 5min return correlation. funding-domain has one
    PASS so far (funding_carry); domain may carry more signal than xs-corr.

Pipeline (per-symbol cross-section z reversal):
  1. Load 8h funding_rate + mark_price for the universe (wide df aligned).
  2. At each timestamp, compute cross-section mean/std across symbols and
     each symbol's xs_z = (own_funding - xs_mean) / xs_std.
  3. Entry per target: xs_z > +ENTRY_Z → SHORT; xs_z < -ENTRY_Z → LONG.
  4. Hold: accumulate funding income each 8h period (short collects on
     positive funding); exit when |xs_z| < EXIT_Z, SL hit, or max_hold.
  5. PnL = price-PnL + accumulated funding − fees.

Usage:
  python -m scripts.poc_funding_dispersion --symbols SOLUSDT
  python -m scripts.poc_funding_dispersion \
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
log = logging.getLogger("poc_funding_dispersion")

PARADIGM = "funding_dispersion"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

DEFAULT_UNIVERSE = [
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "LDOUSDT",
    "SOLUSDT", "AVAXUSDT", "LINKUSDT", "UNIUSDT", "ETCUSDT",
    "WLDUSDT", "JUPUSDT", "PYTHUSDT", "TONUSDT",
]


def load_funding_universe(universe: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load funding_rate + mark_price for each symbol, align on common index.

    Returns (rates_wide, prices_wide). Both indexed by funding_time, columns
    are symbols. Rows where any symbol is missing are dropped (inner join).
    """
    s = SessionLocal()
    try:
        rate_frames = []
        price_frames = []
        for sym in universe:
            df = pd.read_sql(
                text("""
                    SELECT funding_time AS ts, funding_rate, mark_price
                    FROM binance_funding_rate WHERE symbol=:sym
                    ORDER BY funding_time
                """),
                s.connection(),
                params={"sym": sym},
                parse_dates=["ts"],
            )
            if df.empty:
                log.warning("No funding for %s — skipping", sym); continue
            df = df.set_index("ts")
            df["funding_rate"] = df["funding_rate"].astype(float)
            df["mark_price"] = df["mark_price"].astype(float)
            # Round to nearest hour to align across slight ms drift in funding_time
            df.index = df.index.round("h")
            df = df[~df.index.duplicated(keep="last")]
            rate_frames.append(df["funding_rate"].rename(sym))
            price_frames.append(df["mark_price"].rename(sym))
    finally:
        s.close()
    if not rate_frames:
        raise ValueError("No funding data loaded")
    rates = pd.concat(rate_frames, axis=1).sort_index()
    prices = pd.concat(price_frames, axis=1).sort_index()
    # Drop rows where any symbol missing
    aligned = pd.concat({"r": rates, "p": prices}, axis=1).dropna(how="any")
    rates = aligned["r"]; prices = aligned["p"]
    log.info("Universe %d symbols, common funding periods: %d (%s → %s)",
             len(rates.columns), len(rates), rates.index[0], rates.index[-1])
    return rates, prices


def compute_xs_zscores(rates: pd.DataFrame) -> pd.DataFrame:
    """At each timestamp, z-score each symbol's funding against the universe
    cross-section mean/std at that timestamp."""
    xs_mean = rates.mean(axis=1)
    xs_std = rates.std(axis=1, ddof=1)
    z = rates.sub(xs_mean, axis=0).div(xs_std, axis=0)
    return z


def simulate_xs_z_reversal(
    rates: pd.DataFrame,
    prices: pd.DataFrame,
    xs_z: pd.DataFrame,
    target_symbol: str,
    *,
    entry_z: float,
    exit_z: float,
    max_hold: int,
    sl_pct: float,
    fee_rate: float,
    capital: float,
    train_frac: float,
) -> dict:
    """Per-target-symbol cross-section z-score reversal simulation."""
    fr = rates[target_symbol]
    px = prices[target_symbol]
    z = xs_z[target_symbol]

    df = pd.DataFrame({"funding_rate": fr, "mark_price": px, "z": z}).dropna()
    n = len(df)
    if n < 50:
        return {"error": f"too few periods ({n})", "n_trades": 0,
                "symbol": target_symbol}
    split = int(n * train_frac)
    test = df.iloc[split:]

    fundings = test["funding_rate"].values
    pxs = test["mark_price"].values
    zs = test["z"].values
    timestamps = test.index

    equity = capital
    equity_curve = [(timestamps[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    accum_funding = 0.0; entry_ts = ""; entry_z_value = 0.0

    prev_z = zs[0]
    for i in range(1, len(test)):
        cpx = pxs[i]; zv = zs[i]; t = timestamps[i]
        funding_now = fundings[i]

        if in_pos:
            bars_held += 1
            accum_funding += -side * funding_now
            price_pnl = side * (cpx - entry_px) / entry_px
            unrealized = price_pnl + accum_funding

            exit_reason = None
            if abs(zv) < exit_z:
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
                    "side": side, "entry_z": entry_z_value, "exit_z": float(zv),
                    "price_pnl": round(price_pnl, 5),
                    "accum_funding": round(accum_funding, 5),
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0; accum_funding = 0.0

        elif not in_pos and not math.isnan(zv):
            if prev_z <= entry_z and zv > entry_z:
                in_pos = True; side = -1
                entry_px = cpx; entry_ts = str(t); entry_z_value = float(zv)
                bars_held = 0; accum_funding = 0.0
            elif prev_z >= -entry_z and zv < -entry_z:
                in_pos = True; side = 1
                entry_px = cpx; entry_ts = str(t); entry_z_value = float(zv)
                bars_held = 0; accum_funding = 0.0

        prev_z = zv if not math.isnan(zv) else prev_z
        equity_curve.append((t, equity))

    bh_pct = (pxs[-1] / pxs[0]) - 1
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
        "symbol": target_symbol,
        "n_trades": len(trades),
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "avg_funding_per_trade_pct": round(avg_funding_per_trade, 4),
        "funding_share_of_pnl": round(funding_share_of_pnl, 3),
        "oos_days": oos_days,
        "exit_reasons": exit_reasons,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"],
                   help="Target symbols to backtest.")
    p.add_argument("--universe", nargs="+", default=DEFAULT_UNIVERSE,
                   help="Universe used for the cross-section z-score.")
    p.add_argument("--entry-z", type=float, default=1.5)
    p.add_argument("--exit-z", type=float, default=0.3)
    p.add_argument("--max-hold", type=int, default=9)  # 9 × 8h = 3 days
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_ez{args.entry_z}_xz{args.exit_z}_mh{args.max_hold}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rates, prices = load_funding_universe(args.universe)
    xs_z = compute_xs_zscores(rates)
    log.info("xs_z stats per symbol (mean ≈0, std ≈1 expected; abs>2 frequency):")
    for sym in xs_z.columns:
        zs = xs_z[sym].dropna()
        log.info("  %s: |z|>1.5 freq=%.3f, |z|>2.0 freq=%.3f, max=%.2f, min=%.2f",
                 sym, (zs.abs() > 1.5).mean(), (zs.abs() > 2.0).mean(),
                 zs.max(), zs.min())

    rows = []
    for sym in args.symbols:
        if sym not in rates.columns:
            log.warning("%s not in universe — skipping", sym); continue
        try:
            sim = simulate_xs_z_reversal(
                rates, prices, xs_z, sym,
                entry_z=args.entry_z, exit_z=args.exit_z, max_hold=args.max_hold,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
            )
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d funding_share=%.2f",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("funding_share_of_pnl", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor",
            "avg_funding_per_trade_pct", "funding_share_of_pnl", "oos_days"]
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
