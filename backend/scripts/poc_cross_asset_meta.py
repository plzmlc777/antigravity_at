#!/usr/bin/env python3
"""Phase R-1 PoC: Cross-asset meta paradigm (3-B).

Hypothesis: macro context (BTC/ETH/SPX/DXY/VIX dynamics) carries information
that current paper-pool single-symbol microstructure specs cannot access. Adding
macro features to a 14-symbol cross-section regressor should improve out-of-sample
alpha if the hypothesis holds; if alpha matches the multi_symbol_portfolio
baseline, the macro features add nothing and the paradigm is dead.

Pipeline (extends multi_symbol_portfolio):
  1. Daily-resample 14 Binance symbols (server-side from 1m DB).
  2. Load macro daily series (yfinance CSVs in _macro/).
  3. Build per-(date,symbol) features:
       - per-symbol returns/vol/cross-section ranks (same as multi_symbol_portfolio)
       - per-date macro features (broadcast to all symbols)
       - per-(date,symbol) interactions (return × btc_return, vol × vix)
  4. lgbm regressor on long-format panel.
  5. Same simulation: top-K weekly demean rebalance.
  6. Compare against multi_symbol_portfolio best (alpha +73, sharpe +0.81).

Usage:
  python -m scripts.poc_cross_asset_meta
  python -m scripts.poc_cross_asset_meta --top-k 5 --rebalance-every 5
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
from scripts.poc_multi_symbol_portfolio import (  # noqa: E402
    DEFAULT_SYMBOLS, load_daily, simulate_portfolio,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_cross_asset_meta")

PARADIGM = "cross_asset_meta"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
MACRO_DIR = OUT_DIR / "_macro"

MACRO_TICKERS = ["btc", "eth", "spx", "dxy", "vix"]


def load_macro_panel(date_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Read each macro CSV, forward-fill weekends, build feature panel keyed by date."""
    out = pd.DataFrame(index=date_index)
    for name in MACRO_TICKERS:
        path = MACRO_DIR / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Macro file not found: {path} — run yfinance backfill")
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        close = df["close"].reindex(date_index).ffill()
        logret = np.log(close / close.shift(1))

        for lag in (1, 3, 5):
            out[f"{name}_r_{lag}"] = logret.shift(lag - 1)
        out[f"{name}_close"] = close
        out[f"{name}_vol_5"] = logret.rolling(5).std()
    out.index.name = "date"
    out = out.reset_index()
    return out


def build_features_with_macro(daily: pd.DataFrame, *, demean_xs: bool
                              ) -> tuple[pd.DataFrame, list[str]]:
    """Build per-symbol features + macro broadcast + interactions."""
    daily = daily.sort_values(["symbol", "date"]).copy()
    daily["close"] = daily["close"].astype(float)
    daily["log_ret"] = daily.groupby("symbol")["close"].transform(
        lambda s: np.log(s / s.shift(1))
    )

    for lag in (1, 3, 5, 10, 20, 30):
        daily[f"r_{lag}"] = daily.groupby("symbol")["log_ret"].shift(lag)
    for win in (5, 10, 20):
        daily[f"vol_{win}d"] = daily.groupby("symbol")["log_ret"].transform(
            lambda s: s.rolling(win).std()
        )
    daily["y"] = daily.groupby("symbol")["log_ret"].shift(-1)

    def _xs_rank(c: str) -> pd.Series:
        return daily.groupby("date")[c].rank(pct=True) - 0.5
    daily["xs_rank_r1"] = _xs_rank("r_1")
    daily["xs_rank_r5"] = _xs_rank("r_5")
    daily["xs_rank_r20"] = _xs_rank("r_20")
    daily["xs_rank_vol5"] = _xs_rank("vol_5d")

    # Macro broadcast
    full_dates = pd.DatetimeIndex(sorted(daily["date"].unique()))
    macro_df = load_macro_panel(full_dates)
    daily = daily.merge(macro_df, on="date", how="left")

    # Interactions: per-symbol r_5 × btc_r_5 captures co-movement; vol_5d × vix
    # captures regime-conditional vol
    daily["int_r5_btc_r5"] = daily["r_5"] * daily["btc_r_5"]
    daily["int_r5_eth_r5"] = daily["r_5"] * daily["eth_r_5"]
    daily["int_vol5_vix"] = daily["vol_5d"] * daily["vix_close"]
    daily["int_r1_dxy_r1"] = daily["r_1"] * daily["dxy_r_1"]

    base_cols = [
        "r_1", "r_3", "r_5", "r_10", "r_20", "r_30",
        "vol_5d", "vol_10d", "vol_20d",
        "xs_rank_r1", "xs_rank_r5", "xs_rank_r20", "xs_rank_vol5",
    ]
    macro_cols = [
        "btc_r_1", "btc_r_3", "btc_r_5", "btc_vol_5",
        "eth_r_1", "eth_r_3", "eth_r_5", "eth_vol_5",
        "spx_r_1", "spx_r_3", "spx_r_5", "spx_vol_5",
        "dxy_r_1", "dxy_r_3", "dxy_r_5",
        "vix_close", "vix_r_1", "vix_vol_5",
    ]
    interaction_cols = ["int_r5_btc_r5", "int_r5_eth_r5", "int_vol5_vix", "int_r1_dxy_r1"]

    if demean_xs:
        # Only demean per-symbol cols + target. Macro is per-date constant —
        # demean would zero it out, so we leave it alone.
        for c in base_cols:
            daily[c] = daily[c] - daily.groupby("date")[c].transform("mean")
        for c in interaction_cols:
            daily[c] = daily[c] - daily.groupby("date")[c].transform("mean")
        daily["y"] = daily["y"] - daily.groupby("date")["y"].transform("mean")
        log.info("Cross-section demeaning applied to per-symbol cols + interactions + y")

    feature_cols = base_cols + macro_cols + interaction_cols
    df = daily.dropna(subset=feature_cols + ["y"]).copy()
    log.info("Built panel: %d rows (date×symbol) | features: %d (base=%d, macro=%d, int=%d)",
             len(df), len(feature_cols), len(base_cols), len(macro_cols),
             len(interaction_cols))
    return df, feature_cols


