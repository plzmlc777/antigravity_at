#!/usr/bin/env python3
"""Phase R-3 robustness for funding_flip paradigm.

Diagnostics on best R-2 spec (mag=0.0001, hold=6, cont direction):
  1. Walk-forward 6-fold on full 1y series (train_frac=0.0 per fold).
  2. Permutation test (n=200): shuffle funding_rate while keeping mark_price
     intact. p-value = fraction of shuffles producing alpha ≥ real alpha.

Usage:
  python -m scripts.poc_funding_flip_r3 --symbols LINKUSDT COMPUSDT HBARUSDT
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

from scripts.poc_funding_flip import (  # noqa: E402
    PARADIGM, OUT_DIR, load_funding, simulate_funding_flip,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_funding_flip_r3")

DEFAULT_SYMBOLS = ["LINKUSDT", "COMPUSDT", "HBARUSDT"]


def walk_forward_6fold(df: pd.DataFrame, n_folds: int, **rule_params) -> dict:
    n = len(df)
    fold_size = n // n_folds
    folds = []
    pos_count = 0
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        sub = df.iloc[start:end].copy()
        if len(sub) < 50:
            folds.append({"fold": k + 1, "skipped": True})
            continue
        sim = simulate_funding_flip(sub, train_frac=0.0, **rule_params)
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
            "n_periods": len(sub),
            "alpha_pct": sim["alpha_pct"],
            "sharpe_ann": sim["sharpe_ann"],
            "n_trades": sim["n_trades"],
            "max_dd_pct": sim["max_dd_pct"],
            "positive": is_pos,
        })
    return {"n_folds": n_folds, "positive_folds": pos_count, "folds": folds}


def permutation_test(df: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    rng = np.random.default_rng(seed=42)
    real_funding = df["funding_rate"].values.copy()
    random_alphas = []
    for it in range(n_iter):
        shuf = df.copy()
        shuf["funding_rate"] = rng.permutation(real_funding)
        sim = simulate_funding_flip(shuf, train_frac=0.5, **rule_params)
        random_alphas.append(sim.get("alpha_pct", 0.0))
        if (it + 1) % 50 == 0:
            log.info("  perm test %d/%d (running mean=%.2f)",
                     it + 1, n_iter, np.mean(random_alphas))
    arr = np.array(random_alphas)
    p_one_sided = float((arr >= real_alpha).sum() / len(arr))
    return {
        "n_iter": n_iter, "real_alpha_pct": real_alpha,
        "random_alpha_mean": round(float(arr.mean()), 3),
        "random_alpha_std": round(float(arr.std()), 3),
        "random_alpha_q05": round(float(np.percentile(arr, 5)), 3),
        "random_alpha_q95": round(float(np.percentile(arr, 95)), 3),
        "perm_p": round(p_one_sided, 4),
    }


def evaluate_one(symbol: str, *, magnitude: float, hold_periods: int,
                 sl_pct: float, fee_rate: float, capital: float,
                 train_frac: float, reverse_sign: bool, n_iter_perm: int) -> dict:
    rule_params = dict(magnitude=magnitude, hold_periods=hold_periods,
                       sl_pct=sl_pct, fee_rate=fee_rate, capital=capital,
                       reverse_sign=reverse_sign)
    df = load_funding(symbol)
    if len(df) < 200:
        return {"symbol": symbol, "skipped": True}

    log.info("[%s] R-1 baseline (train_frac=%.2f)", symbol, train_frac)
    real_sim = simulate_funding_flip(df, train_frac=train_frac, **rule_params)
    log.info("[%s] full series (train_frac=0.0)", symbol)
    full_sim = simulate_funding_flip(df, train_frac=0.0, **rule_params)
    log.info("[%s] walk-forward 6-fold", symbol)
    wf = walk_forward_6fold(df, n_folds=6, **rule_params)
    log.info("[%s] perm test n=%d", symbol, n_iter_perm)
    perm = permutation_test(df, n_iter=n_iter_perm,
                             real_alpha=real_sim["alpha_pct"], **rule_params)

    return {
        "symbol": symbol, "paradigm": PARADIGM, "phase": "R-3_robustness",
        "config": rule_params | {"train_frac": train_frac},
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "real_metrics_oos": real_sim,
        "full_metrics": full_sim,
        "walk_forward": wf,
        "permutation": perm,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--magnitude", type=float, default=0.0001)
    p.add_argument("--hold-periods", type=int, default=6)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true", default=True)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    for sym in args.symbols:
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        result = evaluate_one(
            sym, magnitude=args.magnitude, hold_periods=args.hold_periods,
            sl_pct=args.sl_pct, fee_rate=args.fee_rate,
            capital=args.capital, train_frac=args.train_frac,
            reverse_sign=args.reverse_sign, n_iter_perm=args.n_iter_perm,
        )
        if result.get("skipped"):
            continue
        out_path = OUT_DIR / f"r3_robust__{sym}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))

        rm = result["real_metrics_oos"]; full = result["full_metrics"]
        wf = result["walk_forward"]; pe = result["permutation"]
        log.info("%s OOS — alpha=%.2f sharpe=%.2f | full alpha=%.2f sharpe=%.2f "
                 "wf=%d/%d perm_p=%.4f",
                 sym, rm["alpha_pct"], rm["sharpe_ann"],
                 full["alpha_pct"], full["sharpe_ann"],
                 wf["positive_folds"], wf["n_folds"], pe["perm_p"])
        summary_rows.append({
            "symbol": sym,
            "alpha_oos": rm["alpha_pct"], "sharpe_oos": rm["sharpe_ann"],
            "alpha_full": full["alpha_pct"], "sharpe_full": full["sharpe_ann"],
            "mdd_full": full["max_dd_pct"], "wr_full": full["win_rate_pct"],
            "pf_full": full["profit_factor"], "trades_full": full["n_trades"],
            "wf_pos": wf["positive_folds"], "wf_total": wf["n_folds"],
            "perm_p": pe["perm_p"], "perm_random_mean": pe["random_alpha_mean"],
        })

    if summary_rows:
        df_sum = pd.DataFrame(summary_rows)
        out_csv = OUT_DIR / "r3_summary.csv"
        df_sum.to_csv(out_csv, index=False)
        print("\n=== R-3 Summary ===")
        print(df_sum.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
