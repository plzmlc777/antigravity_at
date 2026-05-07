#!/usr/bin/env python3
"""Phase R-3 robustness for oi_funding_corr_regime (n=200 perm test).

Permutation: shuffle OPEN_INTEREST series temporally — destroys d_oi
timing AND its correlation with funding while preserving each series'
marginal distribution. If real signal is timing-dependent (real flow
vs noise), shuffled OI should produce alpha distribution centered on 0.
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

from scripts.poc_oi_funding_corr_regime import (  # noqa: E402
    PARADIGM, OUT_DIR, build_8h_frame, load_close_5m, load_oi_5m,
    load_funding_8h, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_oi_funding_corr_regime_r3")


def permutation_test(joined: pd.DataFrame, n_iter: int, real_alpha: float,
                     **rule_params) -> dict:
    rng = np.random.default_rng(seed=42)
    base_oi = joined["open_interest"].values.astype(float).copy()
    random_alphas: list[float] = []
    for it in range(n_iter):
        shuf = rng.permutation(base_oi)
        shuf_df = joined.copy()
        shuf_df["open_interest"] = shuf
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+",
                   default=["DOGEUSDT", "SOLUSDT", "UNIUSDT", "HBARUSDT"])
    p.add_argument("--zwin", type=int, default=30)
    p.add_argument("--corr-win", type=int, default=30)
    p.add_argument("--entry-z", type=float, default=1.0)
    p.add_argument("--entry-z-fund", type=float, default=0.5)
    p.add_argument("--regime-thresh", type=float, default=0.0)
    p.add_argument("--hold-periods", type=int, default=6)
    p.add_argument("--sl-pct", type=float, default=0.05)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--mode", default="fade_long_pos")
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(
        zwin=args.zwin, corr_win=args.corr_win,
        entry_z=args.entry_z, entry_z_fund=args.entry_z_fund,
        regime_thresh=args.regime_thresh,
        hold_periods=args.hold_periods, sl_pct=args.sl_pct,
        fee_rate=args.fee_rate, capital=args.capital,
        mode=args.mode,
    )

    summary = []
    for sym in args.symbols:
        try:
            close_df = load_close_5m(sym)
            oi_df = load_oi_5m(sym)
            fund_df = load_funding_8h(sym)
            joined = build_8h_frame(close_df, oi_df, fund_df)
            log.info("%s 8h frame: %d periods", sym, len(joined))

            real = simulate(joined, train_frac=0.5, **rule_params)
            real_alpha = float(real["alpha_pct"])
            log.info("%s real: alpha=%.2f sharpe=%.2f trades=%d",
                     sym, real_alpha, real.get("sharpe_ann", 0), real.get("n_trades", 0))

            log.info("%s starting perm test n=%d ...", sym, args.n_iter_perm)
            perm = permutation_test(joined, args.n_iter_perm, real_alpha, **rule_params)
            sigma = ((real_alpha - perm["random_alpha_mean"]) /
                     max(perm["random_alpha_std"], 0.001))
            verdict = "PASS" if perm["perm_p"] <= 0.05 and sigma >= 4 else "FAIL"
            out = {
                "paradigm": PARADIGM, "phase": "R-3_robustness",
                "symbol": sym, "mode": args.mode,
                "config": vars(args), "real": real, "perm": perm,
                "sigma": round(sigma, 2), "verdict": verdict,
                "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
            tag = f"r3_{args.mode}_{sym}_ez{args.entry_z}_h{args.hold_periods}"
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
    summary_path = OUT_DIR / "r3_summary.csv"
    pd.DataFrame(summary).to_csv(summary_path, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
