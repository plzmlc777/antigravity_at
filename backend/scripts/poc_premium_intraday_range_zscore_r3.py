#!/usr/bin/env python3
"""Phase R-3 robustness for premium_intraday_range_zscore (n=200 perm test).

Permutation strategy: shuffle premium high/low rows together (preserve
the per-day high>low relationship but break time-of-event vs price). Tests
whether timing of extreme range events truly predicts price direction.

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

from scripts.poc_premium_intraday_range_zscore import (  # noqa: E402
    PARADIGM, OUT_DIR, load_close_1d, load_premium_ohlc, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_premium_intraday_range_zscore_r3")


def permutation_test(close, prem_ohlc, n_iter, real_alpha, **rule_params):
    rng = np.random.default_rng(seed=42)
    base = prem_ohlc.copy()
    idx = base.index
    random_alphas = []
    for it in range(n_iter):
        order = rng.permutation(len(base))
        shuf = pd.DataFrame(base.values[order], index=idx, columns=base.columns)
        sim = simulate(close, shuf, train_frac=0.5, **rule_params)
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
                   default=["SOLUSDT", "LDOUSDT", "DOGEUSDT", "UNIUSDT"])
    p.add_argument("--zwin", type=int, default=30)
    p.add_argument("--ret-lookback", type=int, default=5)
    p.add_argument("--entry-z", type=float, default=1.5)
    p.add_argument("--hold-days", type=int, default=5)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--mode", default="follow")
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(zwin=args.zwin, ret_lookback=args.ret_lookback,
                       entry_z=args.entry_z, hold_days=args.hold_days,
                       sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                       capital=args.capital, mode=args.mode)

    summary = []
    for sym in args.symbols:
        try:
            close = load_close_1d(sym)
            prem = load_premium_ohlc(sym)
            real = simulate(close, prem, train_frac=0.5, **rule_params)
            real_alpha = float(real["alpha_pct"])
            log.info("%s real: alpha=%.2f sharpe=%.2f trades=%d",
                     sym, real_alpha, real["sharpe_ann"], real["n_trades"])
            log.info("%s starting perm test n=%d ...", sym, args.n_iter_perm)
            perm = permutation_test(close, prem, args.n_iter_perm, real_alpha,
                                    **rule_params)
            sigma = ((real_alpha - perm["random_alpha_mean"]) / max(perm["random_alpha_std"], 0.001))
            verdict = "PASS" if perm["perm_p"] <= 0.05 and sigma >= 4 else "FAIL"
            out = {
                "paradigm": PARADIGM, "phase": "R-3_robustness",
                "symbol": sym, "mode": args.mode,
                "config": vars(args), "real": real, "perm": perm,
                "sigma": round(sigma, 2), "verdict": verdict,
                "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            tag = f"r3_{args.mode}_{sym}_z{args.entry_z}_rl{args.ret_lookback}_h{args.hold_days}"
            (OUT_DIR / f"{tag}.json").write_text(json.dumps(out, indent=2, default=str))
            summary.append({"symbol": sym, "real_alpha": real_alpha,
                            "perm_p": perm["perm_p"], "sigma": round(sigma, 2),
                            "verdict": verdict})
            log.info("%s perm_p=%.4f random_mean=%.2f real=%.2f (%.1fσ) → %s",
                     sym, perm["perm_p"], perm["random_alpha_mean"], real_alpha, sigma,
                     verdict)
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)

    print("\n=== R-3 Summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