def train_predict(df: pd.DataFrame, feature_cols: list[str], train_frac: float
                  ) -> tuple[pd.DataFrame, dict]:
    import lightgbm as lgb

    df = df.sort_values(["date", "symbol"]).reset_index(drop=True)
    dates = sorted(df["date"].unique())
    split_date = dates[int(len(dates) * train_frac)]
    train = df[df["date"] < split_date]
    test = df[df["date"] >= split_date].copy()
    log.info("Train: %d rows (< %s) | Test: %d rows", len(train), split_date, len(test))

    model = lgb.LGBMRegressor(
        n_estimators=400, num_leaves=31, learning_rate=0.05,
        min_child_samples=50, feature_fraction=0.7,
        bagging_fraction=0.8, bagging_freq=5,
        reg_alpha=0.1, reg_lambda=0.1, n_jobs=-1, verbose=-1,
    )
    model.fit(train[feature_cols], train["y"])
    test["pred"] = model.predict(test[feature_cols])

    ic_pearson = float(np.corrcoef(test["pred"], test["y"])[0, 1])
    rho, p = spearmanr(test["pred"], test["y"])
    rank_ic = float(rho); rank_ic_p = float(p)

    daily_ics = []
    for d, g in test.groupby("date"):
        if len(g) >= 5:
            r, _ = spearmanr(g["pred"], g["y"])
            if not math.isnan(r):
                daily_ics.append(r)
    xs_rank_ic_mean = float(np.mean(daily_ics)) if daily_ics else 0.0
    xs_rank_ic_std = float(np.std(daily_ics)) if daily_ics else 0.0
    icir = (xs_rank_ic_mean / xs_rank_ic_std * math.sqrt(252)
            if xs_rank_ic_std > 0 else 0.0)

    importance = pd.Series(model.feature_importances_, index=feature_cols
                           ).sort_values(ascending=False)
    top20 = importance.head(20).to_dict()
    # Group importance by family
    fam_groups = {
        "per_symbol_returns": [c for c in feature_cols if c.startswith("r_")],
        "per_symbol_vol": [c for c in feature_cols if c.startswith("vol_")],
        "per_symbol_xs_rank": [c for c in feature_cols if c.startswith("xs_rank_")],
        "macro_btc": [c for c in feature_cols if c.startswith("btc_")],
        "macro_eth": [c for c in feature_cols if c.startswith("eth_")],
        "macro_spx": [c for c in feature_cols if c.startswith("spx_")],
        "macro_dxy": [c for c in feature_cols if c.startswith("dxy_")],
        "macro_vix": [c for c in feature_cols if c.startswith("vix_")],
        "interactions": [c for c in feature_cols if c.startswith("int_")],
    }
    family_importance = {fam: int(importance[cols].sum())
                         for fam, cols in fam_groups.items()}

    return test, {
        "n_train": len(train), "n_test": len(test),
        "test_start": str(test["date"].min()), "test_end": str(test["date"].max()),
        "ic_pearson_pooled": round(ic_pearson, 5),
        "rank_ic_pooled": round(rank_ic, 5),
        "rank_ic_p": round(rank_ic_p, 5),
        "xs_rank_ic_daily_mean": round(xs_rank_ic_mean, 5),
        "xs_rank_ic_daily_std": round(xs_rank_ic_std, 5),
        "xs_rank_icir_ann": round(icir, 3),
        "n_test_days": len(daily_ics),
        "feature_importance_top20": {k: int(v) for k, v in top20.items()},
        "feature_importance_by_family": family_importance,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--demean-xs", action="store_true", default=True)
    p.add_argument("--no-demean-xs", dest="demean_xs", action="store_false")
    p.add_argument("--rebalance-every", type=int, default=5)
    p.add_argument("--tag", default="all14_topK5_macro_demean_weekly")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    daily = load_daily(args.symbols)
    df, feature_cols = build_features_with_macro(daily, demean_xs=args.demean_xs)
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
            "top_k": args.top_k, "fee_rate": args.fee_rate, "capital": args.capital,
            "train_frac": args.train_frac, "demean_xs": args.demean_xs,
            "rebalance_every": args.rebalance_every,
            "macro_tickers": MACRO_TICKERS,
        },
        "train_meta": train_meta,
        **sim,
    }

    out_path = OUT_DIR / f"poc__{args.tag}__metrics.json"
    out_path.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Wrote %s", out_path)

    print(json.dumps({
        "alpha_pct": metrics["alpha_pct"],
        "buy_hold_pct": metrics["buy_hold_pct"],
        "sharpe_ann": metrics["sharpe_ann"],
        "max_dd_pct": metrics["max_dd_pct"],
        "win_rate_pct": metrics["win_rate_pct"],
        "profit_factor": metrics["profit_factor"],
        "rank_ic_pooled": train_meta["rank_ic_pooled"],
        "xs_rank_ic_daily_mean": train_meta["xs_rank_ic_daily_mean"],
        "xs_rank_icir_ann": train_meta["xs_rank_icir_ann"],
        "feature_importance_by_family": train_meta["feature_importance_by_family"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
