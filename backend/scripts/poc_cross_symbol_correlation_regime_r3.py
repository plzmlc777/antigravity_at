#!/usr/bin/env python3
"""Phase R-3 robustness for cross_symbol_correlation_regime.

Permutation test design: shuffle target symbol's 5m return series → regenerate
target's close path → re-run simulation with the SAME pre-computed universe-
level regime signal (avg_corr unchanged because universe data unchanged from
target's perspective; target is one of N+1 columns but its shuffled returns
do not influence the pre-computed regime series, which is held fixed).

This tests: conditional on the regime classification at time t, does the
target's recent direction signal predict future returns? If yes (perm_p ≤
0.05), the regime+direction joint signal is real. If no, the alpha is small-
sample noise or buy-hold drift.
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

from scripts.poc_cross_symbol_correlation_regime import (  # noqa: E402
    PARADIGM, OUT_DIR, DEFAULT_UNIVERSE,
    load_universe_returns_5m, rolling_avg_pairwise_corr,
    simulate_xs_corr_regime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_xs_corr_r3")


def permutation_test_target(
    closes: pd.DataFrame,
    rets: pd.DataFrame,
    avg_corr: pd.Series,
    target_symbol: str,
    n_iter: int,
    real_alpha: float,
    rule_params: dict,
) -> dict:
    """Shuffle target's 5m returns, regenerate target close path, re-simulate."""
    rng = np.random.default_rng(seed=42)
    target_close = closes[target_symbol].values
    target_returns = np.diff(target_close) / target_close[:-1]

    random_alphas = []
    for it in range(n_iter):
        shuf_returns = rng.permutation(target_returns)
        new_close = np.empty_like(target_close)
        new_close[0] = target_close[0]
        for k, r in enumerate(shuf_returns):
            new_close[k + 1] = new_close[k] * (1 + r)
        # Replace target column in closes with shuffled close path.
        closes_shuf = closes.copy()
        closes_shuf[target_symbol] = new_close
        # rets_shuf not needed for this simulation (only closes and avg_corr used).
        sim = simulate_xs_corr_regime(
            closes_shuf, rets, avg_corr, target_symbol, **rule_params,
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
    p.add_argument("--symbols", nargs="+", default=["LDOUSDT", "UNIUSDT", "DOGEUSDT"])
    p.add_argument("--universe", nargs="+", default=DEFAULT_UNIVERSE)
    p.add_argument("--corr-window", type=int, default=288)
    p.add_argument("--hi-thresh", type=float, default=0.90)
    p.add_argument("--lo-thresh", type=float, default=0.50)
    p.add_argument("--dir-lookback", type=int, default=12)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--direction", choices=["fade", "follow"], default="fade")
    p.add_argument("--regime-filter", choices=["both", "hi_only", "lo_only"],
                   default="hi_only")
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    closes, rets = load_universe_returns_5m(args.universe)
    avg_corr = rolling_avg_pairwise_corr(rets, args.corr_window).dropna()

    rule_params = dict(
        hi_thresh=args.hi_thresh, lo_thresh=args.lo_thresh,
        dir_lookback=args.dir_lookback, hold_bars=args.hold_bars,
        sl_pct=args.sl_pct, fee_rate=args.fee_rate,
        capital=args.capital, train_frac=args.train_frac,
        direction=args.direction, regime_filter=args.regime_filter,
    )

    summary_rows = []
    for sym in args.symbols:
        if sym not in closes.columns:
            log.warning("%s not in universe — skipping", sym)
            continue
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        real_sim = simulate_xs_corr_regime(closes, rets, avg_corr, sym, **rule_params)
        log.info("[%s] perm test n=%d (real alpha=%.2f sharpe=%.2f)",
                 sym, args.n_iter_perm, real_sim["alpha_pct"], real_sim["sharpe_ann"])
        perm = permutation_test_target(
            closes, rets, avg_corr, sym,
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
