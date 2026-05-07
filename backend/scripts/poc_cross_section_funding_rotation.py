#!/usr/bin/env python3
"""Phase R-1 PoC: Cross-section funding rate rotation paradigm.

Hypothesis: At each rebalance period, rank 14 symbols by current funding
rate. Long top-K most NEGATIVE funding (longs being paid by shorts →
favorable for going long) + Short top-K most POSITIVE funding (shorts
being paid by longs, fade these). Equal-weighted long-short market-neutral
portfolio.

Distinct from seeded paradigms:
  - funding_carry: per-symbol z-score reversal at 8h.
  - funding_dispersion: cross-section z trade (single-symbol entries).
  - This: rule-based portfolio rotation (no per-symbol z, only rank).

§3 risks: §3-G family (multi_symbol_portfolio graveyard ML version,
funding_carry/dispersion data extension). Mitigation: rule-based ranking is
distinct from ML-based portfolio.
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
log = logging.getLogger("poc_cross_section_funding_rotation")

PARADIGM = "cross_section_funding_rotation"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_funding_close_panel(symbols: list[str], freq: str = "1D") -> pd.DataFrame:
    """Returns wide DataFrame: index=ts, columns=funding & close per symbol."""
    s = SessionLocal()
    fundings = {}
    closes = {}
    try:
        for sym in symbols:
            f = pd.read_sql(
                text("""
                    SELECT funding_time AS ts, funding_rate
                    FROM binance_funding_rate WHERE symbol=:sym
                    ORDER BY funding_time
                """),
                s.connection(),
                params={"sym": sym},
                parse_dates=["ts"],
            )
            if f.empty:
                continue
            f = f.set_index("ts")["funding_rate"].astype(float)
            fundings[sym] = f.resample(freq, label="right", closed="right").mean()

            c = pd.read_sql(
                text("""
                    SELECT timestamp AS ts, close
                    FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                    ORDER BY timestamp
                """),
                s.connection(),
                params={"sym": sym},
                parse_dates=["ts"],
            )
            if c.empty:
                continue
            c = c.set_index("ts")["close"].astype(float)
            closes[sym] = c.resample(freq, label="right", closed="right").last()
    finally:
        s.close()

    fund_df = pd.DataFrame(fundings)
    close_df = pd.DataFrame(closes)
    fund_df.columns = [f"fund_{c}" for c in fund_df.columns]
    close_df.columns = [f"close_{c}" for c in close_df.columns]
    df = pd.concat([fund_df, close_df], axis=1).dropna(how="all")
    df.index = df.index.normalize() if freq == "1D" else df.index
    return df


def simulate_rotation(df: pd.DataFrame, symbols: list[str], *,
                      top_k: int, hold_periods: int, fee_rate: float,
                      capital: float, train_frac: float, mode: str = "carry",
                      ) -> dict:
    """At each rebalance:
      mode='carry': LONG top-K most negative funding, SHORT top-K most positive.
      mode='reverse': LONG top-K most positive funding, SHORT top-K most negative.
    Hold for hold_periods, equal-weighted. Compare to equal-weighted basket buy-hold.
    """
    fund_cols = [f"fund_{s}" for s in symbols if f"fund_{s}" in df.columns]
    close_cols = [f"close_{s}" for s in symbols if f"close_{s}" in df.columns]
    syms = [c[5:] for c in fund_cols]
    if len(syms) < top_k * 2:
        return {"error": f"too few symbols ({len(syms)}) for top_k={top_k}", "n_trades": 0}

    work = df.dropna(subset=fund_cols + close_cols).copy()
    n = len(work)
    if n < 30:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = work.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    rebalances = 0
    long_basket_returns = []
    short_basket_returns = []
    pos_long: list[str] = []
    pos_short: list[str] = []
    bars_since_rebal = 0
    entry_prices: dict[str, float] = {}

    def close_positions(t_idx: int):
        nonlocal equity, pos_long, pos_short, entry_prices
        if not pos_long and not pos_short:
            return
        prices_now = test[close_cols].iloc[t_idx]
        long_rs = []
        short_rs = []
        for sym in pos_long:
            cprev = entry_prices.get(sym)
            cnow = float(prices_now[f"close_{sym}"])
            if cprev and cprev > 0:
                long_rs.append((cnow - cprev) / cprev - 2 * fee_rate)
        for sym in pos_short:
            cprev = entry_prices.get(sym)
            cnow = float(prices_now[f"close_{sym}"])
            if cprev and cprev > 0:
                short_rs.append((cprev - cnow) / cprev - 2 * fee_rate)
        long_avg = float(np.mean(long_rs)) if long_rs else 0.0
        short_avg = float(np.mean(short_rs)) if short_rs else 0.0
        port_ret = 0.5 * long_avg + 0.5 * short_avg
        equity *= (1 + port_ret)
        long_basket_returns.append(long_avg)
        short_basket_returns.append(short_avg)
        pos_long = []; pos_short = []; entry_prices = {}

    def open_positions(t_idx: int):
        nonlocal pos_long, pos_short, rebalances, entry_prices
        funds = test[fund_cols].iloc[t_idx]
        prices = test[close_cols].iloc[t_idx]
        ranked = sorted(syms, key=lambda s: float(funds[f"fund_{s}"]))
        if mode == "carry":
            longs = ranked[:top_k]    # most negative
            shorts = ranked[-top_k:]  # most positive
        else:  # reverse
            longs = ranked[-top_k:]
            shorts = ranked[:top_k]
        pos_long = list(longs)
        pos_short = list(shorts)
        entry_prices = {sym: float(prices[f"close_{sym}"]) for sym in pos_long + pos_short}
        rebalances += 1

    open_positions(0)
    for i in range(1, len(test)):
        bars_since_rebal += 1
        if bars_since_rebal >= hold_periods:
            close_positions(i)
            open_positions(i)
            bars_since_rebal = 0
        equity_curve.append((test.index[i], equity))
    close_positions(len(test) - 1)

    # benchmark: equal-weighted buy-hold of all symbols
    all_returns = []
    for sym in syms:
        c0 = float(test[f"close_{sym}"].iloc[0])
        cN = float(test[f"close_{sym}"].iloc[-1])
        if c0 > 0:
            all_returns.append((cN - c0) / c0)
    bh_pct = float(np.mean(all_returns)) if all_returns else 0.0

    total_return_pct = (equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    if long_basket_returns:
        all_rs = np.array([0.5*l + 0.5*s for l, s in zip(long_basket_returns, short_basket_returns)])
        mu = all_rs.mean(); sd = all_rs.std(ddof=1) if len(all_rs) > 1 else 0.0
        oos_seconds = (test.index[-1] - test.index[0]).total_seconds()
        rebalances_per_year = (rebalances / oos_seconds * 31536000.0
                               if oos_seconds > 0 else 0)
        sharpe_ann = (float(mu / sd * math.sqrt(max(rebalances_per_year, 1)))
                      if sd > 0 else 0.0)
        wins = all_rs[all_rs > 0]
        win_rate_pct = float(len(wins) / len(all_rs) * 100)
        gw = float(all_rs[all_rs > 0].sum()) if (all_rs > 0).any() else 0.0
        gl = float(-all_rs[all_rs < 0].sum()) if (all_rs < 0).any() else 0.0
        profit_factor = (float(gw / gl) if gl > 0
                         else (float("inf") if gw > 0 else 0.0))
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0

    oos_days = int((test.index[-1] - test.index[0]).total_seconds() // 86400)

    return {
        "n_trades": rebalances,
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
        "n_symbols": len(syms),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+",
                   default=["AVAXUSDT", "AXSUSDT", "BTCUSDT", "COMPUSDT",
                            "DOGEUSDT", "ETCUSDT", "ETHUSDT", "HBARUSDT",
                            "ICPUSDT", "LDOUSDT", "LINKUSDT", "SOLUSDT",
                            "UNIUSDT", "WLDUSDT"])
    p.add_argument("--freq", default="1D")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--hold-periods", type=int, default=7)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--mode", choices=["carry", "reverse"], default="carry")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_freq{args.freq}_k{args.top_k}_h{args.hold_periods}_{args.mode}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading panel for %d symbols at freq=%s ...", len(args.symbols), args.freq)
    df = load_funding_close_panel(args.symbols, freq=args.freq)
    log.info("Panel loaded: %d rows, %d cols. Date range %s → %s",
             len(df), df.shape[1], df.index[0], df.index[-1])

    sim = simulate_rotation(
        df, args.symbols,
        top_k=args.top_k, hold_periods=args.hold_periods,
        fee_rate=args.fee_rate, capital=args.capital,
        train_frac=args.train_frac, mode=args.mode,
    )
    log.info("alpha=%.2f sharpe=%.2f bh=%.2f total=%.2f mdd=%.1f wr=%.1f pf=%s rebalances=%d (n_syms=%d, oos=%d days)",
             sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
             sim.get("buy_hold_pct", 0), sim.get("total_return_pct", 0),
             sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
             sim.get("profit_factor", 0), sim["n_trades"],
             sim.get("n_symbols", 0), sim.get("oos_days", 0))

    out_meta = {
        "paradigm": PARADIGM, "phase": "R-1_PoC", "spec_name": tag,
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "config": vars(args), "result": sim,
    }
    out_meta_path = OUT_DIR / f"{tag}__metrics.json"
    out_meta_path.write_text(json.dumps(out_meta, indent=2, default=str))
    print("\n=== Result ===")
    print(json.dumps(sim, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
