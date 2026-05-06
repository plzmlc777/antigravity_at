#!/usr/bin/env python3
"""Phase R-3 robustness for partial_autocorr_regime (n=200 perm test).

Permutation test: shuffle target symbol's 5m return series → regenerate close
path → re-run simulation. Tests whether the rolling PACF[2] signal predicts
future returns (vs random walk + drift artifacts).
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

from scripts.poc_partial_autocorr_regime import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, simulate_pacf2_regime,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_partial_autocorr_regime_r3")


def permutation_test(df: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    rng = np.random.default_rng(seed=42)
    base_close = df["close"].values
    base_returns = np.diff(base_close) / base_close[:-1]
    random_alphas = []
    for it in range(n_iter):
        shuf_returns = rng.permutation(base_returns)
        new_close = [base_close[0]]
        for r in shuf_returns:
            new_close.append(new_close[-1] * (1 + r))
        shuf = df.copy()
        shuf["close"] = new_close
        sim = simulate_pacf2_regime(shuf, train_frac=0.5, **rule_params)
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
    p.add_argument("--symbols", nargs="+", default=["ETCUSDT", "UNIUSDT", "LINKUSDT"])
    p.add_argument("--pacf-window", type=int, default=288)
    p.add_argument("--trend-thresh", type=float, default=0.15)
    p.add_argument("--rev-thresh", type=float, default=0.15)
    p.add_argument("--dir-lookback", type=int, default=12)
    p.add_argument("--hold-bars", type=int, default=72)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--n-iter-perm", type=int, default=200)
    p.add_argument("--regime-filter", choices=["both", "trend_only", "rev_only"],
                   default="rev_only")
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(pacf_window=args.pacf_window,
                       trend_thresh=args.trend_thresh,
                       rev_thresh=args.rev_thresh,
                       dir_lookback=args.dir_lookback,
                       hold_bars=args.hold_bars,
                       sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                       capital=args.capital,
                       regime_filter=args.regime_filter)

    summary_rows = []
    for sym in args.symbols:
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        df = load_ohlcv_5m(sym)
        real_sim = simulate_pacf2_regime(df, train_frac=args.train_frac, **rule_params)
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
