#!/usr/bin/env python3
"""Phase R-1 PoC: OI-Funding Correlation Regime paradigm (8h).

Hypothesis: When 8h-aggregated d_OI z-score and funding-rate z-score have a
positive rolling correlation regime over the past N funding periods, the
symbol is in a "positioning-flow + carry-cost coupled" regime — extreme
joint signals are trustworthy. When recent correlation is weak/negative, the
two signals are decoupled and joint extremes are just noise.

We work at 8h granularity (natural funding tick) to avoid forward-fill
correlation artifacts that destroy signal at 5m.

§3-G/§3-A risk profile:
  - Combines TWO seeded-strong domains (OI Δ in oi_price_decoupling 6.7σ AVAX,
    funding rate in funding_carry seeded 3 syms). NOT premium domain.
  - oi_premium_5m_correlation_regime (1d) was graveyard — but funding instead
    of premium + corr REGIME as filter dimension is new.
  - joint_3signal_ensemble was POSITIVE/SKIP — distinct because we use rolling
    CORR REGIME as third dimension (temporal stability of relationship), not
    a third static signal.

Pipeline (per-symbol, 8h granularity):
  1. Load 1m close → 5m close → resample to 8h-aligned bars at funding boundary.
  2. Load 5m OI (microstructure joblib) → snapshot at each funding boundary.
  3. Load 8h funding from binance_funding_rate.
  4. At each 8h bar: d_oi_pct = OI[t] / OI[t−1] − 1; funding[t] from DB.
  5. oi_z = rolling N-period z of d_oi; fund_z = rolling N-period z of funding.
  6. corr_regime = rolling M-period Pearson corr of (d_oi, funding) raw series.
  7. Entry: |oi_z| > entry_z AND |fund_z| > entry_z_fund
     AND sign(oi_z) == sign(fund_z) AND corr_regime > regime_thresh
  8. Modes:
     - 'follow_long_pos': aligned + → LONG, aligned − → SHORT (regime momentum)
     - 'fade_long_pos':   aligned + → SHORT, aligned − → LONG (extreme unwind)

Anti-pattern checks:
  - rare-event §3-A: R-1 sweep multiple entry thresholds.
  - truncation §3-B: full data, no max-bars.
  - in-sample §3-F: rolling z-score realtime, train/test split.
  - family-extension §3-G: corr_regime as REGIME dimension is novel (vs voting).
  - multi-symbol §3-E: R-3 perm test.

Usage:
  python -m scripts.poc_oi_funding_corr_regime --symbols SOLUSDT
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
log = logging.getLogger("poc_oi_funding_corr_regime")

PARADIGM = "oi_funding_corr_regime"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
MICRO_DIR = ROOT / "runs" / "microstructure"


def load_close_5m(symbol: str) -> pd.DataFrame:
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
    df_5m = series.resample("5min", label="right", closed="right").last().dropna().to_frame("close")
    return df_5m


def load_oi_5m(symbol: str) -> pd.DataFrame:
    p = MICRO_DIR / f"{symbol}_full_metrics.joblib"
    if not p.exists():
        raise FileNotFoundError(f"No microstructure joblib for {symbol}: {p}")
    df = joblib.load(p)
    if "open_interest" not in df.columns:
        raise ValueError(f"{symbol} joblib missing open_interest column")
    out = df[["open_interest"]].copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out


def load_funding_8h(symbol: str) -> pd.DataFrame:
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
        raise ValueError(f"No funding rate data for {symbol}")
    df["funding_rate"] = df["funding_rate"].astype(float)
    return df.set_index("ts").sort_index()


def build_8h_frame(close_5m: pd.DataFrame, oi_5m: pd.DataFrame, fund_8h: pd.DataFrame) -> pd.DataFrame:
    """Resample to 8h grid aligned with funding timestamps.

    Funding ticks are at 00:00/08:00/16:00 UTC. We snapshot OI and close at
    the bar immediately preceding each funding tick (last 5m bar before the
    funding window closes).
    """
    fund_idx = fund_8h.index
    close_re = close_5m["close"].reindex(fund_idx, method="ffill")
    oi_re = oi_5m["open_interest"].reindex(fund_idx, method="ffill")
    out = pd.DataFrame({
        "close": close_re,
        "open_interest": oi_re,
        "funding_rate": fund_8h["funding_rate"],
    }).dropna()
    return out


def simulate(df: pd.DataFrame, *, zwin: int, corr_win: int,
             entry_z: float, entry_z_fund: float, regime_thresh: float,
             hold_periods: int, sl_pct: float, fee_rate: float, capital: float,
             train_frac: float, mode: str = "follow_long_pos",
             ) -> dict:
    """mode:
      'follow_long_pos': aligned + → LONG, aligned − → SHORT
      'fade_long_pos':   aligned + → SHORT, aligned − → LONG
    All series at 8h granularity.
    """
    df = df.copy()
    df["d_oi"] = df["open_interest"].pct_change()
    df["oi_z"] = (df["d_oi"] - df["d_oi"].rolling(zwin).mean()) / df["d_oi"].rolling(zwin).std()
    df["fund_z"] = (df["funding_rate"] - df["funding_rate"].rolling(zwin).mean()) / df["funding_rate"].rolling(zwin).std()
    df["corr_regime"] = df["d_oi"].rolling(corr_win).corr(df["funding_rate"])
    df = df.dropna(subset=["oi_z", "fund_z", "corr_regime"])

    n = len(df)
    if n < 200:
        return {"error": f"too few periods ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; target_hold = 0
    n_pos = 0; n_neg = 0  # aligned positive / aligned negative entries

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
                    "side": side, "return_pct": ret_pct,
                    "exit_reason": exit_reason, "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            oz = float(row["oi_z"]); fz = float(row["fund_z"])
            cr = float(row["corr_regime"])
            if math.isnan(oz) or math.isnan(fz) or math.isnan(cr):
                equity_curve.append((ts, equity)); continue
            in_high_regime = cr > regime_thresh
            if (in_high_regime and abs(oz) > entry_z and abs(fz) > entry_z_fund
                    and (oz * fz > 0)):
                aligned_sign = 1 if oz > 0 else -1
                if mode == "follow_long_pos":
                    side = aligned_sign
                elif mode == "fade_long_pos":
                    side = -aligned_sign
                if aligned_sign > 0:
                    n_pos += 1
                else:
                    n_neg += 1
                in_pos = True
                entry_px = px; entry_ts = str(ts)
                bars_held = 0; target_hold = hold_periods
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
        "n_aligned_pos": n_pos,
        "n_aligned_neg": n_neg,
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
    p.add_argument("--zwin", type=int, default=30)             # 30 funding periods = 10 days
    p.add_argument("--corr-win", type=int, default=30)         # 30 funding periods corr window
    p.add_argument("--entry-z", type=float, default=1.5)
    p.add_argument("--entry-z-fund", type=float, default=1.0)
    p.add_argument("--regime-thresh", type=float, default=0.2)
    p.add_argument("--hold-periods", type=int, default=3)      # 3 funding periods = 24h
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--mode", choices=["follow_long_pos", "fade_long_pos"],
                   default="follow_long_pos")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_ez{args.entry_z}_efz{args.entry_z_fund}"
        f"_cr{args.regime_thresh}_h{args.hold_periods}_{args.mode}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            close_df = load_close_5m(sym)
            oi_df = load_oi_5m(sym)
            fund_df = load_funding_8h(sym)
            joined = build_8h_frame(close_df, oi_df, fund_df)
            log.info("%s 8h frame: %d periods (%s → %s)",
                     sym, len(joined), joined.index[0], joined.index[-1])
            sim = simulate(
                joined, zwin=args.zwin, corr_win=args.corr_win,
                entry_z=args.entry_z, entry_z_fund=args.entry_z_fund,
                regime_thresh=args.regime_thresh,
                hold_periods=args.hold_periods, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, mode=args.mode,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (pos=%d neg=%d)",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("n_aligned_pos", 0), sim.get("n_aligned_neg", 0))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "n_aligned_pos", "n_aligned_neg",
            "alpha_pct", "total_return_pct", "buy_hold_pct", "sharpe_ann",
            "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days"]
    df_out = df_out.reindex(columns=[c for c in cols if c in df_out.columns])
    out_csv = OUT_DIR / f"{tag}__per_symbol.csv"
    df_out.to_csv(out_csv, index=False)

    if len(rows) > 0 and "alpha_pct" in df_out.columns:
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
