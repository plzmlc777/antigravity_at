#!/usr/bin/env python3
"""Phase R-3 robustness for vol_regime_breakout (n=200 perm test, COMP/SOL)."""
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

from scripts.poc_vol_regime_breakout import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, simulate_vol_regime_breakout,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_vol_regime_breakout_r3")


def permutation_test(df: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    """Shuffle 5m return series. Destroys vol-regime + breakout structure
    while preserving marginal return distribution."""
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
        # rebuild high/low from close (approximation: use close as midpoint, original hl range)
        # simpler: just shuffle high and low same indices as close
        shuf["high"] = pd.Series(new_close, index=df.index)
        shuf["low"] = pd.Series(new_close, index=df.index)
        sim = simulate_vol_regime_breakout(shuf, train_frac=0.5, **rule_params)
        if sim.get("error"):
            random_alphas.append(0.0)
        else:
            random_alphas.append(sim["alpha_pct"])
        if (it + 1) % 50 == 0:
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
    p.add_argument("--symbols", nargs="+", default=["COMPUSDT", "SOLUSDT"])
    p.add_argument("--vol-window", type=int, default=288)
    p.add_argument("--regime-window", type=int, default=8640)
    p.add_argument("--vol-pctl", type=float, default=0.10)
    p.add_argument("--breakout-lookback", type=int, default=72)
    p.add_argument("--hold-bars", type=int, default=72)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--reverse-sign", action="store_true", default=True)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(vol_window=args.vol_window, regime_window=args.regime_window,
                       vol_pctl=args.vol_pctl, breakout_lookback=args.breakout_lookback,
                       hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                       fee_rate=args.fee_rate, capital=args.capital,
                       reverse_sign=args.reverse_sign)

    summary_rows = []
    for sym in args.symbols:
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        df = load_ohlcv_5m(sym)
        real_sim = simulate_vol_regime_breakout(df, train_frac=args.train_frac,
                                                  **rule_params)
        log.info("[%s] perm test n=%d (real alpha=%.2f)", sym, args.n_iter_perm,
                 real_sim["alpha_pct"])
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
