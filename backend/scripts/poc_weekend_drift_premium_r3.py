#!/usr/bin/env python3
"""Phase R-3 robustness for weekend_drift_premium (n=200 perm test).

Permutation: shuffle daily premium series in time. Keep close (price) intact
+ DoW labels intact. Tests whether Friday + premium follow signal is genuine
or coincidental.

PASS criterion: perm_p ≤ 0.05.
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

from scripts.poc_weekend_drift_premium import (  # noqa: E402
    PARADIGM, OUT_DIR, load_close_1d, load_premium_1d, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_weekend_drift_premium_r3")


def permutation_test(close: pd.Series, premium: pd.Series, n_iter: int,
                     real_alpha: float, **rule_params) -> dict:
    rng = np.random.default_rng(seed=42)
    base = premium.values.astype(float)
    random_alphas = []
    for it in range(n_iter):
        shuf = rng.permutation(base)
        shuf_series = pd.Series(shuf, index=premium.index)
        sim = simulate(close, shuf_series, train_frac=0.5, **rule_params)
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
                   default=["HBARUSDT", "LDOUSDT", "AXSUSDT", "DOGEUSDT", "UNIUSDT"])
    p.add_argument("--zwin", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=1.5)
    p.add_argument("--hold-days", type=int, default=3)
    p.add_argument("--entry-dow", type=int, default=4)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--mode", default="follow")
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(zwin=args.zwin, entry_z=args.entry_z,
                       hold_days=args.hold_days, entry_dow=args.entry_dow,
                       sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                       capital=args.capital, mode=args.mode)

    for sym in args.symbols:
        try:
            close = load_close_1d(sym)
            premium = load_premium_1d(sym)
            real = simulate(close, premium, train_frac=0.5, **rule_params)
            real_alpha = float(real["alpha_pct"])
            log.info("%s real: alpha=%.2f sharpe=%.2f trades=%d",
                     sym, real_alpha, real["sharpe_ann"], real["n_trades"])
            log.info("%s starting perm n=%d ...", sym, args.n_iter_perm)
            perm = permutation_test(close, premium, args.n_iter_perm, real_alpha, **rule_params)
            out = {
                "paradigm": PARADIGM, "phase": "R-3_robustness",
                "symbol": sym, "mode": args.mode,
                "config": vars(args), "real": real, "perm": perm,
                "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            tag = f"r3_{args.mode}_dow{args.entry_dow}_{sym}_z{args.entry_z}_h{args.hold_days}"
            (OUT_DIR / f"{tag}.json").write_text(json.dumps(out, indent=2, default=str))
            sigma = ((real_alpha - perm["random_alpha_mean"]) / max(perm["random_alpha_std"], 0.001))
            log.info("%s perm_p=%.4f random_mean=%.2f real=%.2f (%.1fσ) → %s",
                     sym, perm["perm_p"], perm["random_alpha_mean"], real_alpha, sigma,
                     "PASS" if perm["perm_p"] <= 0.05 else "FAIL")
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
