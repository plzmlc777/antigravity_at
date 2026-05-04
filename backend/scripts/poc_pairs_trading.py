#!/usr/bin/env python3
"""Phase R-1 PoC: Pairs trading paradigm.

Hypothesis: every paper-pool spec extracts directional alpha from a single
symbol's microstructure. A pair-spread strategy creates a brand-new instrument
(log P_a - β log P_b) whose mean-reverting residual has *no overlap* with any
single-symbol spec — strict orthogonality, market-neutral by construction.

Pipeline:
  1. Load daily OHLCV for 14 Binance symbols (server-side resample from 1m DB).
  2. On TRAIN window only:
       - Engle-Granger cointegration test on each of 91 pairs (14C2).
       - Keep pairs with p < COINT_P_CUTOFF and |β| in [0.1, 10] (sane hedge).
  3. On TEST window:
       - For each surviving pair compute spread = log(P_a) - β * log(P_b)
         (β is FIXED from train OLS — no look-ahead).
       - Rolling z-score over LOOKBACK days.
       - Entry: |z| crosses ENTRY_Z → long spread (long A, short B) or vice versa.
       - Exit: z returns to 0, OR max_hold timeout, OR SL.
  4. Per-pair simulation, then equal-weight aggregate across surviving pairs.

Usage:
  python -m scripts.poc_pairs_trading
  python -m scripts.poc_pairs_trading --coint-p 0.05 --lookback 30 --entry-z 2.0
"""
from __future__ import annotations

import argparse
import itertools
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
log = logging.getLogger("poc_pairs_trading")

PARADIGM = "pairs_trading"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

DEFAULT_SYMBOLS = [
    "SOLUSDT", "HBARUSDT", "AXSUSDT", "DOGEUSDT", "UNIUSDT",
    "PYTHUSDT", "TONUSDT", "ICPUSDT", "ETCUSDT", "JUPUSDT",
    "COMPUSDT", "WLDUSDT", "LDOUSDT", "1000LUNCUSDT",
]


def load_daily_close(symbols: list[str]) -> pd.DataFrame:
    """Wide-format daily close DF (rows=date, cols=symbol)."""
    s = SessionLocal()
    try:
        all_dfs = {}
        for sym in symbols:
            df = pd.read_sql(
                text("""
                    SELECT
                      DATE(timestamp) AS date,
                      (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
                      COUNT(*) AS bar_count
                    FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                    GROUP BY DATE(timestamp)
                    ORDER BY DATE(timestamp)
                """),
                s.connection(),
                params={"sym": sym},
                parse_dates=["date"],
            )
            df = df[df["bar_count"] >= 1000]
            all_dfs[sym] = df.set_index("date")["close"].astype(float)
        wide = pd.DataFrame(all_dfs).sort_index()
        log.info("Daily close panel: %d dates × %d symbols (NaN per col mean=%.1f)",
                 len(wide), len(wide.columns), wide.isna().sum().mean())
        return wide
    finally:
        s.close()


def find_cointegrated_pairs(close_train: pd.DataFrame, *, p_cutoff: float,
                            beta_min: float, beta_max: float
                            ) -> list[tuple[str, str, float, float]]:
    """Engle-Granger test on all pairs. Return [(s1, s2, pval, beta), ...]."""
    from statsmodels.tsa.stattools import coint

    log_close = np.log(close_train)
    symbols = list(log_close.columns)
    pairs = []
    n_tested = 0

    for s1, s2 in itertools.combinations(symbols, 2):
        x = log_close[s1].dropna()
        y = log_close[s2].dropna()
        common = x.index.intersection(y.index)
        if len(common) < 200:
            continue
        x_c = x.loc[common].values
        y_c = y.loc[common].values
        try:
            score, pval, _ = coint(x_c, y_c)
        except Exception:
            continue
        n_tested += 1
        if pval >= p_cutoff:
            continue

        # OLS hedge ratio: x = beta * y + alpha
        beta = float(np.cov(x_c, y_c, ddof=1)[0, 1] / np.var(y_c, ddof=1))
        if not (beta_min <= abs(beta) <= beta_max):
            continue
        pairs.append((s1, s2, float(pval), beta))

    pairs.sort(key=lambda x: x[2])
    log.info("Cointegration: %d/%d pairs passed (p<%.2f, |β|∈[%.1f,%.1f])",
             len(pairs), n_tested, p_cutoff, beta_min, beta_max)
    return pairs


