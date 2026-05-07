#!/usr/bin/env python3
"""Phase R-1 PoC: Taker Buy/Sell Ratio Z-Score paradigm.

Hypothesis: Binance publishes 5m `taker_buy_sell_ratio` (TBS) — the realized
ratio of aggressive taker BUY volume to taker SELL volume. Unlike LSR
(positioning state, which graveyard'd 2026-05-06 as `top_global_lsr_divergence`
22nd paradigm), TBS measures DYNAMIC realized flow at each 5m bar.

When TBS deviates significantly from its rolling 288-bar (24h) baseline,
extreme aggressive flow indicates climax. Two modes tested:
  - `fade` (mean-reversion): TBS_z > +entry → SHORT (buying climax reversal);
                             TBS_z < -entry → LONG (selling capitulation bounce)
  - `follow` (momentum): TBS_z > +entry → LONG (sustained buying pressure);
                         TBS_z < -entry → SHORT (sustained selling pressure)

Distinct from all 5 seeded + 21 graveyard paradigms:
  - `oi_price_decoupling` (seeded, perm 0.000 6.7σ): OI Δ vs price Δ joint z.
    This: realized aggressive flow ratio (different metric, exchange-published)
  - `volume_absorption` (graveyard 2026-05-04): 5m candle body × volume z-score.
    Distinct: candle-body indirect proxy vs direct exchange-published TBS ratio.
    Different metric class, not §3-G family-extension.
  - `top_global_lsr_divergence` (graveyard 2026-05-06): LSR positioning state.
    Distinct: TBS is realized flow ≠ static positioning ratio.
  - All other graveyards: returns/vol moments, cross-section, ML-flatten.

Anti-pattern checks:
  - rare-event §3-A: R-1 sweep entry_z (1.0/1.5/2.0/2.5) — Hurst-trap auto check
  - truncation §3-B: full 2y data, no max-bars
  - in-sample §3-F: rolling z-score real-time, no train-table lookup
  - family-extension §3-G: distinct metric class from volume_absorption (graveyard
    used candle-body proxy, this uses exchange-published flow ratio)
  - multi-symbol §3-E: R-3 perm test required if alpha 10/10

Usage:
  python -m scripts.poc_taker_flow_zscore --symbols SOLUSDT --mode fade
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
log = logging.getLogger("poc_taker_flow_zscore")

PARADIGM = "taker_flow_zscore"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
MICRO_DIR = ROOT / "runs" / "microstructure"


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
    series = df.set_index("ts")["close"].astype(float)
    df_5m = series.resample("5min", label="right", closed="right").last().dropna().to_frame("close")
    return df_5m


def load_tbs_5m(symbol: str) -> pd.DataFrame:
    p = MICRO_DIR / f"{symbol}_full_metrics.joblib"
    if not p.exists():
        raise FileNotFoundError(f"No microstructure joblib for {symbol}: {p}")
    df = joblib.load(p)
    if "taker_buy_sell_ratio" not in df.columns:
        raise ValueError(f"{symbol} joblib missing taker_buy_sell_ratio column")
    out = df[["taker_buy_sell_ratio"]].copy()
    out.columns = ["tbs"]
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out.replace(0.0, np.nan).dropna()
    return out


def simulate(df: pd.DataFrame, *, zwin: int, entry_z: float, hold_bars: int,
             sl_pct: float, fee_rate: float, capital: float, train_frac: float,
             mode: str = "fade",
             ) -> dict:
    """mode: 'fade' (z>entry → short, z<-entry → long, climax reversal)
            'follow' (z>entry → long, z<-entry → short, momentum)."""
    df = df.copy()
    # log-transform to symmetrize heavily right-skewed TBS distribution
    # (raw TBS max 12.7 vs min 0.07; z>2 occurred 4.3% but z<-2 only 0.05% → asymmetric signal)
    df["log_tbs"] = np.log(df["tbs"].clip(lower=1e-6))
    df["tbs_z"] = (df["log_tbs"] - df["log_tbs"].rolling(zwin).mean()) / df["log_tbs"].rolling(zwin).std()
    df = df.dropna(subset=["tbs_z"])

    n = len(df)
    if n < 2000:
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
                    "side": side, "entry_tbs_z": entry_z_val,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                    "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        if not in_pos:
            row = test.iloc[i]
            tz = float(row["tbs_z"])
            if math.isnan(tz):
                equity_curve.append((ts, equity)); continue
            if abs(tz) > entry_z:
                if mode == "fade":
                    side = -1 if tz > 0 else 1   # buying climax → short
                else:  # follow
                    side = 1 if tz > 0 else -1
                if side > 0:
                    n_long += 1
                else:
                    n_short += 1
                in_pos = True
                entry_px = px; entry_ts = str(ts); entry_z_val = tz
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
    p.add_argument("--zwin", type=int, default=288)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--mode", choices=["fade", "follow"], default="fade")
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or (
        f"poc_{args.mode}_zw{args.zwin}_ez{args.entry_z}_h{args.hold_bars}"
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for sym in args.symbols:
        try:
            close_df = load_ohlcv_5m(sym)
            tbs_df = load_tbs_5m(sym)
            joined = pd.concat([close_df, tbs_df], axis=1, join="inner").dropna()
            log.info("%s joined: %d bars (%s → %s)",
                     sym, len(joined), joined.index[0], joined.index[-1])
            sim = simulate(
                joined, zwin=args.zwin, entry_z=args.entry_z,
                hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac, mode=args.mode,
            )
            sim["symbol"] = sym
            rows.append(sim)
            log.info("%s [%s] alpha=%.2f sharpe=%.2f mdd=%.1f wr=%.1f pf=%s "
                     "trades=%d (L=%d S=%d)",
                     sym, args.mode, sim.get("alpha_pct", 0), sim.get("sharpe_ann", 0),
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
