#!/usr/bin/env python3
"""Phase R-1 PoC: Funding-Premium spread z-score paradigm.

Signal: spread_z = (funding_daily_z - premium_daily_z) at daily timestamp.
Tests if extreme divergence between funding and premium z-scores
predicts mean reversion direction.

Modes:
  - 'fade': |spread_z| > entry → trade opposite spread sign (mean-revert)
  - 'follow': |spread_z| > entry → trade with spread sign (momentum)

§3-G strong: two seeded paradigms combined. Per queue rule, jump to R-3
perm test directly. 3σ borderline → graveyard.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_funding_premium_spread_zscore")

PARADIGM = "funding_premium_spread_zscore"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
PREMIUM_DIR = ROOT / "runs" / "premium_index"


def load_close_1d(symbol: str) -> pd.Series:
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
    series = df.set_index("ts")["close"].astype(float)
    daily = series.resample("1D", label="right", closed="right").last().dropna()
    daily.index = daily.index.normalize()
    return daily


def load_premium_close_1d(symbol: str) -> pd.Series:
    p = PREMIUM_DIR / f"{symbol}_premium.joblib"
    if not p.exists():
        raise FileNotFoundError(f"No premium joblib for {symbol}: {p}")
    df = joblib.load(p)
    s = df["close"].astype(float).copy()
    s.index = pd.to_datetime(s.index).normalize()
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s


def load_funding_1d(symbol: str) -> pd.Series:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT funding_time AS ts, funding_rate
                FROM binance_funding_rate WHERE symbol=:sym
                ORDER BY funding_time
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["ts"],
        )
    finally:
        s.close()
    if df.empty:
        raise ValueError(f"No funding for {symbol}")
    df["funding_rate"] = df["funding_rate"].astype(float)
    s2 = df.set_index("ts")["funding_rate"]
    daily = s2.resample("1D", label="right", closed="right").mean().dropna()
    daily.index = daily.index.normalize()
    return daily


def simulate(close: pd.Series, funding: pd.Series, premium: pd.Series, *,
             zwin: int, entry_z: float, hold_days: int,
             sl_pct: float, fee_rate: float, capital: float, train_frac: float,
             mode: str = "fade",
             ) -> dict:
    df = pd.concat({"close": close, "funding": funding, "premium": premium},
                   axis=1, join="inner").dropna()
    df["fund_z"] = (df["funding"] - df["funding"].rolling(zwin).mean()) / df["funding"].rolling(zwin).std()
    df["prem_z"] = (df["premium"] - df["premium"].rolling(zwin).mean()) / df["premium"].rolling(zwin).std()
    df["spread"] = df["fund_z"] - df["prem_z"]
    df["spread_z"] = (df["spread"] - df["spread"].rolling(zwin).mean()) / df["spread"].rolling(zwin).std()
    df = df.dropna(subset=["spread_z"])

    n = len(df)
    if n < 50:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; target_hold = 0; entry_z_val = 0.0
    n_long = 0; n_short = 0

    for i in range(1, len(test)):
        ts = test.index[i]
        px = float(test["close"].iloc[i])
        if in_pos:
            bars_held += 1
            unrealized = side * (px - entry_px) / entry_px
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
                    "side": side, "entry_z": entry_z_val,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            sz = float(row["spread_z"])
            if math.isnan(sz):
                equity_curve.append((ts, equity)); continue
            if abs(sz) > entry_z:
                if mode == "fade":
                    side = -1 if sz > 0 else 1
                else:
                    side = 1 if sz > 0 else -1
                if side > 0:
                    n_long += 1
                else:
                    n_short += 1
                in_pos = True
                entry_px = px; entry_ts = str(ts); entry_z_val = sz
                bars_held = 0; target_hold = hold_days
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
        "n_long_entries": n_long,
        "n_short_entries": n_short,
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
    p.add_argument("--zwin", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--hold-days", type=int, default=5)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--mode", choices=["fade", "follow"], default="fade")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or f"poc_zw{args.zwin}_ez{args.entry_z}_h{args.hold_days}_{args.mode}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            close = load_close_1d(sym)
            funding = load_funding_1d(sym)
            premium = load_premium_close_1d(sym)
            log.info("%s close: %d days, funding: %d days, premium: %d days",
                     sym, len(close), len(funding), len(premium))
            sim = simulate(
                close, funding, premium,
                zwin=args.zwin, entry_z=args.entry_z, hold_days=args.hold_days,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac, mode=args.mode,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d S=%d)",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_long_entries", 0), sim.get("n_short_entries", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_long_entries", "n_short_entries",
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
