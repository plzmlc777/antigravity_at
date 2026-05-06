#!/usr/bin/env python3
"""Phase R-1/R-2 PoC: Multi-Timeframe Alignment Consensus paradigm.

Hypothesis: when 5m/1h/4h timeframe momentum signs all agree (|alignment_score|
= 3 or 2), the directional consensus is strong enough that the next M bars
continue in that direction more often than revert.

alignment_score = sign(R_5m) + sign(R_1h) + sign(R_4h)
  = +3 → all 3 timeframes bullish → momentum continuation LONG
  = -3 → all bearish → SHORT
  = ±2 → 2/3 timeframes agree (one diverging)
  =  0 → fully diverging — no signal

Distinct from prior paradigms (19 graveyard + 4 seeded):
  - autocorr_regime (seeded LINK/UNI): single-TF intra-symbol lag-1
  - cross_symbol_lead_lag (seeded DOGE): cross-symbol BTC leader spillover
  - All funding paradigms: orthogonal data domain (8h funding rate)
  - **mtf_alignment_consensus**: cross-TIMEFRAME (within same symbol) sign
    consensus — NEW dimension not yet explored

Pipeline:
  1. Load 1m → 5m, log returns (5m units).
  2. Compute rolling sum of log returns over 1 / 12 / 48 5m-bars (5m, 1h, 4h).
  3. alignment_score = sign(R_5m) + sign(R_1h) + sign(R_4h) ∈ {-3..+3}
  4. Entry per |min_align|:
     |alignment| ≥ MIN_ALIGN → enter in sign(alignment)
  5. Exit at HOLD bars or SL.

Anti-pattern checks:
  - rare-event §3-A: |align|=3 sparse — threshold sweep mandatory
  - in-sample §3-F: real-time rolling sums, no train table
  - family-extension §3-G: cross-TF different from intra-TF lag-1 autocorr
  - data-coverage §3-B: 1y OHLCV all symbols ✅
  - multi-symbol consistency §3-E: R-3 perm test mandatory

Usage:
  python -m scripts.poc_mtf_alignment_consensus --symbols SOLUSDT
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
log = logging.getLogger("poc_mtf_alignment_consensus")

PARADIGM = "mtf_alignment_consensus"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlcv_5m(symbol: str) -> pd.DataFrame:
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
    df = df.set_index("ts")["close"].astype(float)
    df_5m = df.resample("5min", label="right", closed="right").last().dropna().to_frame("close")
    return df_5m


def simulate_mtf_alignment(df: pd.DataFrame, *, min_align: int, hold_bars: int,
                            sl_pct: float, fee_rate: float, capital: float,
                            train_frac: float, direction: str = "follow",
                            ) -> dict:
    """direction: 'follow' (continuation) or 'fade' (reversal)"""
    df = df.copy()
    df["ret5"] = np.log(df["close"] / df["close"].shift(1))
    df["R_5m"] = df["ret5"]                                    # 1 bar
    df["R_1h"] = df["ret5"].rolling(12).sum()                  # 12 5m-bars
    df["R_4h"] = df["ret5"].rolling(48).sum()                  # 48 5m-bars
    df["sign5"] = np.sign(df["R_5m"])
    df["sign1h"] = np.sign(df["R_1h"])
    df["sign4h"] = np.sign(df["R_4h"])
    df["align"] = df["sign5"].fillna(0) + df["sign1h"].fillna(0) + df["sign4h"].fillna(0)
    df = df.dropna(subset=["R_4h"])

    n = len(df)
    if n < 1000:
        return {"error": f"too few bars ({n})", "n_trades": 0}
    split = int(n * train_frac)
    test = df.iloc[split:].copy()

    equity = capital
    equity_curve = [(test.index[0], equity)]
    trades: list[dict] = []
    in_pos = False; side = 0; entry_px = 0.0; bars_held = 0
    entry_ts = ""; target_hold = 0; entry_align = 0

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
                    "side": side, "entry_align": entry_align,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            align = int(row["align"]) if not math.isnan(row["align"]) else 0
            if abs(align) >= min_align:
                if direction == "follow":
                    side = 1 if align > 0 else -1
                else:  # fade
                    side = -1 if align > 0 else 1
                in_pos = True
                entry_px = cpx; entry_ts = str(ts); entry_align = align
                bars_held = 0; target_hold = hold_bars
            else:
                equity_curve.append((ts, equity)); continue
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

    align_dist = test["align"].value_counts().to_dict()

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
        "align_dist": {int(k): int(v) for k, v in align_dist.items()},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--min-align", type=int, default=3)  # |align|>=3
    p.add_argument("--hold-bars", type=int, default=12)  # 1h
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--direction", choices=["follow", "fade"], default="follow")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_align{args.min_align}_h{args.hold_bars}_{args.direction}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            sim = simulate_mtf_alignment(
                df, min_align=args.min_align, hold_bars=args.hold_bars,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital, train_frac=args.train_frac,
                direction=args.direction,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s — alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d align_dist=%s",
                     sym, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
                     sim.get("max_dd_pct", 0), sim.get("win_rate_pct", 0),
                     sim.get("profit_factor", 0), sim["n_trades"],
                     sim.get("align_dist", {}))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    df_out = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor", "oos_days"]
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
