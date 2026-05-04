#!/usr/bin/env python3
"""Phase R-1 PoC: Multi-symbol portfolio paradigm (3-E).

Hypothesis: cross-sectional alpha (predicting *which* symbol outperforms others)
is orthogonal to single-symbol alpha (predicting future return per symbol). The
14 Binance paper-pool symbols all have single-symbol specs; a portfolio that
only uses *relative* signals would be strictly orthogonal.

Pipeline:
  1. Load daily OHLCV for 14 Binance symbols (server-side resample from 1m DB).
  2. For each (date, symbol), build features:
       - return_t-i for i in {1, 3, 5, 10, 20, 30}
       - vol_5d / vol_10d / vol_20d (rolling stdev of daily returns)
       - cross-section rank of return_t-1 (relative position among 14 symbols)
       - cross-section rank of vol_5d
  3. Target: next-day return.
  4. lgbm regressor on long-format (date × symbol).
  5. Train chronologically on first 50%, predict on rest.
  6. Each test day: predict 14 returns, rank, long top-K, short bottom-K
     (equal weight, market-neutral).
  7. Portfolio daily return − fee × turnover.
  8. Metrics: alpha vs equal-weight BH, sharpe, MDD, drawdown, etc.

Usage:
  python -m scripts.poc_multi_symbol_portfolio
  python -m scripts.poc_multi_symbol_portfolio --top-k 3 --train-frac 0.5
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
from scipy.stats import spearmanr
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_multi_symbol_portfolio")

PARADIGM = "multi_symbol_portfolio"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM

# Same 14 Binance symbols as paper pool
DEFAULT_SYMBOLS = [
    "SOLUSDT", "HBARUSDT", "AXSUSDT", "DOGEUSDT", "UNIUSDT",
    "PYTHUSDT", "TONUSDT", "ICPUSDT", "ETCUSDT", "JUPUSDT",
    "COMPUSDT", "WLDUSDT", "LDOUSDT", "1000LUNCUSDT",
]


def load_daily(symbols: list[str]) -> pd.DataFrame:
    """Server-side daily resample from 1m OHLCV."""
    s = SessionLocal()
    try:
        rows = []
        for sym in symbols:
            df = pd.read_sql(
                text("""
                    SELECT
                      DATE(timestamp) AS date,
                      (ARRAY_AGG(open ORDER BY timestamp ASC))[1] AS open,
                      MAX(high) AS high,
                      MIN(low) AS low,
                      (ARRAY_AGG(close ORDER BY timestamp DESC))[1] AS close,
                      SUM(volume) AS volume,
                      COUNT(*) AS bar_count
                    FROM ohlcv WHERE symbol=:sym AND time_frame='1m'
                    GROUP BY DATE(timestamp)
                    ORDER BY DATE(timestamp)
                """),
                s.connection(),
                params={"sym": sym},
                parse_dates=["date"],
            )
            df["symbol"] = sym
            df = df[df["bar_count"] >= 1000]  # filter incomplete days (<70% of 1440)
            rows.append(df)
            log.info("Loaded %s daily: %d rows (%s → %s)",
                     sym, len(df), df["date"].min(), df["date"].max())
        return pd.concat(rows, ignore_index=True)
    finally:
        s.close()


def build_features(daily: pd.DataFrame, *, demean_xs: bool
                   ) -> tuple[pd.DataFrame, list[str]]:
    """Build per-symbol features + cross-section ranks. Returns long-format DF + target.

    When demean_xs=True, every feature (and the target) is demeaned per date —
    forcing the model to learn pure cross-sectional relatives, not level effects.
    """
    daily = daily.sort_values(["symbol", "date"]).copy()
    daily["close"] = daily["close"].astype(float)
    daily["log_ret"] = daily.groupby("symbol")["close"].transform(
        lambda s: np.log(s / s.shift(1))
    )

    # Per-symbol features (lookback returns + rolling vol)
    for lag in (1, 3, 5, 10, 20, 30):
        daily[f"r_{lag}"] = daily.groupby("symbol")["log_ret"].shift(lag)
    for win in (5, 10, 20):
        daily[f"vol_{win}d"] = daily.groupby("symbol")["log_ret"].transform(
            lambda s: s.rolling(win).std()
        )

    # Target: next-day return
    daily["y"] = daily.groupby("symbol")["log_ret"].shift(-1)

    # Cross-section ranks (per-date, across symbols)
    def _xs_rank(group_col: str) -> pd.Series:
        return daily.groupby("date")[group_col].rank(pct=True) - 0.5

    daily["xs_rank_r1"] = _xs_rank("r_1")
    daily["xs_rank_r5"] = _xs_rank("r_5")
    daily["xs_rank_r20"] = _xs_rank("r_20")
    daily["xs_rank_vol5"] = _xs_rank("vol_5d")

    base_cols = [
        "r_1", "r_3", "r_5", "r_10", "r_20", "r_30",
        "vol_5d", "vol_10d", "vol_20d",
        "xs_rank_r1", "xs_rank_r5", "xs_rank_r20", "xs_rank_vol5",
    ]

    if demean_xs:
        for c in base_cols:
            daily[c] = daily[c] - daily.groupby("date")[c].transform("mean")
        daily["y"] = daily["y"] - daily.groupby("date")["y"].transform("mean")
        log.info("Cross-section demeaning applied to all features + target")

    feature_cols = base_cols
    df = daily.dropna(subset=feature_cols + ["y"]).copy()

    log.info("Built panel: %d (date, symbol) rows over %d dates × %d symbols",
             len(df), df["date"].nunique(), df["symbol"].nunique())
    return df, feature_cols


def train_predict(df: pd.DataFrame, feature_cols: list[str], train_frac: float
                  ) -> tuple[pd.DataFrame, dict]:
    import lightgbm as lgb

    df = df.sort_values(["date", "symbol"]).reset_index(drop=True)
    dates = sorted(df["date"].unique())
    split_date = dates[int(len(dates) * train_frac)]

    train = df[df["date"] < split_date]
    test = df[df["date"] >= split_date].copy()
    log.info("Train: %d rows (< %s) | Test: %d rows (>= %s)",
             len(train), split_date, len(test), split_date)

    model = lgb.LGBMRegressor(
        n_estimators=400, num_leaves=31, learning_rate=0.05,
        min_child_samples=50, feature_fraction=0.7,
        bagging_fraction=0.8, bagging_freq=5,
        reg_alpha=0.1, reg_lambda=0.1, n_jobs=-1, verbose=-1,
    )
    model.fit(train[feature_cols], train["y"])
    test["pred"] = model.predict(test[feature_cols])

    # IC diagnostics
    ic_pearson = float(np.corrcoef(test["pred"], test["y"])[0, 1])
    rho, p = spearmanr(test["pred"], test["y"])
    rank_ic = float(rho); rank_ic_p = float(p)

    # Cross-sectional IC: per-date Spearman, then average
    daily_ics = []
    for d, g in test.groupby("date"):
        if len(g) >= 5:
            r, _ = spearmanr(g["pred"], g["y"])
            if not math.isnan(r):
                daily_ics.append(r)
    xs_rank_ic_mean = float(np.mean(daily_ics)) if daily_ics else 0.0
    xs_rank_ic_std = float(np.std(daily_ics)) if daily_ics else 0.0
    icir = xs_rank_ic_mean / xs_rank_ic_std * math.sqrt(252) if xs_rank_ic_std > 0 else 0.0

    importance = pd.Series(model.feature_importances_, index=feature_cols
                           ).sort_values(ascending=False).to_dict()

    return test, {
        "n_train": len(train), "n_test": len(test),
        "test_start": str(test["date"].min()),
        "test_end": str(test["date"].max()),
        "ic_pearson_pooled": round(ic_pearson, 5),
        "rank_ic_pooled": round(rank_ic, 5),
        "rank_ic_p": round(rank_ic_p, 5),
        "xs_rank_ic_daily_mean": round(xs_rank_ic_mean, 5),
        "xs_rank_ic_daily_std": round(xs_rank_ic_std, 5),
        "xs_rank_icir_ann": round(icir, 3),
        "n_test_days": len(daily_ics),
        "feature_importance": {k: int(v) for k, v in importance.items()},
    }


def simulate_portfolio(test: pd.DataFrame, *, top_k: int, fee_rate: float,
                       capital: float, rebalance_every: int) -> dict:
    """Long top-K / short bottom-K, equal-weight, market-neutral.

    Rebalances every `rebalance_every` test days; the realized return on
    intervening days uses the prior weights and adds zero turnover.

    `test` MUST contain the original (un-demeaned) `log_ret` column so we can
    compute realized portfolio returns; demeaning applies only to features
    and the regression target.
    """
    test = test.sort_values(["date", "symbol"]).copy()
    dates = sorted(test["date"].unique())

    equity = capital
    equity_curve = []
    bh_curve = []
    bh_equity = capital
    daily_strategy_rets = []
    daily_bh_rets = []
    prev_weights = pd.Series(dtype=float)
    total_turnover = 0.0
    n_long_legs = 0
    n_short_legs = 0

    for i, d in enumerate(dates):
        g = test[test["date"] == d]
        if len(g) < 2 * top_k:
            equity_curve.append((d, equity))
            bh_curve.append((d, bh_equity))
            continue

        rebalance_today = (i % rebalance_every == 0)

        # Decide today's weights
        if rebalance_today:
            ranked = g.sort_values("pred", ascending=False)
            longs = ranked.head(top_k)
            shorts = ranked.tail(top_k)
            weights = pd.Series(0.0, index=g["symbol"])
            weights.loc[longs["symbol"].values] = 1.0 / top_k
            weights.loc[shorts["symbol"].values] = -1.0 / top_k
        else:
            weights = prev_weights.reindex(g["symbol"]).fillna(0.0)

        # Realize today's return on PREVIOUS weights
        if i > 0 and len(prev_weights) > 0:
            today_logret = g.set_index("symbol")["log_ret"]
            simple_ret = np.exp(today_logret) - 1
            port_simple_ret = (prev_weights.reindex(simple_ret.index).fillna(0)
                               * simple_ret).sum()
            turnover = (weights.reindex(simple_ret.index).fillna(0)
                        - prev_weights.reindex(simple_ret.index).fillna(0)
                        ).abs().sum()
            total_turnover += turnover
            net_ret = port_simple_ret - turnover * fee_rate
            equity *= (1 + net_ret)
            daily_strategy_rets.append(net_ret)

            bh_simple_ret = simple_ret.mean()
            bh_equity *= (1 + bh_simple_ret)
            daily_bh_rets.append(bh_simple_ret)

        prev_weights = weights
        if rebalance_today:
            n_long_legs += top_k
            n_short_legs += top_k
        equity_curve.append((d, equity))
        bh_curve.append((d, bh_equity))

    n_test_days = len(daily_strategy_rets)
    total_return_pct = (equity / capital) - 1
    bh_pct = (bh_equity / capital) - 1
    alpha_pct = (total_return_pct - bh_pct) * 100

    # Sharpe (daily, annualized)
    if daily_strategy_rets:
        rs = np.array(daily_strategy_rets)
        mu, sd = rs.mean(), rs.std(ddof=1) if len(rs) > 1 else 0.0
        sharpe_ann = float(mu / sd * math.sqrt(252)) if sd > 0 else 0.0
        wins = rs[rs > 0]; losses = rs[rs < 0]
        win_rate_pct = float(len(wins) / len(rs) * 100)
        gw = float(wins.sum()) if len(wins) else 0.0
        gl = float(-losses.sum()) if len(losses) else 0.0
        profit_factor = float(gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
    else:
        sharpe_ann = win_rate_pct = profit_factor = 0.0

    # Drawdown (daily granularity)
    eq = np.array([e for _, e in equity_curve])
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / peak
    max_dd_pct = float(dd.max() * 100) if len(dd) else 0.0

    avg_turnover_pct = (total_turnover / n_test_days * 100) if n_test_days else 0.0

    return {
        "n_test_days": n_test_days,
        "n_trades": int(n_long_legs + n_short_legs),  # leg count, not round-trips
        "alpha_pct": round(alpha_pct * 100, 2) if False else round(alpha_pct, 2),
        "total_return_pct": round(total_return_pct * 100, 2),
        "buy_hold_pct": round(bh_pct * 100, 2),
        "sharpe_ann": round(sharpe_ann, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
        "oos_days": n_test_days,
        "avg_daily_turnover_pct": round(avg_turnover_pct, 2),
        "total_turnover": round(total_turnover, 2),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--top-k", type=int, default=3,
                   help="Long top-K, short bottom-K. Default 3 (out of 14).")
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--demean-xs", action="store_true",
                   help="Cross-section demean every feature + target each day, "
                        "forcing the model to learn pure relatives (no level effects).")
    p.add_argument("--rebalance-every", type=int, default=1,
                   help="Rebalance every N test days. Default 1 (daily). "
                        "Set 5 or 7 to slash turnover.")
    p.add_argument("--tag", default="all14_topK3_daily_lgbm",
                   help="Spec name suffix written to metrics file.")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    daily = load_daily(args.symbols)
    df, feature_cols = build_features(daily, demean_xs=args.demean_xs)
    test_df, train_meta = train_predict(df, feature_cols, train_frac=args.train_frac)
    sim = simulate_portfolio(
        test_df, top_k=args.top_k, fee_rate=args.fee_rate,
        capital=args.capital, rebalance_every=args.rebalance_every,
    )

    metrics = {
        "paradigm": PARADIGM,
        "phase": "R-1_PoC",
        "spec_name": args.tag,
        "symbols": args.symbols,
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "config": {
            "top_k": args.top_k, "fee_rate": args.fee_rate,
            "capital": args.capital, "train_frac": args.train_frac,
            "demean_xs": args.demean_xs,
            "rebalance_every": args.rebalance_every,
        },
        "train_meta": train_meta,
        **sim,
    }

    out_path = OUT_DIR / f"poc__{args.tag}__metrics.json"
    out_path.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Wrote %s", out_path)

    print(json.dumps({
        "alpha_pct": metrics["alpha_pct"],
        "total_return_pct": metrics["total_return_pct"],
        "buy_hold_pct": metrics["buy_hold_pct"],
        "sharpe_ann": metrics["sharpe_ann"],
        "max_dd_pct": metrics["max_dd_pct"],
        "win_rate_pct": metrics["win_rate_pct"],
        "profit_factor": metrics["profit_factor"],
        "oos_days": metrics["oos_days"],
        "rank_ic_pooled": train_meta["rank_ic_pooled"],
        "xs_rank_ic_daily_mean": train_meta["xs_rank_ic_daily_mean"],
        "xs_rank_icir_ann": train_meta["xs_rank_icir_ann"],
        "avg_daily_turnover_pct": sim["avg_daily_turnover_pct"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
