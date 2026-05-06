#!/usr/bin/env python3
"""Phase R-3 robustness for funding_acceleration."""
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

from scripts.poc_funding_acceleration import (  # noqa: E402
    PARADIGM, OUT_DIR, load_funding, simulate_acceleration,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_funding_acceleration_r3")


def permutation_test(df: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    """Shuffle funding rate series → recompute Δfunding → re-simulate.

    This isolates whether the acceleration z-score signal predicts price moves
    beyond random funding-rate noise."""
    rng = np.random.default_rng(seed=42)
    base_funding = df["funding_rate"].values.copy()
    random_alphas = []
    for it in range(n_iter):
        shuf = df.copy()
        shuf["funding_rate"] = rng.permutation(base_funding)
        sim = simulate_acceleration(shuf, train_frac=0.5, **rule_params)
        if sim.get("error"):
            random_alphas.append(0.0)
        else:
            random_alphas.append(sim["alpha_pct"])
        if (it + 1) % 25 == 0:
            log.info("  perm test %d/%d (running mean=%.2f)",
                     it + 1, n_iter, np.mean(random_alphas))
    arr = np.array(random_alphas)
    p_one_sided = float((arr >= real_alpha).sum() / len(arr))
    return {
        "n_iter": n_iter, "real_alpha_pct": real_alpha,
        "random_alpha_mean": round(float(arr.mean()), 3),
        "random_alpha_std": round(float(arr.std()), 3),
        "perm_p": round(p_one_sided, 4),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["COMPUSDT", "SOLUSDT", "ETCUSDT"])
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--exit-z", type=float, default=0.5)
    p.add_argument("--max-hold", type=int, default=15)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(lookback=args.lookback, entry_z=args.entry_z,
                       exit_z=args.exit_z, max_hold=args.max_hold,
                       sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                       capital=args.capital)

    summary_rows = []
    for sym in args.symbols:
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        df = load_funding(sym)
        real_sim = simulate_acceleration(df, train_frac=args.train_frac, **rule_params)
        log.info("[%s] perm test n=%d (real alpha=%.2f sharpe=%.2f trades=%d)",
                 sym, args.n_iter_perm, real_sim["alpha_pct"],
                 real_sim["sharpe_ann"], real_sim["n_trades"])
        perm = permutation_test(df, n_iter=args.n_iter_perm,
                                 real_alpha=real_sim["alpha_pct"], **rule_params)
        result = {
            "symbol": sym, "paradigm": PARADIGM, "phase": "R-3_robustness",
            "config": rule_params | {"train_frac": args.train_frac},
            "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            "real_metrics": real_sim, "permutation": perm,
        }
        out_path = OUT_DIR / f"r3_robust__{sym}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))
        log.info("%s alpha=%.2f sharpe=%.2f perm_p=%.4f random_mean=%.2f",
                 sym, real_sim["alpha_pct"], real_sim["sharpe_ann"],
                 perm["perm_p"], perm["random_alpha_mean"])
        summary_rows.append({
            "symbol": sym,
            "alpha_pct": real_sim["alpha_pct"],
            "sharpe_ann": real_sim["sharpe_ann"],
            "max_dd_pct": real_sim["max_dd_pct"],
            "win_rate_pct": real_sim["win_rate_pct"],
            "profit_factor": real_sim["profit_factor"],
            "n_trades": real_sim["n_trades"],
            "perm_p": perm["perm_p"],
            "perm_random_mean": perm["random_alpha_mean"],
        })

    if summary_rows:
        df_sum = pd.DataFrame(summary_rows)
        df_sum.to_csv(OUT_DIR / "r3_summary.csv", index=False)
        print("\n=== R-3 Summary ===")
        print(df_sum.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
