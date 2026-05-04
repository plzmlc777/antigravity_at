#!/usr/bin/env python3
"""Phase R-1 PoC: AI-native raw 1m paradigm.

Hypothesis: a model trained on raw 1m OHLCV windows (no engineered features)
contains alpha that is orthogonal to current paper-pool (source-aggregation)
strategies.

Pipeline:
  1. Load 1m OHLCV from DB.
  2. Build sliding window features:
       - log_return_t-i (i=1..LOOKBACK)
       - hl_range_t-i
       - log_volume_t-i
     (total = 3 * LOOKBACK columns; no engineered indicators)
  3. Target: next FWD-bar cumulative log return.
  4. lgbm regressor on first 50% (train), predict last 50% (test/OOS).
  5. Simulation: long if pred > entry_threshold, short if < -entry_threshold,
     hold MAX_HOLD bars, sl/tp bounded.
  6. Compute alpha (vs Buy&Hold), sharpe (annualized per-trade), MDD, WR, PF.
  7. Emit metrics JSON to research_track/{paradigm}/poc__{symbol}__metrics.json.

Usage:
  python -m scripts.poc_ai_native_raw_1m --symbol SOLUSDT
  python -m scripts.poc_ai_native_raw_1m --symbol SOLUSDT --lookback 60 --fwd 10
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
log = logging.getLogger("poc_ai_native_raw_1m")


PARADIGM = "ai_native_raw_1m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM


def load_ohlcv_1m(symbol: str) -> pd.DataFrame:
    s = SessionLocal()
    try:
        df = pd.read_sql(
            text("""
                SELECT timestamp, open, high, low, close, volume
                FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                ORDER BY timestamp
            """),
            s.connection(),
            params={"sym": symbol},
            parse_dates=["timestamp"],
        )
    finally:
        s.close()
    df = df.set_index("timestamp").astype(float)
    log.info("Loaded %s: %d 1m bars (%s → %s)",
             symbol, len(df), df.index[0], df.index[-1])
    return df


def build_features(ohlcv: pd.DataFrame, lookback: int, fwd: int
                   ) -> tuple[pd.DataFrame, pd.Series]:
    """Build raw windowed features + forward-return target."""
    log_close = np.log(ohlcv["close"].values)
    log_ret = np.diff(log_close, prepend=log_close[0])
    hl_range = (ohlcv["high"] - ohlcv["low"]).values / np.maximum(ohlcv["close"].values, 1e-9)
    log_vol = np.log(np.maximum(ohlcv["volume"].values, 1e-9))
    log_vol = (log_vol - log_vol.mean()) / max(log_vol.std(), 1e-9)

    n = len(ohlcv)
    feat_cols = {}
    for i in range(1, lookback + 1):
        feat_cols[f"r_{i}"] = pd.Series(log_ret).shift(i).values
        feat_cols[f"hl_{i}"] = pd.Series(hl_range).shift(i).values
        feat_cols[f"v_{i}"] = pd.Series(log_vol).shift(i).values

    X = pd.DataFrame(feat_cols, index=ohlcv.index)
    fwd_logret = pd.Series(log_close).shift(-fwd).values - log_close
    y = pd.Series(fwd_logret, index=ohlcv.index, name="y")

    valid = X.dropna().index.intersection(y.dropna().index)
    X = X.loc[valid]
    y = y.loc[valid]
    log.info("Built features: X=%s, y=%s (lookback=%d, fwd=%d)",
             X.shape, y.shape, lookback, fwd)
    return X, y


def train_predict(X: pd.DataFrame, y: pd.Series, train_frac: float
                  ) -> tuple[pd.Series, dict]:
    import lightgbm as lgb
    from scipy.stats import spearmanr

    n = len(X)
    split = int(n * train_frac)
    X_tr, X_te = X.iloc[:split], X.iloc[split:]
    y_tr, y_te = y.iloc[:split], y.iloc[split:]

    log.info("Training lgbm: train=%d test=%d", len(X_tr), len(X_te))
    model = lgb.LGBMRegressor(
        n_estimators=300,
        num_leaves=31,
        learning_rate=0.05,
        min_child_samples=200,
        feature_fraction=0.6,
        bagging_fraction=0.8,
        bagging_freq=5,
        reg_alpha=0.1,
        reg_lambda=0.1,
        n_jobs=-1,
        verbose=-1,
    )
    model.fit(X_tr, y_tr)
    preds = pd.Series(model.predict(X_te), index=X_te.index, name="pred")

    importance = pd.Series(model.feature_importances_, index=X.columns
                           ).sort_values(ascending=False).head(20).to_dict()

    # Information Coefficient diagnostics — answers "does prediction
    # contain alpha-bearing signal at all?"
    ic_pearson = float(np.corrcoef(preds.values, y_te.values)[0, 1])
    rank_corr, rank_p = spearmanr(preds.values, y_te.values)
    rank_ic = float(rank_corr); rank_ic_p = float(rank_p)

    # Decile breakdown
    df_d = pd.DataFrame({"pred": preds.values, "y": y_te.values})
    df_d["bucket"] = pd.qcut(df_d["pred"], 10, labels=False, duplicates="drop")
    decile_avg_y = df_d.groupby("bucket")["y"].mean().to_dict()
    top_minus_bottom = float(decile_avg_y.get(9, 0) - decile_avg_y.get(0, 0))

    return preds, {
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "test_start": str(X_te.index[0]),
        "test_end": str(X_te.index[-1]),
        "ic_pearson": round(ic_pearson, 5),
        "rank_ic": round(rank_ic, 5),
        "rank_ic_p": round(rank_ic_p, 5),
        "decile_avg_y": {str(k): round(v, 6) for k, v in decile_avg_y.items()},
        "top_minus_bottom_decile_y": round(top_minus_bottom, 6),
        "pred_mean": round(float(preds.mean()), 6),
        "pred_std": round(float(preds.std()), 6),
        "pred_quantiles": {
            "q01": round(float(preds.quantile(0.01)), 6),
            "q10": round(float(preds.quantile(0.10)), 6),
            "q50": round(float(preds.quantile(0.50)), 6),
            "q90": round(float(preds.quantile(0.90)), 6),
            "q99": round(float(preds.quantile(0.99)), 6),
        },
        "top20_features": importance,
    }


def simulate(ohlcv: pd.DataFrame, preds: pd.Series, *,
             entry_threshold: float, sl_pct: float, tp_pct: float,
             max_hold_bars: int, fee_rate: float, capital: float
             ) -> dict:
    """Run long/short threshold simulation, mimicking LongShortThresholdPolicy."""
    bars = ohlcv.loc[preds.index]
    closes = bars["close"].values
    highs = bars["high"].values
    lows = bars["low"].values
    timestamps = bars.index

    equity = capital
    equity_curve = [(timestamps[0], equity)]
    trades = []
    in_pos = False
    side = 0  # +1 long, -1 short
    entry_px = sl_px = tp_px = 0.0
    bars_held = 0
    qty = 0.0

    for i in range(len(preds)):
        px = closes[i]
        hi = highs[i]
        lo = lows[i]
        ts = timestamps[i]
        pred = preds.iloc[i]

        if in_pos:
            bars_held += 1
            exit_reason = None
            exit_px = px
            if side == 1:
                if lo <= sl_px:
                    exit_reason = "sl"; exit_px = sl_px
                elif hi >= tp_px:
                    exit_reason = "tp"; exit_px = tp_px
                elif bars_held >= max_hold_bars:
                    exit_reason = "time"; exit_px = px
            else:
                if hi >= sl_px:
                    exit_reason = "sl"; exit_px = sl_px
                elif lo <= tp_px:
                    exit_reason = "tp"; exit_px = tp_px
                elif bars_held >= max_hold_bars:
                    exit_reason = "time"; exit_px = px

            if exit_reason:
                gross = (exit_px - entry_px) / entry_px * side
                ret_pct = gross - 2 * fee_rate
                equity *= (1 + ret_pct)
                trades.append({
                    "entry_ts": entry_ts, "exit_ts": str(ts),
                    "side": side, "entry_px": entry_px, "exit_px": exit_px,
                    "return_pct": ret_pct, "exit_reason": exit_reason,
                })
                in_pos = False; side = 0; bars_held = 0

        elif not in_pos and not math.isnan(pred):
            if pred > entry_threshold:
                in_pos = True; side = 1
                entry_px = px
                sl_px = px * (1 - sl_pct); tp_px = px * (1 + tp_pct)
                bars_held = 0; entry_ts = str(ts); qty = equity / px
            elif pred < -entry_threshold:
                in_pos = True; side = -1
                entry_px = px
                sl_px = px * (1 + sl_pct); tp_px = px * (1 - tp_pct)
                bars_held = 0; entry_ts = str(ts); qty = equity / px

        equity_curve.append((ts, equity))

    # Buy & Hold benchmark over test window
    bh_pct = (closes[-1] / closes[0]) - 1
    total_return_pct = (equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    # Drawdown
    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    # Sharpe (annualized per-trade)
    if trades:
        rs = np.array([t["return_pct"] for t in trades])
        mu, sd = rs.mean(), rs.std(ddof=1) if len(rs) > 1 else 0.0
        # Annualize: 1m bars × 365 days × 24h × 60min = 525600 bars/year.
        # Trades_per_year = n_trades / oos_minutes * 525600
        oos_minutes = (timestamps[-1] - timestamps[0]).total_seconds() / 60.0
        trades_per_year = len(trades) / oos_minutes * 525600.0 if oos_minutes > 0 else 0
        sharpe_ann = float(mu / sd * math.sqrt(max(trades_per_year, 1))) if sd > 0 else 0.0
        wins = rs[rs > 0]
        losses = rs[rs < 0]
        win_rate_pct = float(len(wins) / len(rs) * 100)
        gw = float(wins.sum()) if len(wins) else 0.0
        gl = float(-losses.sum()) if len(losses) else 0.0
        profit_factor = float(gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
        avg_win = float(wins.mean() * 100) if len(wins) else 0.0
        avg_loss = float(losses.mean() * 100) if len(losses) else 0.0
    else:
        sharpe_ann = 0.0; win_rate_pct = 0.0; profit_factor = 0.0
        avg_win = 0.0; avg_loss = 0.0

    oos_days = int((timestamps[-1] - timestamps[0]).total_seconds() // 86400)

    return {
        "n_trades": len(trades),
        "alpha_pct": round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "oos_days": oos_days,
        "exit_reasons": _count_reasons(trades),
    }


def _count_reasons(trades: list[dict]) -> dict:
    out = {}
    for t in trades:
        out[t["exit_reason"]] = out.get(t["exit_reason"], 0) + 1
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--lookback", type=int, default=120,
                   help="Default 120 = 2h lookback on 1m bars.")
    p.add_argument("--fwd", type=int, default=60,
                   help="Default 60 = 1h forward target on 1m bars.")
    p.add_argument("--entry-threshold", type=float, default=0.002,
                   help="In log-return units. Default 0.002 ≈ 20bps fwd return — "
                        "must beat round-trip fee × ~3 to be net-positive.")
    p.add_argument("--sl-pct", type=float, default=0.06)
    p.add_argument("--tp-pct", type=float, default=0.15)
    p.add_argument("--max-hold-bars", type=int, default=60,
                   help="Default 60 = 1h hold on 1m bars (matches fwd horizon).")
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--out-dir", default=str(OUT_DIR))
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ohlcv = load_ohlcv_1m(args.symbol)
    X, y = build_features(ohlcv, lookback=args.lookback, fwd=args.fwd)
    preds, train_meta = train_predict(X, y, train_frac=args.train_frac)
    sim = simulate(
        ohlcv, preds,
        entry_threshold=args.entry_threshold,
        sl_pct=args.sl_pct, tp_pct=args.tp_pct,
        max_hold_bars=args.max_hold_bars,
        fee_rate=args.fee_rate, capital=args.capital,
    )

    metrics = {
        "paradigm": PARADIGM,
        "phase": "R-1_PoC",
        "spec_name": f"{args.symbol}_lookback{args.lookback}_fwd{args.fwd}",
        "symbol": args.symbol,
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "config": {
            "lookback": args.lookback, "fwd": args.fwd,
            "entry_threshold": args.entry_threshold,
            "sl_pct": args.sl_pct, "tp_pct": args.tp_pct,
            "max_hold_bars": args.max_hold_bars,
            "fee_rate": args.fee_rate, "capital": args.capital,
            "train_frac": args.train_frac,
        },
        "train_meta": train_meta,
        **sim,
    }

    out_path = out_dir / f"poc__{args.symbol}__metrics.json"
    out_path.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Wrote %s", out_path)

    print(json.dumps({
        "symbol": args.symbol,
        "alpha_pct": metrics["alpha_pct"],
        "n_trades": metrics["n_trades"],
        "sharpe_ann": metrics["sharpe_ann"],
        "max_dd_pct": metrics["max_dd_pct"],
        "win_rate_pct": metrics["win_rate_pct"],
        "profit_factor": metrics["profit_factor"],
        "buy_hold_pct": metrics["buy_hold_pct"],
        "total_return_pct": metrics["total_return_pct"],
        "oos_days": metrics["oos_days"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
