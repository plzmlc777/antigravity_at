#!/usr/bin/env python3
"""Phase R-3 robustness for oi_price_decoupling (n=100 perm test, top candidates).

Permutation strategy: shuffle return series AND OI delta series independently
(preserves marginal distributions but destroys joint time structure). Real
signal lies in the joint price-OI pattern at extreme z; if that's destroyed,
random_alpha distribution should center near 0 with real_alpha well above.

PASS criterion: perm_p ≤ 0.05 (real alpha exceeds ≥95% of randoms).
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

from scripts.poc_oi_price_decoupling import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, load_oi_5m, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_oi_price_decoupling_r3")


def permutation_test(df: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    """Shuffle close-to-close log_returns AND oi pct_change independently.
    Reconstruct price/OI series from shuffled increments → destroys joint
    structure but preserves each marginal."""
    rng = np.random.default_rng(seed=42)
    base_close = df["close"].values.astype(float)
    base_oi = df["open_interest"].values.astype(float)
    log_rets = np.diff(np.log(base_close))
    oi_pct = np.diff(base_oi) / base_oi[:-1]
    random_alphas = []
    for it in range(n_iter):
        shuf_lr = rng.permutation(log_rets)
        shuf_oi = rng.permutation(oi_pct)
        new_close = np.empty_like(base_close)
        new_close[0] = base_close[0]
        new_close[1:] = base_close[0] * np.exp(np.cumsum(shuf_lr))
        new_oi = np.empty_like(base_oi)
        new_oi[0] = base_oi[0]
        new_oi[1:] = base_oi[0] * np.cumprod(1.0 + shuf_oi)
        shuf = df.copy()
        shuf["close"] = new_close
        shuf["open_interest"] = new_oi
        sim = simulate(shuf, train_frac=0.5, **rule_params)
        if sim.get("error"):
            random_alphas.append(0.0)
        else:
            random_alphas.append(sim["alpha_pct"])
        if (it + 1) % 20 == 0:
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
    p.add_argument("--symbols", nargs="+", default=["LINKUSDT", "AXSUSDT", "HBARUSDT"])
    p.add_argument("--zwin", type=int, default=288)
    p.add_argument("--entry-z", type=float, default=2.5)
    p.add_argument("--hold-bars", type=int, default=24)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--mode", default="invert_decouple")
    p.add_argument("--n-iter-perm", type=int, default=100)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(zwin=args.zwin, entry_z=args.entry_z,
                       hold_bars=args.hold_bars, sl_pct=args.sl_pct,
                       fee_rate=args.fee_rate, capital=args.capital,
                       mode=args.mode)

    for sym in args.symbols:
        try:
            close_df = load_ohlcv_5m(sym)
            oi_df = load_oi_5m(sym)
            joined = pd.concat([close_df, oi_df], axis=1, join="inner").dropna()
            real = simulate(joined, train_frac=0.5, **rule_params)
            real_alpha = float(real["alpha_pct"])
            log.info("%s real: alpha=%.2f sharpe=%.2f trades=%d",
                     sym, real_alpha, real["sharpe_ann"], real["n_trades"])
            log.info("%s starting perm test n=%d ...", sym, args.n_iter_perm)
            perm = permutation_test(joined, args.n_iter_perm, real_alpha, **rule_params)
            out = {
                "paradigm": PARADIGM, "phase": "R-3_robustness",
                "symbol": sym, "mode": args.mode,
                "config": vars(args), "real": real, "perm": perm,
                "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            tag = f"r3_{args.mode}_{sym}_z{args.entry_z}_h{args.hold_bars}"
            (OUT_DIR / f"{tag}.json").write_text(json.dumps(out, indent=2, default=str))
            log.info("%s perm_p=%.4f random_mean=%.2f real=%.2f → %s",
                     sym, perm["perm_p"], perm["random_alpha_mean"], real_alpha,
                     "PASS" if perm["perm_p"] <= 0.05 else "FAIL")
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
