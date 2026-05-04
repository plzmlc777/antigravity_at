#!/usr/bin/env python3
"""Phase R-3 robustness for funding_carry paradigm.

Two diagnostics:
  1. Walk-forward 6-fold: split OOS into 6 contiguous segments, evaluate the
     z-score rule on each. Robustness = ≥5/6 folds with positive return.
  2. Permutation test (n=200): randomly shuffle the funding_rate time series
     while keeping mark_price intact, re-run the same rule. p-value =
     fraction of random shuffles producing alpha ≥ real alpha.

Both diagnostics go into a metrics JSON consumable by eval_research_gate.py.

Usage:
  python -m scripts.poc_funding_carry_r3 --symbol HBARUSDT
  python -m scripts.poc_funding_carry_r3 --symbols HBARUSDT AXSUSDT COMPUSDT ETCUSDT
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.poc_funding_carry import (  # noqa: E402
    PARADIGM, OUT_DIR, load_funding, simulate_funding_reversal,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_funding_carry_r3")

DEFAULT_SYMBOLS = ["HBARUSDT", "AXSUSDT", "COMPUSDT", "ETCUSDT"]


def simulate_window(df_window: pd.DataFrame, **rule_params) -> dict:
    """Run the z-score rule on a pre-sliced window with NO further train/test split."""
    rp = dict(rule_params)
    return simulate_funding_reversal(df_window, **rp, train_frac=0.0)


def walk_forward_6fold(df: pd.DataFrame, n_folds: int, lookback: int,
                       **rule_params) -> dict:
    """Split into n_folds contiguous segments. Each fold: full simulate within."""
    n = len(df)
    fold_size = n // n_folds
    folds = []
    pos_count = 0
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else n
        # Need lookback bars BEFORE the fold to seed the z-score
        seed_start = max(0, start - lookback)
        sub = df.iloc[seed_start:end]
        if len(sub) < lookback + 5:
            folds.append({"fold": k + 1, "skipped": True})
            continue
        sim = simulate_window(sub, lookback=lookback, **rule_params)
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


def permutation_test(df: pd.DataFrame, n_iter: int, lookback: int,
                     real_alpha: float, **rule_params) -> dict:
    """Shuffle funding_rate; mark_price untouched. Compute p-value."""
    rng = np.random.default_rng(seed=42)
    real_funding = df["funding_rate"].values.copy()
    random_alphas = []
    for it in range(n_iter):
        shuf = df.copy()
        shuf["funding_rate"] = rng.permutation(real_funding)
        sim = simulate_funding_reversal(shuf, lookback=lookback, train_frac=0.5,
                                         **rule_params)
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


def evaluate_one(symbol: str, *, lookback: int, entry_z: float, exit_z: float,
                 max_hold: int, sl_pct: float, fee_rate: float, capital: float,
                 train_frac: float, n_iter_perm: int) -> dict:
    rule_params = dict(entry_z=entry_z, exit_z=exit_z, max_hold=max_hold,
                       sl_pct=sl_pct, fee_rate=fee_rate, capital=capital)

    df = load_funding(symbol)
    if len(df) < 200:
        log.warning("Skip %s: only %d rows", symbol, len(df))
        return {"symbol": symbol, "skipped": True}

    # 1. Real R-1 simulation (same as PoC) for canonical real metrics
    real_sim = simulate_funding_reversal(df, lookback=lookback,
                                          train_frac=train_frac, **rule_params)

    # 2. Walk-forward 6-fold on the FULL series
    wf = walk_forward_6fold(df, n_folds=6, lookback=lookback, **rule_params)

    # 3. Permutation test
    perm = permutation_test(df, n_iter=n_iter_perm, lookback=lookback,
                             real_alpha=real_sim["alpha_pct"], **rule_params)

    return {
        "symbol": symbol, "paradigm": PARADIGM, "phase": "R-3_robustness",
        "config": {
            "lookback": lookback, "entry_z": entry_z, "exit_z": exit_z,
            "max_hold": max_hold, "sl_pct": sl_pct, "fee_rate": fee_rate,
            "capital": capital, "train_frac": train_frac,
        },
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
        "real_metrics": real_sim,
        "walk_forward": wf,
        "permutation": perm,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=2.5)
    p.add_argument("--exit-z", type=float, default=0.5)
    p.add_argument("--max-hold", type=int, default=15)
    p.add_argument("--sl-pct", type=float, default=0.05)
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
            sym, lookback=args.lookback, entry_z=args.entry_z,
            exit_z=args.exit_z, max_hold=args.max_hold,
            sl_pct=args.sl_pct, fee_rate=args.fee_rate,
            capital=args.capital, train_frac=args.train_frac,
            n_iter_perm=args.n_iter_perm,
        )
        if result.get("skipped"):
            continue

        out_path = OUT_DIR / f"r3_robust__{sym}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))

        rm = result["real_metrics"]; wf = result["walk_forward"]; pe = result["permutation"]
        log.info("%s — alpha=%.2f sharpe=%.2f wf=%d/%d positive perm_p=%.3f",
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
