#!/usr/bin/env python3
"""Phase R-1 PoC: Joint 3-Signal Ensemble paradigm.

Hypothesis: Combining 3 seeded paradigm signals via voting could either:
(a) Filter false positives by requiring agreement → higher per-trade alpha
(b) Detect correlated signals as alpha residual → §3-G fail mode

The 3 component paradigms (all R-5 seeded ⭐):
  1. premium_index_zscore (24th, perm 9σ DOGE): daily premium close 30d z,
     follow mode → sign(z) at |z|>2
  2. oi_price_decoupling (21st, perm 6.7σ AVAX): 5m OI Δ × price Δ joint z,
     confirm mode → sign(price_z) when both extreme & same sign
  3. funding_carry (1st seed): 8h funding rate 30-period z, fade reversal
     → -sign(z) at |z|>2.5

Voting strategy modes:
  - 'any_majority': ≥1 fires; if multiple, take majority direction; tie→skip
  - 'require_2': only enter if ≥2 agree on same direction
  - 'unanimous': only enter if all 3 fire with same sign
  - 'sum_threshold': continuous weighted sum direction sign

Daily granularity (slowest paradigm). 5m and 8h signals forward-filled to day.

Usage:
  python -m scripts.poc_joint_3signal_ensemble --symbols SOLUSDT --vote require_2
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
log = logging.getLogger("poc_joint_3signal_ensemble")

PARADIGM = "joint_3signal_ensemble"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
PREMIUM_DIR = ROOT / "runs" / "premium_index"
MICRO_DIR = ROOT / "runs" / "microstructure"


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


def load_close_5m(symbol: str) -> pd.Series:
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
    return series.resample("5min", label="right", closed="right").last().dropna()


def premium_signal_1d(symbol: str, entry_z: float = 2.0,
                      zwin: int = 30) -> pd.Series:
    p = PREMIUM_DIR / f"{symbol}_premium.joblib"
    if not p.exists():
        return pd.Series(dtype=float)
    df = joblib.load(p)
    s = df["close"].astype(float).copy()
    s.index = pd.to_datetime(s.index).normalize()
    s = s.sort_index()
    s = s[~s.index.duplicated(keep="last")]
    z = (s - s.rolling(zwin).mean()) / s.rolling(zwin).std()
    sig = pd.Series(0.0, index=z.index)
    sig[z > entry_z] = 1.0
    sig[z < -entry_z] = -1.0
    return sig


def oi_price_signal_1d(symbol: str, entry_z: float = 2.0,
                       zwin: int = 288) -> pd.Series:
    """Compute 5m OI×price joint z signal, then aggregate to daily.
    Daily signal = last non-zero signal within day (most recent extreme)."""
    p = MICRO_DIR / f"{symbol}_full_metrics.joblib"
    if not p.exists():
        return pd.Series(dtype=float)
    m = joblib.load(p)
    if "open_interest" not in m.columns:
        return pd.Series(dtype=float)
    oi = pd.to_numeric(m["open_interest"], errors="coerce")
    oi.index = pd.to_datetime(oi.index)
    oi = oi.replace(0.0, np.nan).dropna().sort_index()
    oi = oi[~oi.index.duplicated(keep="last")]

    close5m = load_close_5m(symbol)
    df = pd.concat([close5m.rename("close"), oi.rename("oi")],
                   axis=1, join="inner").dropna()
    if len(df) < zwin + 50:
        return pd.Series(dtype=float)
    log_ret = np.log(df["close"] / df["close"].shift(1))
    d_oi = df["oi"].pct_change(fill_method=None)
    ret_z = (log_ret - log_ret.rolling(zwin).mean()) / log_ret.rolling(zwin).std()
    oi_z = (d_oi - d_oi.rolling(zwin).mean()) / d_oi.rolling(zwin).std()

    # confirm mode: same-sign extreme → follow price direction
    both_extreme = (ret_z.abs() > entry_z) & (oi_z.abs() > entry_z)
    same_sign = both_extreme & (ret_z * oi_z > 0)
    sig5m = pd.Series(0.0, index=df.index)
    sig5m.loc[same_sign & (ret_z > 0)] = 1.0
    sig5m.loc[same_sign & (ret_z < 0)] = -1.0

    # Resample to daily: take LAST non-zero signal in each day
    sig5m_normalized = sig5m.copy()
    sig5m_normalized.index = sig5m_normalized.index.normalize()
    daily = sig5m_normalized.groupby(sig5m_normalized.index).agg(
        lambda x: x[x != 0].iloc[-1] if (x != 0).any() else 0.0
    )
    return daily


def funding_signal_1d(symbol: str, entry_z: float = 2.5,
                      zwin: int = 30) -> pd.Series:
    """Load funding rate from DB, compute z-score, fade direction."""
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT funding_time, funding_rate
                FROM binance_funding_rate WHERE symbol=:sym
                ORDER BY funding_time
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["funding_time"],
        )
    finally:
        s.close()
    if df.empty:
        return pd.Series(dtype=float)
    fr = df.set_index("funding_time")["funding_rate"].astype(float)
    z = (fr - fr.rolling(zwin).mean()) / fr.rolling(zwin).std()
    sig = pd.Series(0.0, index=z.index)
    # fade reversal direction
    sig[z > entry_z] = -1.0
    sig[z < -entry_z] = 1.0
    # Aggregate 8h to daily: take last signal of day
    sig.index = sig.index.normalize()
    daily = sig.groupby(sig.index).agg(
        lambda x: x[x != 0].iloc[-1] if (x != 0).any() else 0.0
    )
    return daily


def vote_signals(p: float, o: float, f: float, mode: str) -> int:
    sigs = [s for s in [p, o, f] if s != 0]
    if len(sigs) == 0:
        return 0
    pos = sum(1 for s in sigs if s > 0)
    neg = sum(1 for s in sigs if s < 0)
    if mode == "any_majority":
        if len(sigs) == 1:
            return int(sigs[0])
        if pos > neg:
            return 1
        if neg > pos:
            return -1
        return 0
    elif mode == "require_2":
        if pos >= 2:
            return 1
        if neg >= 2:
            return -1
        return 0
    elif mode == "unanimous":
        if pos == 3:
            return 1
        if neg == 3:
            return -1
        return 0
    elif mode == "sum_threshold":
        s = p + o + f
        if abs(s) >= 1.0:  # weighted sum nonzero
            return int(np.sign(s))
        return 0
    else:
        raise ValueError(f"Unknown vote mode {mode}")


def simulate(close: pd.Series, ensemble_sig: pd.Series, *,
             hold_days: int, sl_pct: float, fee_rate: float,
             capital: float, train_frac: float,
             ) -> dict:
    df = pd.concat({"close": close, "sig": ensemble_sig}, axis=1, join="inner").dropna()

    n = len(df)
    if n < 60:
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
            sig = int(test["sig"].iloc[i])
            if sig != 0:
                side = sig
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


def build_ensemble(symbol: str, vote_mode: str,
                   p_z: float, oi_z: float, f_z: float) -> pd.Series:
    p_sig = premium_signal_1d(symbol, entry_z=p_z)
    o_sig = oi_price_signal_1d(symbol, entry_z=oi_z)
    f_sig = funding_signal_1d(symbol, entry_z=f_z)
    log.info("%s signal counts: premium=%d (n=%d), oi_price=%d (n=%d), funding=%d (n=%d)",
             symbol, (p_sig != 0).sum(), len(p_sig),
             (o_sig != 0).sum(), len(o_sig),
             (f_sig != 0).sum(), len(f_sig))
    # Align to common daily index — outer join all signals
    df = pd.concat({"p": p_sig, "o": o_sig, "f": f_sig}, axis=1).fillna(0.0)
    ens = df.apply(lambda r: vote_signals(r["p"], r["o"], r["f"], vote_mode), axis=1)
    return ens.astype(float)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--vote", choices=["any_majority", "require_2", "unanimous", "sum_threshold"],
                   default="any_majority")
    p.add_argument("--premium-z", type=float, default=2.0)
    p.add_argument("--oi-z", type=float, default=2.0)
    p.add_argument("--funding-z", type=float, default=2.5)
    p.add_argument("--hold-days", type=int, default=5)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_{args.vote}_p{args.premium_z}_o{args.oi_z}_f{args.funding_z}_h{args.hold_days}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            close = load_close_1d(sym)
            ens = build_ensemble(sym, args.vote, args.premium_z, args.oi_z, args.funding_z)
            log.info("%s ensemble fires (non-zero): %d / %d days", sym, (ens != 0).sum(), len(ens))
            sim = simulate(
                close, ens,
                hold_days=args.hold_days, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s [%s] alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d S=%d)",
                     sym, args.vote,
                     sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
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
