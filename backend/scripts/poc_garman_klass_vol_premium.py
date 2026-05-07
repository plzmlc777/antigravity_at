#!/usr/bin/env python3
"""Phase R-1 PoC: Garman-Klass vol of premium paradigm.

Signal: Garman-Klass vol estimator using premium OHLC.
  σ²_GK = 0.5 * (ln(H/L))² - (2*ln(2)-1) * (ln(C/O))²
  GK-vol z-score (30d rolling). Direction from prior price return.

Distinct from #1 premium_volatility_regime (range-based simple z) and
#7 premium_intraday_range_zscore (range/median ratio):
  - GK uses C/O information in addition to H/L (more efficient vol estimator)
  - Different statistical structure

§3-G family: premium domain (3rd vol-of-basis paradigm).
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
log = logging.getLogger("poc_garman_klass_vol_premium")

PARADIGM = "garman_klass_vol_premium"
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
    series = df.set_index("ts")["close"].astype(float)
    daily = series.resample("1D", label="right", closed="right").last().dropna()
    daily.index = daily.index.normalize()
    return daily


def load_premium_ohlc(symbol: str) -> pd.DataFrame:
    p = PREMIUM_DIR / f"{symbol}_premium.joblib"
    df = joblib.load(p)
    out = df[["open", "high", "low", "close"]].astype(float).copy()
    out.index = pd.to_datetime(out.index).normalize()
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out


def compute_gk_vol(prem_ohlc: pd.DataFrame) -> pd.Series:
    """Garman-Klass vol on premium series. Premium can be negative so we
    work with shifted series (premium + offset). Use absolute differences
    instead to avoid log of negatives.

    Approximation: vol²_proxy = 0.5*(H-L)² - (2ln(2)-1)*(C-O)²
    (drops log scaling but preserves variance ranking)
    """
    H = prem_ohlc["high"]; L = prem_ohlc["low"]
    C = prem_ohlc["close"]; O = prem_ohlc["open"]
    hl_term = 0.5 * (H - L) ** 2
    co_term = (2 * np.log(2) - 1) * (C - O) ** 2
    var_gk = hl_term - co_term
    var_gk = var_gk.clip(lower=0)
    return np.sqrt(var_gk)


def simulate(close: pd.Series, prem_ohlc: pd.DataFrame, *,
             zwin: int, ret_lookback: int, entry_z: float, hold_days: int,
             sl_pct: float, fee_rate: float, capital: float, train_frac: float,
             mode: str = "follow",
             ) -> dict:
    df = pd.concat({
        "close": close,
        "prem_o": prem_ohlc["open"],
        "prem_h": prem_ohlc["high"],
        "prem_l": prem_ohlc["low"],
        "prem_c": prem_ohlc["close"],
    }, axis=1, join="inner").dropna()
    prem_only = pd.DataFrame({
        "open": df["prem_o"], "high": df["prem_h"],
        "low": df["prem_l"], "close": df["prem_c"],
    }, index=df.index)
    df["gk_vol"] = compute_gk_vol(prem_only)
    df["gk_z"] = (df["gk_vol"] - df["gk_vol"].rolling(zwin).mean()) / df["gk_vol"].rolling(zwin).std()
    df["prior_ret"] = df["close"].pct_change(ret_lookback)
    df = df.dropna(subset=["gk_z", "prior_ret"])

    n = len(df)
    if n < 100:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; target_hold = 0
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
                trades.append({"side": side, "return_pct": ret_pct,
                               "exit_reason": exit_reason, "bars_held": bars_held})
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            gz = float(row["gk_z"]); pr = float(row["prior_ret"])
            if math.isnan(gz) or math.isnan(pr):
                equity_curve.append((ts, equity)); continue
            if gz > entry_z and abs(pr) > 0:
                if mode == "follow":
                    side = 1 if pr > 0 else -1
                else:
                    side = -1 if pr > 0 else 1
                if side > 0:
                    n_long += 1
                else:
                    n_short += 1
                in_pos = True
                entry_px = px; entry_ts = str(ts)
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
    p.add_argument("--ret-lookback", type=int, default=5)
    p.add_argument("--entry-z", type=float, default=1.5)
    p.add_argument("--hold-days", type=int, default=5)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--mode", choices=["follow", "fade"], default="follow")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or f"poc_zw{args.zwin}_rl{args.ret_lookback}_ez{args.entry_z}_h{args.hold_days}_{args.mode}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            close = load_close_1d(sym)
            prem = load_premium_ohlc(sym)
            log.info("%s close: %d days, premium: %d days", sym, len(close), len(prem))
            sim = simulate(close, prem,
                           zwin=args.zwin, ret_lookback=args.ret_lookback,
                           entry_z=args.entry_z, hold_days=args.hold_days,
                           sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                           capital=args.capital, train_frac=args.train_frac,
                           mode=args.mode)
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
