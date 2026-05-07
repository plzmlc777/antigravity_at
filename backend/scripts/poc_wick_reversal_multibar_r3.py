#!/usr/bin/env python3
"""Phase R-3 robustness for wick_reversal_multibar (n=200 perm test).

Same shuffle approach as Q3 #2 (high/low pair shuffled, open/close
preserved). Goal: verify whether multi-bar averaging reduces random_std.
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

from scripts.poc_wick_reversal_multibar import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlc_5m, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_wick_reversal_multibar_r3")


def permutation_test(df, n_iter, real_alpha, **rule_params):
    rng = np.random.default_rng(seed=42)
    base_high = df["high"].values.astype(float).copy()
    base_low = df["low"].values.astype(float).copy()
    base_open = df["open"].values.astype(float).copy()
    base_close = df["close"].values.astype(float).copy()
    n = len(df)
    random_alphas = []
    for it in range(n_iter):
        perm_idx = rng.permutation(n)
        new_high = base_high[perm_idx]
        new_low = base_low[perm_idx]
        body_top = np.maximum(base_open, base_close)
        body_bot = np.minimum(base_open, base_close)
        new_high = np.maximum(new_high, body_top)
        new_low = np.minimum(new_low, body_bot)
        shuf_df = df.copy()
        shuf_df["high"] = new_high
        shuf_df["low"] = new_low
        sim = simulate(shuf_df, train_frac=0.5, **rule_params)
        if sim.get("error"):
            random_alphas.append(0.0)
        else:
            random_alphas.append(sim["alpha_pct"])
        if (it + 1) % 25 == 0:
            log.info("  perm %d/%d running_mean=%.2f real=%.2f",
                     it + 1, n_iter, float(np.mean(random_alphas)), real_alpha)
    arr = np.array(random_alphas)
    p_one_sided = float((arr >= real_alpha).sum() / len(arr))
    return {
        "n_iter": n_iter, "real_alpha_pct": real_alpha,
        "random_alpha_mean": round(float(arr.mean()), 3),
        "random_alpha_std": round(float(arr.std()), 3),
        "random_alpha_max": round(float(arr.max()), 3),
        "perm_p": round(p_one_sided, 4),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SOLUSDT"])
    p.add_argument("--n-bars", type=int, default=2)
    p.add_argument("--wick-thresh", type=float, default=0.35)
    p.add_argument("--prior-lookback", type=int, default=12)
    p.add_argument("--prior-move-pct", type=float, default=0.03)
    p.add_argument("--hold-bars", type=int, default=12)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(
        n_bars=args.n_bars, wick_thresh=args.wick_thresh,
        prior_lookback=args.prior_lookback,
        prior_move_pct=args.prior_move_pct, hold_bars=args.hold_bars,
        sl_pct=args.sl_pct, fee_rate=args.fee_rate, capital=args.capital,
    )

    summary = []
    for sym in args.symbols:
        try:
            df = load_ohlc_5m(sym)
            real = simulate(df, train_frac=0.5, **rule_params)
            real_alpha = float(real["alpha_pct"])
            log.info("%s real: alpha=%.2f sharpe=%.2f trades=%d",
                     sym, real_alpha, real.get("sharpe_ann", 0), real.get("n_trades", 0))
            log.info("%s starting perm test n=%d ...", sym, args.n_iter_perm)
            perm = permutation_test(df, args.n_iter_perm, real_alpha, **rule_params)
            sigma = ((real_alpha - perm["random_alpha_mean"]) /
                     max(perm["random_alpha_std"], 0.001))
            verdict = "PASS" if perm["perm_p"] <= 0.05 and sigma >= 4 else "FAIL"
            out = {
                "paradigm": PARADIGM, "symbol": sym, "config": vars(args),
                "real": real, "perm": perm,
                "sigma": round(sigma, 2), "verdict": verdict,
                "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            (OUT_DIR / f"r3_{sym}_n{args.n_bars}_wt{args.wick_thresh}.json").write_text(
                json.dumps(out, indent=2, default=str))
            summary.append({"symbol": sym, "real_alpha": real_alpha,
                            "perm_p": perm["perm_p"], "sigma": round(sigma, 2),
                            "verdict": verdict,
                            "random_mean": perm["random_alpha_mean"],
                            "random_std": perm["random_alpha_std"]})
            log.info("%s perm_p=%.4f random_mean=%.2f std=%.2f real=%.2f (%.1fσ) → %s",
                     sym, perm["perm_p"], perm["random_alpha_mean"],
                     perm["random_alpha_std"], real_alpha, sigma, verdict)
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    print("\n=== R-3 Summary ===")
    print(json.dumps(summary, indent=2))
    pd.DataFrame(summary).to_csv(OUT_DIR / "r3_summary.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