def trade_pair(close_a: pd.Series, close_b: pd.Series, beta: float, *,
               lookback: int, entry_z: float, exit_z: float, max_hold: int,
               sl_pct: float, fee_rate: float, capital: float) -> dict:
    """Trade a pair on its full series; metrics computed on the trades produced."""
    common = close_a.index.intersection(close_b.index)
    a = close_a.loc[common].values
    b = close_b.loc[common].values
    ts = common

    log_a = np.log(a); log_b = np.log(b)
    spread = log_a - beta * log_b
    spread_s = pd.Series(spread, index=ts)
    mean = spread_s.rolling(lookback).mean().values
    std = spread_s.rolling(lookback).std().values
    z = (spread - mean) / std

    equity = capital
    equity_curve = [(ts[0], equity)]
    trades: list[dict] = []
    in_pos = False
    side = 0      # +1 = long spread (long A short B); -1 = short spread
    entry_a = entry_b = 0.0
    bars_held = 0
    entry_ts = ""

    prev_z = z[0] if not math.isnan(z[0]) else 0.0
    for i in range(1, len(ts)):
        ai = a[i]; bi = b[i]; zi = z[i]; t = ts[i]

        if in_pos:
            bars_held += 1
            exit_reason = None
            if side == 1:
                pnl_a = (ai - entry_a) / entry_a
                pnl_b = (bi - entry_b) / entry_b
                gross = pnl_a - beta * pnl_b
                if not math.isnan(zi) and zi >= -exit_z:
                    exit_reason = "mean"
                elif gross < -sl_pct:
                    exit_reason = "sl"
                elif bars_held >= max_hold:
                    exit_reason = "time"
            else:
                pnl_a = (ai - entry_a) / entry_a
                pnl_b = (bi - entry_b) / entry_b
                gross = -pnl_a + beta * pnl_b
                if not math.isnan(zi) and zi <= exit_z:
                    exit_reason = "mean"
                elif gross < -sl_pct:
                    exit_reason = "sl"
                elif bars_held >= max_hold:
                    exit_reason = "time"

            if exit_reason:
                # 4 fees: open A + open B + close A + close B
                ret_pct = gross - 4 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(t),
                    "side": side, "return_pct": ret_pct,
                    "exit_reason": exit_reason, "bars_held": bars_held,
                })
                in_pos = False; side = 0; bars_held = 0

        elif not in_pos and not math.isnan(zi):
            # cross outward beyond ±entry_z
            if prev_z > -entry_z and zi <= -entry_z:
                in_pos = True; side = 1
                entry_a = ai; entry_b = bi; entry_ts = str(t); bars_held = 0
            elif prev_z < entry_z and zi >= entry_z:
                in_pos = True; side = -1
                entry_a = ai; entry_b = bi; entry_ts = str(t); bars_held = 0

        prev_z = zi if not math.isnan(zi) else prev_z
        equity_curve.append((t, equity))

    total_return_pct = (equity / capital) - 1
    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    if trades:
        rs = np.array([t["return_pct"] for t in trades])
        mu = rs.mean(); sd = rs.std(ddof=1) if len(rs) > 1 else 0.0
        oos_days = (ts[-1] - ts[0]).days
        trades_per_year = len(trades) / oos_days * 365.0 if oos_days > 0 else 0
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

    exit_reasons: dict[str, int] = {}
    for t in trades:
        exit_reasons[t["exit_reason"]] = exit_reasons.get(t["exit_reason"], 0) + 1

    return {
        "n_trades": len(trades),
        "total_return_pct": round(total_return_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "exit_reasons": exit_reasons,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--coint-p", type=float, default=0.05)
    p.add_argument("--beta-min", type=float, default=0.1)
    p.add_argument("--beta-max", type=float, default=10.0)
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--exit-z", type=float, default=0.0)
    p.add_argument("--max-hold", type=int, default=20)
    p.add_argument("--sl-pct", type=float, default=0.10)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    tag = args.tag or f"all14_p{args.coint_p}_lb{args.lookback}_z{args.entry_z}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    close = load_daily_close(args.symbols)
    n_dates = len(close)
    split = int(n_dates * args.train_frac)
    train = close.iloc[:split]
    test = close.iloc[split:]
    log.info("Train: %d days (%s → %s) | Test: %d days (%s → %s)",
             len(train), train.index[0], train.index[-1],
             len(test), test.index[0], test.index[-1])

    pairs = find_cointegrated_pairs(
        train, p_cutoff=args.coint_p,
        beta_min=args.beta_min, beta_max=args.beta_max,
    )
    if not pairs:
        log.warning("No cointegrated pairs found.")
        return 1

    log.info("Top pairs: %s",
             [(s1, s2, round(p, 4), round(b, 2)) for s1, s2, p, b in pairs[:5]])

    rows = []
    for s1, s2, pval, beta in pairs:
        try:
            sim = trade_pair(
                close[s1], close[s2], beta,
                lookback=args.lookback, entry_z=args.entry_z,
                exit_z=args.exit_z, max_hold=args.max_hold,
                sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                capital=args.capital,
            )
            sim.update({"pair": f"{s1}/{s2}", "coint_p": round(pval, 5),
                        "beta": round(beta, 3)})
            rows.append(sim)
            log.info("%s/%s — return=%.2f%% sharpe=%.2f mdd=%.1f wr=%.1f trades=%d",
                     s1, s2, sim["total_return_pct"], sim["sharpe_ann"],
                     sim["max_dd_pct"], sim["win_rate_pct"], sim["n_trades"])
        except Exception as exc:
            log.exception("Failed %s/%s: %s", s1, s2, exc)

    df_out = pd.DataFrame(rows)
    cols = ["pair", "coint_p", "beta", "n_trades", "total_return_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor"]
    df_out = df_out.reindex(columns=[c for c in cols if c in df_out.columns])
    out_csv = OUT_DIR / f"{tag}__per_pair.csv"
    df_out.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    # Aggregate
    total_ret = df_out["total_return_pct"].astype(float)
    sharpe = df_out["sharpe_ann"].astype(float)
    pf_numeric = df_out["profit_factor"].apply(
        lambda x: float(x) if x != "inf" else None).dropna()

    agg = {
        "spec_name": tag,
        "n_pairs": len(rows),
        "n_trades_total": int(df_out["n_trades"].sum()),
        "trades_per_pair_mean": round(float(df_out["n_trades"].mean()), 1),
        "total_return_mean": round(float(total_ret.mean()), 2),
        "total_return_median": round(float(total_ret.median()), 2),
        "total_return_pos_count": int((total_ret > 0).sum()),
        "sharpe_mean": round(float(sharpe.mean()), 3),
        "sharpe_pos_count": int((sharpe > 0).sum()),
        "mdd_mean": round(float(df_out["max_dd_pct"].astype(float).mean()), 2),
        "wr_mean": round(float(df_out["win_rate_pct"].astype(float).mean()), 2),
        "pf_mean_finite": round(float(pf_numeric.mean()), 3) if len(pf_numeric) else None,
        "best_pair": df_out.iloc[total_ret.idxmax()]["pair"] if len(df_out) else None,
        "best_pair_return": round(float(total_ret.max()), 2) if len(df_out) else None,
        "best_pair_sharpe": round(float(sharpe.max()), 3) if len(df_out) else None,
    }

    out_meta = {
        "paradigm": PARADIGM, "phase": "R-1_PoC", "spec_name": tag,
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "config": vars(args),
        "aggregate": agg,
        "per_pair": rows,
    }
    out_meta_path = OUT_DIR / f"{tag}__metrics.json"
    out_meta_path.write_text(json.dumps(out_meta, indent=2, default=str))

    print("\n=== Aggregate ===")
    print(json.dumps(agg, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
