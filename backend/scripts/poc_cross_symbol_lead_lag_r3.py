#!/usr/bin/env python3
"""Phase R-3 robustness for cross_symbol_lead_lag.

Permutation test: shuffle target alt's 5m return series → regenerate close →
re-simulate with the SAME real BTC leader returns. Tests whether the
BTC-direction conditioned entry actually predicts alt's future returns.
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

from scripts.poc_cross_symbol_lead_lag import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, simulate_lead_lag,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_cross_symbol_lead_lag_r3")


def permutation_test(close_alt: pd.Series, close_btc: pd.Series,
                     n_iter: int, real_alpha: float, **rule_params) -> dict:
    """Shuffle alt's returns, regenerate close, re-simulate."""
    rng = np.random.default_rng(seed=42)
    base_alt = close_alt.values
    base_returns = np.diff(base_alt) / base_alt[:-1]
    random_alphas = []
    for it in range(n_iter):
        shuf_returns = rng.permutation(base_returns)
        new_close = np.empty_like(base_alt)
        new_close[0] = base_alt[0]
        for k, r in enumerate(shuf_returns):
            new_close[k + 1] = new_close[k] * (1 + r)
        sim = simulate_lead_lag(
            pd.Series(new_close, index=close_alt.index),
            close_btc, train_frac=0.5, **rule_params,
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
    p.add_argument("--symbols", nargs="+", default=["DOGEUSDT", "ETCUSDT"])
    p.add_argument("--leader", default="BTCUSDT")
    p.add_argument("--lead-lookback", type=int, default=1)
    p.add_argument("--lead-thresh", type=float, default=0.005)
    p.add_argument("--follow-ratio", type=float, default=0.5)
    p.add_argument("--hold-bars", type=int, default=12)
    p.add_argument("--sl-pct", type=float, default=0.02)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    p.add_argument("--n-iter-perm", type=int, default=200)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rule_params = dict(lead_lookback=args.lead_lookback,
                       lead_thresh=args.lead_thresh,
                       follow_ratio=args.follow_ratio,
                       hold_bars=args.hold_bars,
                       sl_pct=args.sl_pct, fee_rate=args.fee_rate,
                       capital=args.capital)

    log.info("Loading leader %s...", args.leader)
    leader_df = load_ohlcv_5m(args.leader)

    summary_rows = []
    for sym in args.symbols:
        log.info("=" * 60)
        log.info("R-3 robustness for %s", sym)
        alt_df = load_ohlcv_5m(sym)
        joined = pd.concat({"alt": alt_df["close"], "btc": leader_df["close"]},
                           axis=1).dropna()
        real_sim = simulate_lead_lag(joined["alt"], joined["btc"],
                                      train_frac=args.train_frac, **rule_params)
        log.info("[%s] perm test n=%d (real alpha=%.2f sharpe=%.2f trades=%d)",
                 sym, args.n_iter_perm, real_sim["alpha_pct"],
                 real_sim["sharpe_ann"], real_sim["n_trades"])
        perm = permutation_test(joined["alt"], joined["btc"],
                                 n_iter=args.n_iter_perm,
                                 real_alpha=real_sim["alpha_pct"], **rule_params)
        result = {
            "symbol": sym, "paradigm": PARADIGM, "phase": "R-3_robustness",
            "config": rule_params | {"train_frac": args.train_frac, "leader": args.leader},
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
