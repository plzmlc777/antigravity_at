#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Cross-Symbol Dispersion Breakout paradigm.

Hypothesis: cross-section std of 5m log returns across the 14 paper-pool
universe at each instant measures market vol dispersion. Compression regime
(low pct dispersion) is a coiled-spring state — next move is more likely a
breakout in recent direction (continuation). Expansion regime (high pct) is
chaotic — recent direction more likely to reverse.

Distinct from prior cross-section paradigms (graveyards):
  - cross_symbol_correlation_regime (graveyard): contemporaneous CORRELATION
    matrix avg → market co-movement regime. perm 0.17-0.39 fail.
  - funding_dispersion (seeded ETC): funding-rate cross-section z (8h period
    domain, different data source from price returns)
  - **cross_symbol_dispersion_breakout**: cross-section STD of returns
    (vol spread regime) — different from corr (co-movement) and from
    funding (rate domain)

ANTI-PATTERN risk §3-G (family-extension):
  cross_symbol_correlation_regime already failed. dispersion may be a
  weak sibling in the cross-section family. R-3 perm test arbitrates.

Pipeline:
  1. Load 14 paper-pool 5m close → wide returns df (inner-join).
  2. Compute cross-section std (across columns) at each timestamp.
  3. Rolling 288-bar percentile rank of cross-section std.
  4. Direction signal: target symbol's recent DIR_LOOKBACK pct change.
  5. Entry per regime + direction:
     low pct (compression) + dir up → LONG (breakout continuation)
     low pct (compression) + dir down → SHORT
     high pct (expansion) + dir up → SHORT (chaos reversal)
     high pct (expansion) + dir down → LONG
  6. Exit at HOLD bars or SL.

Usage:
  python -m scripts.poc_cross_symbol_dispersion_breakout --symbols SOLUSDT
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
log = logging.getLogger("poc_cross_symbol_dispersion_breakout")

PARADIGM = "cross_symbol_dispersion_breakout"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

DEFAULT_UNIVERSE = [
    "HBARUSDT", "AXSUSDT", "COMPUSDT", "DOGEUSDT", "LDOUSDT",
    "SOLUSDT", "AVAXUSDT", "LINKUSDT", "UNIUSDT", "ETCUSDT",
]


def load_universe_returns_5m(universe: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
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
            if df.empty: continue
            ser = df.set_index("ts")["close"].astype(float)
            ser_5m = ser.resample("5min", label="right", closed="right").last().dropna()
            ser_5m.name = sym
            frames.append(ser_5m)
    finally:
        s.close()
    if not frames:
        raise ValueError("No symbols loaded")
    closes = pd.concat(frames, axis=1).sort_index().dropna(how="any")
    rets = np.log(closes / closes.shift(1)).dropna(how="any")
    log.info("Universe %d symbols, common 5m bars: %d (%s → %s)",
             len(closes.columns), len(rets), rets.index[0], rets.index[-1])
    return closes, rets


def compute_dispersion_pct(rets: pd.DataFrame, pct_window: int) -> pd.Series:
    """Cross-section std at each timestamp, then rolling percentile rank."""
    xs_std = rets.std(axis=1)
    pct = xs_std.rolling(pct_window, min_periods=pct_window // 2).rank(pct=True)
    return pct


def simulate_dispersion_breakout(
    closes: pd.DataFrame,
    rets: pd.DataFrame,
    disp_pct: pd.Series,
    target_symbol: str,
    *,
    p_low: float, p_high: float,
    dir_lookback: int, hold_bars: int, sl_pct: float,
    fee_rate: float, capital: float, train_frac: float,
    regime_filter: str = "both",
) -> dict:
    """regime_filter: 'low_only' / 'high_only' / 'both'"""
    px = closes[target_symbol]
    df = pd.DataFrame({"close": px, "disp_pct": disp_pct}).dropna()
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
    entry_ts = ""; target_hold = 0; entry_regime_kind = ""

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
                    "side": side, "regime_kind": entry_regime_kind,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            pct = float(row["disp_pct"]); dr = float(row["dir_ret"])
            if math.isnan(pct) or math.isnan(dr) or dr == 0:
                equity_curve.append((ts, equity)); continue

            chosen = ""
            if pct < p_low and regime_filter in ("low_only", "both"):
                # compression breakout: continuation
                side = 1 if dr > 0 else -1
                chosen = "low"; n_low += 1
            elif pct > p_high and regime_filter in ("high_only", "both"):
                # expansion: reversal
                side = -1 if dr > 0 else 1
                chosen = "high"; n_high += 1
            else:
                equity_curve.append((ts, equity)); continue

            in_pos = True
            entry_px = cpx; entry_ts = str(ts)
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
        "symbol": target_symbol,
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
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--universe", nargs="+", default=DEFAULT_UNIVERSE)
    p.add_argument("--pct-window", type=int, default=288)
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
        f"poc_w{args.pct_window}_pl{args.p_low}_ph{args.p_high}"
        f"_dl{args.dir_lookback}_h{args.hold_bars}_{args.regime_filter}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    closes, rets = load_universe_returns_5m(args.universe)
    disp_pct = compute_dispersion_pct(rets, args.pct_window).dropna()

    rows = []
    for sym in args.symbols:
        if sym not in closes.columns:
            log.warning("%s not in universe — skipping", sym); continue
        try:
            sim = simulate_dispersion_breakout(
                closes, rets, disp_pct, sym,
                p_low=args.p_low, p_high=args.p_high,
                dir_lookback=args.dir_lookback, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                regime_filter=args.regime_filter,
            )
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d H=%d)",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_low_entries", 0), sim.get("n_high_entries", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_low_entries", "n_high_entries",
            "alpha_pct", "total_return_pct", "buy_hold_pct", "sharpe_ann",
            "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days"]
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
