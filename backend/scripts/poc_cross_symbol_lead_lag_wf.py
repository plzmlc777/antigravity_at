#!/usr/bin/env python3
"""Walk-forward 6-fold robustness for cross_symbol_lead_lag.

Splits the 1y OOS window into 6 equal chunks (~66 days each). For each
chunk, simulates the strategy starting fresh from capital=1M, with no
in-sample dependency (paradigm is rule-based, not parameter-fit). Counts
chunks where the strategy produces positive alpha vs buy-hold.

Master plan §2-B PASS criterion: ≥ 5/6 positive folds.

Companion to scripts/poc_cross_symbol_lead_lag_r3.py (perm test).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.poc_cross_symbol_lead_lag import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_5m, simulate_lead_lag,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poc_cross_symbol_lead_lag_wf")


def walk_forward_6fold(close_alt: pd.Series, close_btc: pd.Series, *,
                       n_folds: int = 6, train_frac: float = 0.5,
                       **rule_params) -> list[dict]:
    """Split OOS portion of joined data into n_folds equal chunks. For each
    chunk, simulate the strategy from scratch within only that chunk's data.

    Note: rule-based paradigm has no in-sample fitting, so chunk-only
    simulation is valid. Each fold gets a fresh capital=1M.
    """
    joined = pd.concat({"alt": close_alt, "btc": close_btc}, axis=1).dropna()
    n_total = len(joined)
    split = int(n_total * train_frac)
    oos = joined.iloc[split:]

    fold_size = len(oos) // n_folds
    folds = []
    for k in range(n_folds):
        start = k * fold_size
        end = (k + 1) * fold_size if k < n_folds - 1 else len(oos)
        fold_data = oos.iloc[start:end]
        # Re-simulate within this fold only (train_frac=0 so all of fold is "test")
        # We pass entire fold data as if it were the full series, train_frac=0
        sim = simulate_lead_lag(
            fold_data["alt"], fold_data["btc"],
            train_frac=0.0, **rule_params,
        )
        sim["fold"] = k + 1
        sim["fold_start"] = str(fold_data.index[0])
        sim["fold_end"] = str(fold_data.index[-1])
        sim["fold_n_bars"] = len(fold_data)
        folds.append(sim)
    return folds


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
    p.add_argument("--n-folds", type=int, default=6)
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
        log.info("WF %d-fold for %s", args.n_folds, sym)
        alt_df = load_ohlcv_5m(sym)
        folds = walk_forward_6fold(
            alt_df["close"], leader_df["close"],
            n_folds=args.n_folds, train_frac=args.train_frac,
            **rule_params,
        )
        pos_folds = sum(1 for f in folds if f.get("alpha_pct", 0) > 0)
        result = {
            "symbol": sym, "paradigm": PARADIGM, "phase": "WF_robustness",
            "config": rule_params | {"train_frac": args.train_frac, "leader": args.leader,
                                      "n_folds": args.n_folds},
            "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            "wf_positive_folds": pos_folds,
            "wf_total_folds": args.n_folds,
            "folds": folds,
        }
        out_path = OUT_DIR / f"wf_robust__{sym}.json"
        out_path.write_text(json.dumps(result, indent=2, default=str))
        log.info("%s WF positive folds: %d/%d", sym, pos_folds, args.n_folds)
        for f in folds:
            log.info("  fold %d (%s ~ %s): alpha=%.2f sharpe=%.2f trades=%d",
                     f["fold"], f["fold_start"][:10], f["fold_end"][:10],
                     f.get("alpha_pct", 0), f.get("sharpe_ann", 0), f.get("n_trades", 0))
        summary_rows.append({
            "symbol": sym,
            "wf_positive_folds": pos_folds,
            "wf_total_folds": args.n_folds,
            "fold_alphas": [round(f.get("alpha_pct", 0), 2) for f in folds],
        })

    if summary_rows:
        df_sum = pd.DataFrame(summary_rows)
        df_sum.to_csv(OUT_DIR / "wf_summary.csv", index=False)
        print("\n=== WF Summary ===")
        print(df_sum.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
