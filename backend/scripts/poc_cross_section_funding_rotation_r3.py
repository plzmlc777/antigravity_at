#!/usr/bin/env python3
"""Phase R-3 robustness for cross_section_funding_rotation (n=200 perm test).

Permutation strategy: at each rebalance, shuffle the funding rate values
across symbols (random rotation pick instead of true funding rank). This
tests whether funding rate truly identifies which symbols out/under-perform,
or if the alpha is just noise from picking 1-3 random alts in a bear basket.

PASS: perm_p ≤ 0.05 AND ≥ 4σ.
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

from scripts.poc_cross_section_funding_rotation import (  # noqa: E402
    PARADIGM, OUT_DIR, load_funding_close_panel, simulate_rotation,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_cross_section_funding_rotation_r3")


def permutation_test(df, symbols, n_iter, real_alpha, **rule_params):
    rng = np.random.default_rng(seed=42)
    fund_cols = [f"fund_{s}" for s in symbols if f"fund_{s}" in df.columns]
    base = df[fund_cols].copy()
    random_alphas = []
    for it in range(n_iter):
        # Shuffle funding values WITHIN each row (across symbols)
        shuf = base.copy()
        vals = shuf.values
        for r in range(vals.shape[0]):
            perm = rng.permutation(vals.shape[1])
            vals[r] = vals[r, perm]
        shuf.iloc[:, :] = vals
        df_shuf = df.copy()
        df_shuf[fund_cols] = shuf
        sim = simulate_rotation(df_shuf, symbols, train_frac=0.5, **rule_params)
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+",
                   default=["AVAXUSDT", "AXSUSDT", "BTCUSDT", "COMPUSDT",
                            "DOGEUSDT", "ETCUSDT", "ETHUSDT", "HBARUSDT",
                            "ICPUSDT", "LDOUSDT", "LINKUSDT", "SOLUSDT",
                            "UNIUSDT", "WLDUSDT"])
    p.add_argument("--freq", default="1D")
    p.add_argument("--top-k", type=int, default=1)
    p.add_argument("--hold-periods", type=int, default=14)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--mode", default="reverse")
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading panel for %d symbols at freq=%s ...", len(args.symbols), args.freq)
    df = load_funding_close_panel(args.symbols, freq=args.freq)
    log.info("Panel: %d rows × %d cols", len(df), df.shape[1])

    rule_params = dict(top_k=args.top_k, hold_periods=args.hold_periods,
                       fee_rate=args.fee_rate, capital=args.capital,
                       mode=args.mode)

    real = simulate_rotation(df, args.symbols, train_frac=0.5, **rule_params)
    real_alpha = float(real["alpha_pct"])
    log.info("Real: alpha=%.2f sharpe=%.2f rebalances=%d",
             real_alpha, real["sharpe_ann"], real["n_trades"])

    log.info("Starting perm test n=%d ...", args.n_iter_perm)
    perm = permutation_test(df, args.symbols, args.n_iter_perm, real_alpha,
                            **rule_params)
    sigma = ((real_alpha - perm["random_alpha_mean"]) / max(perm["random_alpha_std"], 0.001))
    verdict = "PASS" if perm["perm_p"] <= 0.05 and sigma >= 4 else "FAIL"
    out = {
        "paradigm": PARADIGM, "phase": "R-3_robustness",
        "config": vars(args), "real": real, "perm": perm,
        "sigma": round(sigma, 2), "verdict": verdict,
        "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    tag = f"r3_{args.mode}_k{args.top_k}_h{args.hold_periods}"
    (OUT_DIR / f"{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    log.info("perm_p=%.4f random_mean=%.2f real=%.2f (%.1fσ) → %s",
             perm["perm_p"], perm["random_alpha_mean"], real_alpha, sigma,
             verdict)
    print("\n=== R-3 Result ===")
    print(json.dumps({"k": args.top_k, "h": args.hold_periods, "mode": args.mode,
                      "real_alpha": real_alpha, "perm_p": perm["perm_p"],
                      "sigma": round(sigma, 2), "verdict": verdict}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
