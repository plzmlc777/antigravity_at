#!/usr/bin/env python3
"""Phase R-3 robustness for funding_dispersion (n=200 perm test).

Permutation test: shuffle target symbol's price-change series (preserving
marginal return distribution) → regenerate target's mark_price path → re-run
simulation with the SAME pre-computed cross-section z-score signal (xs_z is
derived from funding_rate cross-section, which is unchanged).

This isolates whether the entry trigger (xs_z extreme) actually predicts
future price moves of the target — beyond random walk + downside-protection
artifacts seen in 4 prior multi-symbol-consistency-but-perm-fail graveyard.
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

from scripts.poc_funding_dispersion import (  # noqa: E402
    PARADIGM, OUT_DIR, DEFAULT_UNIVERSE,
    load_funding_universe, compute_xs_zscores, simulate_xs_z_reversal,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_funding_dispersion_r3")


def permutation_test_target(
    rates: pd.DataFrame,
    prices: pd.DataFrame,
    xs_z: pd.DataFrame,
    target_symbol: str,
    n_iter: int,
    real_alpha: float,
    rule_params: dict,
) -> dict:
    """Shuffle target's price returns, regenerate close path, re-simulate."""
    rng = np.random.default_rng(seed=42)
    target_prices = prices[target_symbol].values
    target_returns = np.diff(target_prices) / target_prices[:-1]

    random_alphas = []
    for it in range(n_iter):
        shuf_returns = rng.permutation(target_returns)
        new_prices = np.empty_like(target_prices)
        new_prices[0] = target_prices[0]
        for k, r in enumerate(shuf_returns):
            new_prices[k + 1] = new_prices[k] * (1 + r)
        prices_shuf = prices.copy()
        prices_shuf[target_symbol] = new_prices
        sim = simulate_xs_z_reversal(
            rates, prices_shuf, xs_z, target_symbol, **rule_params,
        )
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
    p.add_argument("--symbols", nargs="+", default=["ETCUSDT", "UNIUSDT", "LDOUSDT"])
    p.add_argument("--universe", nargs="+", default=DEFAULT_UNIVERSE)
    p.add_argument("--entry-z", type=float, default=1.0)
    p.add_argument("--exit-z", type=float, default=0.2)
    p.add_argument("--max-hold", type=int, default=6)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rates, prices = load_funding_universe(args.universe)
    xs_z = compute_xs_zscores(rates)

    rule_params = dict(
        entry_z=args.entry_z, exit_z=args.exit_z, max_hold=args.max_hold,
        sl_pct=args.sl_pct, fee_rate=args.fee_rate,
        capital=args.capital, train_frac=args.train_frac,
    )

    summary_rows = []
    for sym in args.symbols:
        if sym not in rates.columns:
            log.warning("%s not in universe — skipping", sym); continue
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        real_sim = simulate_xs_z_reversal(rates, prices, xs_z, sym, **rule_params)
        log.info("[%s] perm test n=%d (real alpha=%.2f sharpe=%.2f trades=%d)",
                 sym, args.n_iter_perm, real_sim["alpha_pct"],
                 real_sim["sharpe_ann"], real_sim["n_trades"])
        perm = permutation_test_target(
            rates, prices, xs_z, sym,
            n_iter=args.n_iter_perm,
            real_alpha=real_sim["alpha_pct"],
            rule_params=rule_params,
        )
        result = {
            "symbol": sym, "paradigm": PARADIGM, "phase": "R-3_robustness",
            "config": rule_params,
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
