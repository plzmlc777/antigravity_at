#!/usr/bin/env python3
"""Phase R-3 robustness for funding_window_anomaly paradigm.

Two diagnostics on the best R-2 spec (z=2.5, pre=24, hold=12, lb=90):
  1. Walk-forward 6-fold: split full series into 6 contiguous segments. Each
     fold runs the rule with its own internal lookback seeding.
  2. Permutation test (n=200): randomly shuffle the 5m bar return series. The
     boundary timestamps are kept intact; we shuffle the WHICH bars get which
     return, so the funding-time seasonality (if real) is destroyed but data
     properties preserved. p-value = fraction of random shuffles producing
     alpha ≥ real alpha.

Usage:
  python -m scripts.poc_funding_window_r3 --symbols COMPUSDT AVAXUSDT SOLUSDT LINKUSDT
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.poc_funding_window import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, simulate_funding_window,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_funding_window_r3")

DEFAULT_SYMBOLS = ["COMPUSDT", "AVAXUSDT", "SOLUSDT", "LINKUSDT"]


def walk_forward_6fold(df: pd.DataFrame, n_folds: int, **rule_params) -> dict:
    n = len(df)
    fold_size = n // n_folds
    folds = []
    pos_count = 0
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        # use 5000 bars of seed before fold to warm up rolling windows
        seed_start = max(0, start - 5000)
        sub = df.iloc[seed_start:end].copy()
        if len(sub) < 10000:
            folds.append({"fold": k + 1, "skipped": True})
            continue
        sim = simulate_funding_window(sub, train_frac=0.0, **rule_params)
        if sim.get("error"):
            folds.append({"fold": k + 1, "error": sim["error"]})
            continue
        is_pos = sim["alpha_pct"] > 0
        if is_pos:
            pos_count += 1
        folds.append({
            "fold": k + 1,
            "start": str(sub.index[0]),
            "end": str(sub.index[-1]),
            "n_bars": len(sub),
            "alpha_pct": sim["alpha_pct"],
            "sharpe_ann": sim["sharpe_ann"],
            "n_trades": sim["n_trades"],
            "max_dd_pct": sim["max_dd_pct"],
            "positive": is_pos,
        })
    return {"n_folds": n_folds, "positive_folds": pos_count, "folds": folds}


def permutation_test(df: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    """Shuffle the 5m close-return series. This destroys funding-time seasonality
    while preserving the marginal distribution of returns."""
    rng = np.random.default_rng(seed=42)
    base_close = df["close"].values
    base_returns = np.diff(base_close) / base_close[:-1]  # length n-1

    random_alphas = []
    for it in range(n_iter):
        shuf_returns = rng.permutation(base_returns)
        # rebuild close series from shuffled returns
        new_close = [base_close[0]]
        for r in shuf_returns:
            new_close.append(new_close[-1] * (1 + r))
        shuf = df.copy()
        shuf["close"] = new_close
        sim = simulate_funding_window(shuf, train_frac=0.5, **rule_params)
        if sim.get("error"):
            random_alphas.append(0.0)
        else:
            random_alphas.append(sim["alpha_pct"])
        if (it + 1) % 50 == 0:
            log.info("  perm test progress: %d/%d (running mean=%.2f)",
                     it + 1, n_iter, np.mean(random_alphas))

    arr = np.array(random_alphas)
    p_one_sided = float((arr >= real_alpha).sum() / len(arr))
    return {
        "n_iter": n_iter,
        "real_alpha_pct": real_alpha,
        "random_alpha_mean": round(float(arr.mean()), 3),
        "random_alpha_std": round(float(arr.std()), 3),
        "random_alpha_q05": round(float(np.percentile(arr, 5)), 3),
        "random_alpha_q95": round(float(np.percentile(arr, 95)), 3),
        "perm_p": round(p_one_sided, 4),
    }


def evaluate_one(symbol: str, *, pre_bars: int, hold_bars: int, lookback: int,
                 entry_z: float, sl_pct: float, fee_rate: float, capital: float,
                 train_frac: float, n_iter_perm: int) -> dict:
    rule_params = dict(pre_bars=pre_bars, hold_bars=hold_bars,
                       lookback=lookback, entry_z=entry_z, sl_pct=sl_pct,
                       fee_rate=fee_rate, capital=capital)

    df = load_ohlcv_5m(symbol)
    if len(df) < 50000:
        log.warning("Skip %s: only %d bars", symbol, len(df))
        return {"symbol": symbol, "skipped": True}

    log.info("[%s] R-1 baseline simulate (train_frac=%.2f)", symbol, train_frac)
    real_sim = simulate_funding_window(df, train_frac=train_frac, **rule_params)

    log.info("[%s] walk-forward 6-fold", symbol)
    wf = walk_forward_6fold(df, n_folds=6, **rule_params)

    log.info("[%s] permutation test n=%d", symbol, n_iter_perm)
    perm = permutation_test(df, n_iter=n_iter_perm,
                             real_alpha=real_sim["alpha_pct"], **rule_params)

    return {
        "symbol": symbol, "paradigm": PARADIGM, "phase": "R-3_robustness",
        "config": rule_params | {"train_frac": train_frac},
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "real_metrics": real_sim,
        "walk_forward": wf,
        "permutation": perm,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--pre-bars", type=int, default=24)
    p.add_argument("--hold-bars", type=int, default=12)
    p.add_argument("--lookback", type=int, default=90)
    p.add_argument("--entry-z", type=float, default=2.5)
    p.add_argument("--sl-pct", type=float, default=0.03)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for sym in args.symbols:
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        result = evaluate_one(
            sym, pre_bars=args.pre_bars, hold_bars=args.hold_bars,
            lookback=args.lookback, entry_z=args.entry_z,
            sl_pct=args.sl_pct, fee_rate=args.fee_rate,
            capital=args.capital, train_frac=args.train_frac,
            n_iter_perm=args.n_iter_perm,
        )
        if result.get("skipped"):
            continue
        out_path = OUT_DIR / f"r3_robust__{sym}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))

        rm = result["real_metrics"]; wf = result["walk_forward"]; pe = result["permutation"]
        log.info("%s — alpha=%.2f sharpe=%.2f wf=%d/%d positive perm_p=%.4f",
                 sym, rm["alpha_pct"], rm["sharpe_ann"],
                 wf["positive_folds"], wf["n_folds"], pe["perm_p"])

        summary_rows.append({
            "symbol": sym,
            "alpha_pct": rm["alpha_pct"],
            "sharpe_ann": rm["sharpe_ann"],
            "max_dd_pct": rm["max_dd_pct"],
            "win_rate_pct": rm["win_rate_pct"],
            "profit_factor": rm["profit_factor"],
            "n_trades": rm["n_trades"],
            "wf_positive_folds": wf["positive_folds"],
            "wf_total_folds": wf["n_folds"],
            "perm_p": pe["perm_p"],
            "perm_random_mean": pe["random_alpha_mean"],
        })

    if summary_rows:
        df_sum = pd.DataFrame(summary_rows)
        out_csv = OUT_DIR / "r3_summary.csv"
        df_sum.to_csv(out_csv, index=False)
        log.info("Wrote %s", out_csv)
        print("\n=== R-3 Summary ===")
        print(df_sum.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
