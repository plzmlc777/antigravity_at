#!/usr/bin/env python3
"""Phase R-1 PoC: Wick Reversal 5m paradigm.

Hypothesis: A 5m candle with extreme one-sided wick dominance (e.g. lower
wick > 60% of range, body small) coincides with a liquidation cascade —
price plunged, stops cleared, then the market bid it back within the bar.
The next K bars are more likely to follow the wick-rejection direction
than to revert.

Distinct from prior 49 paradigms (no wick/shape paradigm yet):
  - vol_regime_breakout (graveyard): close-to-close volatility regime
  - garman_klass_vol_premium (graveyard): GK estimator on PREMIUM, not price
  - oi_price_decoupling (seeded): OI flow + price return — uses close return
  - All return/funding/premium z paradigms: use close-to-close, ignore wicks
  - **NEW dimension**: intra-bar high/low excursion shape

Entry rule (per symbol, 5m bars):
  1. body = |close - open|, range = high - low
  2. lower_wick = min(open, close) - low
     upper_wick = high - max(open, close)
  3. lower_wick_frac = lower_wick / range  (0..1)
     upper_wick_frac = upper_wick / range  (0..1)
  4. If range > 0 AND volume nonzero:
     - lower_wick_frac > wick_thresh AND prior_n_bars price drop > drop_thresh
       → liquidation-proxy LONG (shorts cleared, reversal up)
     - upper_wick_frac > wick_thresh AND prior_n_bars price rally > rally_thresh
       → liquidation-proxy SHORT (longs cleared, reversal down)
  5. Hold hold_bars or stop on SL.

Anti-pattern checks:
  - rare-event §3-A: R-1 sweep wick_thresh ∈ {0.5, 0.6, 0.7}.
  - truncation §3-B: full data, no max-bars.
  - in-sample §3-F: real-time, no train-table.
  - family-extension §3-G: no prior wick paradigm (vol_regime used C2C, not wicks).
  - multi-symbol §3-E: R-3 perm test.
  - §3-J two-seeded-fade-joint: this is single-domain (price OHLC), no joint.

Usage:
  python -m scripts.poc_wick_reversal --symbols SOLUSDT
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
log = logging.getLogger("poc_wick_reversal")

PARADIGM = "wick_reversal"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlc_5m(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp AS ts, open, high, low, close
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
    df = df.set_index("ts")
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    agg = df.resample("5min", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    return agg


def simulate(df: pd.DataFrame, *, wick_thresh: float, prior_lookback: int,
             prior_move_pct: float, hold_bars: int, sl_pct: float,
             fee_rate: float, capital: float, train_frac: float,
             ) -> dict:
    df = df.copy()
    rng = (df["high"] - df["low"]).replace(0.0, np.nan)
    body_top = df[["open", "close"]].max(axis=1)
    body_bot = df[["open", "close"]].min(axis=1)
    df["lower_wick_frac"] = (body_bot - df["low"]) / rng
    df["upper_wick_frac"] = (df["high"] - body_top) / rng
    df["prior_ret"] = df["close"].pct_change(prior_lookback)
    df = df.dropna(subset=["lower_wick_frac", "upper_wick_frac", "prior_ret"])

    n = len(df)
    if n < 2000:
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
            lwf = float(row["lower_wick_frac"])
            uwf = float(row["upper_wick_frac"])
            pr = float(row["prior_ret"])
            if math.isnan(lwf) or math.isnan(uwf) or math.isnan(pr):
                equity_curve.append((ts, equity)); continue
            # Long-side liquidation reversal: lower wick dominant + prior drop
            if lwf > wick_thresh and pr < -prior_move_pct:
                side = 1; n_long += 1
                in_pos = True
                entry_px = px; entry_ts = str(ts)
                bars_held = 0; target_hold = hold_bars
            # Short-side liquidation reversal: upper wick dominant + prior rally
            elif uwf > wick_thresh and pr > prior_move_pct:
                side = -1; n_short += 1
                in_pos = True
                entry_px = px; entry_ts = str(ts)
                bars_held = 0; target_hold = hold_bars
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
    p.add_argument("--wick-thresh", type=float, default=0.6)
    p.add_argument("--prior-lookback", type=int, default=12)   # 1h prior
    p.add_argument("--prior-move-pct", type=float, default=0.02)
    p.add_argument("--hold-bars", type=int, default=12)         # 1h hold
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_wt{args.wick_thresh}_pl{args.prior_lookback}"
        f"_pm{args.prior_move_pct}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlc_5m(sym)
            log.info("%s 5m frame: %d bars (%s → %s)",
                     sym, len(df), df.index[0], df.index[-1])
            sim = simulate(
                df, wick_thresh=args.wick_thresh,
                prior_lookback=args.prior_lookback,
                prior_move_pct=args.prior_move_pct,
                hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
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
