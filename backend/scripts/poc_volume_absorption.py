#!/usr/bin/env python3
"""Phase R-1 PoC: Volume Absorption paradigm.

Hypothesis: a "volume absorption" bar — defined as a candle with EXCEPTIONAL
volume (z-score > VOL_Z) AND a SMALL body relative to its range (body/range
ratio < BODY_RATIO) — represents one-sided directional pressure being absorbed
by counterparty (often institutional liquidity providers). This precedes
reversal of the prior trend because the absorbed pressure has been converted
to inventory by the counterparty, who will unwind it back to the market.

Distinct paradigms in graveyard:
  - mean_reversion: z-score reversal of returns (generic, not pattern-specific)
  - ai_native_raw_1m: ML on flattened OHLCV — black box
  - cross_asset_meta: macro features
  - pairs_trading: cointegration
  - funding_window_anomaly: funding TIMING seasonality
volume_absorption is rule-based + specific candle pattern + OHLCV-only +
volume-driven (not return-driven). Genuinely orthogonal.

Pipeline:
  1. Load 1m → resample to 5m bars (open=first, high=max, low=min, close=last,
     volume=sum). Same boundary scheme as funding_window for consistency.
  2. Compute rolling lookback volume z-score and body/range ratio per bar.
  3. Compute prior trend direction over PRIOR_BARS using close pct_change.
  4. Entry: when bar i has vol_z > VOL_Z AND body_ratio < BODY_RATIO:
       - if prior trend up → SHORT (buy pressure absorbed)
       - if prior trend down → LONG (sell pressure absorbed)
  5. Exit: HOLD bars or SL.
  6. PnL = price PnL - 2 × fee.

Usage:
  python -m scripts.poc_volume_absorption --symbols SOLUSDT
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
log = logging.getLogger("poc_volume_absorption")

PARADIGM = "volume_absorption"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlcv_5m(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp AS ts, open, high, low, close, volume
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
    df = df.set_index("ts").astype({"open": float, "high": float, "low": float,
                                     "close": float, "volume": float})
    # Resample 1m → 5m
    df_5m = pd.DataFrame({
        "open": df["open"].resample("5min", label="right", closed="right").first(),
        "high": df["high"].resample("5min", label="right", closed="right").max(),
        "low": df["low"].resample("5min", label="right", closed="right").min(),
        "close": df["close"].resample("5min", label="right", closed="right").last(),
        "volume": df["volume"].resample("5min", label="right", closed="right").sum(),
    }).dropna()
    log.info("Loaded %s 5m: %d bars (%s → %s)",
             symbol, len(df_5m), df_5m.index[0], df_5m.index[-1])
    return df_5m


def simulate_volume_absorption(df: pd.DataFrame, *, lookback: int, prior_bars: int,
                                vol_z: float, body_ratio: float, hold_bars: int,
                                sl_pct: float, fee_rate: float, capital: float,
                                train_frac: float, reverse_sign: bool = False) -> dict:
    df = df.copy()
    # Volume z-score
    df["vol_mean"] = df["volume"].rolling(lookback).mean()
    df["vol_std"] = df["volume"].rolling(lookback).std()
    df["vol_z"] = (df["volume"] - df["vol_mean"]) / df["vol_std"]
    # Body / range ratio
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    df["body_ratio"] = (df["close"] - df["open"]).abs() / rng
    # Prior trend (close pct over prior_bars)
    df["prior_ret"] = df["close"].pct_change(prior_bars).shift(1)
    df = df.dropna(subset=["vol_z", "body_ratio", "prior_ret"])

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
        px = float(test["close"].iloc[i])
        if in_pos:
            bars_held += 1
            price_pnl = side * (px - entry_px) / entry_px
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
                    "side": side, "return_pct": ret_pct,
                    "exit_reason": exit_reason, "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            vz = float(row["vol_z"]); br = float(row["body_ratio"])
            pr = float(row["prior_ret"])
            if not math.isnan(vz) and not math.isnan(br) and not math.isnan(pr):
                if vz > vol_z and br < body_ratio:
                    if pr > 0:
                        in_pos = True; side = (1 if reverse_sign else -1)
                    elif pr < 0:
                        in_pos = True; side = (-1 if reverse_sign else 1)
                    if in_pos:
                        entry_px = px; entry_ts = str(ts); bars_held = 0
                        target_hold = hold_bars
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
        "profit_factor": (round(profit_factor, 3)
                          if profit_factor != float("inf") else "inf"),
        "oos_days": oos_days,
        "exit_reasons": exit_reasons,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--lookback", type=int, default=288)   # 288 × 5m = 1 day
    p.add_argument("--prior-bars", type=int, default=12)  # 1h prior trend
    p.add_argument("--vol-z", type=float, default=2.5)
    p.add_argument("--body-ratio", type=float, default=0.3)
    p.add_argument("--hold-bars", type=int, default=12)   # 1h hold
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true",
                   help="Flip absorption→reversal hypothesis to continuation hypothesis")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_lb{args.lookback}_prior{args.prior_bars}_vz{args.vol_z}"
        f"_br{args.body_ratio}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_volume_absorption(
                df, lookback=args.lookback, prior_bars=args.prior_bars,
                vol_z=args.vol_z, body_ratio=args.body_ratio,
                hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, reverse_sign=args.reverse_sign,
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
