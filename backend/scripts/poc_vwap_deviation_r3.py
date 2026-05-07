#!/usr/bin/env python3
"""Phase R-3 robustness for vwap_deviation (n=200 perm test)."""
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

from scripts.poc_vwap_deviation import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_vwap_deviation_r3")


def permutation_test(df, n_iter, real_alpha, **rule_params):
    rng = np.random.default_rng(seed=42)
    base_vol = df["volume"].values.astype(float).copy()
    n = len(df)
    random_alphas = []
    for it in range(n_iter):
        perm_idx = rng.permutation(n)
        new_vol = base_vol[perm_idx]
        shuf_df = df.copy()
        shuf_df["volume"] = new_vol
        shuf_df["pv"] = shuf_df["close"] * shuf_df["volume"]
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
    p.add_argument("--symbols", nargs="+", default=["AXSUSDT", "SOLUSDT"])
    p.add_argument("--vwap-window", type=int, default=144)
    p.add_argument("--zwin", type=int, default=288)
    p.add_argument("--entry-z", type=float, default=3.0)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--mode", default="follow")
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(
        vwap_window=args.vwap_window, zwin=args.zwin,
        entry_z=args.entry_z, hold_bars=args.hold_bars,
        sl_pct=args.sl_pct, fee_rate=args.fee_rate,
        capital=args.capital, mode=args.mode,
    )

    summary = []
    for sym in args.symbols:
        try:
            df = load_ohlcv_5m(sym)
            real = simulate(df, train_frac=0.5, **rule_params)
            real_alpha = float(real["alpha_pct"])
            log.info("%s real: alpha=%.2f sharpe=%.2f trades=%d",
                     sym, real_alpha, real.get("sharpe_ann", 0), real.get("n_trades", 0))
            log.info("%s starting perm test n=%d ...", sym, args.n_iter_perm)
            perm = permutation_test(df, args.n_iter_perm, real_alpha, **rule_params)
            sigma = ((real_alpha - perm["random_alpha_mean"]) /
                     max(perm["random_alpha_std"], 0.001))
            verdict = "PASS" if perm["perm_p"] <= 0.05 and sigma >= 4 else "FAIL"
            (OUT_DIR / f"r3_{sym}.json").write_text(
                json.dumps({"paradigm": PARADIGM, "symbol": sym, "config": vars(args),
                            "real": real, "perm": perm,
                            "sigma": round(sigma, 2), "verdict": verdict,
                            "evaluated_at": datetime.now(tz=timezone.utc).isoformat()},
                           indent=2, default=str))
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
