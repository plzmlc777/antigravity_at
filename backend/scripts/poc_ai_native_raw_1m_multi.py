#!/usr/bin/env python3
"""R-2 mini-validation runner for ai_native_raw_1m paradigm.

Re-uses the single-symbol PoC pipeline (poc_ai_native_raw_1m.py) on a list of
symbols with identical hyperparameters, then writes an aggregate summary table.

Output:
  backend/runs/research_track/ai_native_raw_1m/poc__{symbol}__metrics.json (one per)
  backend/runs/research_track/ai_native_raw_1m/r2_mini_summary.csv

Usage:
  python -m scripts.poc_ai_native_raw_1m_multi \\
    --symbols HBARUSDT AXSUSDT DOGEUSDT PYTHUSDT
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.poc_ai_native_raw_1m import (  # noqa: E402
    PARADIGM, OUT_DIR, load_ohlcv_1m, build_features, train_predict, simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("r2_mini")


def run_one(symbol: str, *, lookback: int, fwd: int, entry_threshold: float,
            sl_pct: float, tp_pct: float, max_hold_bars: int,
            fee_rate: float, capital: float, train_frac: float
            ) -> dict:
    ohlcv = load_ohlcv_1m(symbol)
    X, y = build_features(ohlcv, lookback=lookback, fwd=fwd)
    preds, train_meta = train_predict(X, y, train_frac=train_frac)
    sim = simulate(
        ohlcv, preds,
        entry_threshold=entry_threshold,
        sl_pct=sl_pct, tp_pct=tp_pct,
        max_hold_bars=max_hold_bars,
        fee_rate=fee_rate, capital=capital,
    )
    metrics = {
        "paradigm": PARADIGM,
        "phase": "R-2_mini",
        "spec_name": f"{symbol}_lookback{lookback}_fwd{fwd}",
        "symbol": symbol,
        "config": {
            "lookback": lookback, "fwd": fwd, "entry_threshold": entry_threshold,
            "sl_pct": sl_pct, "tp_pct": tp_pct, "max_hold_bars": max_hold_bars,
            "fee_rate": fee_rate, "capital": capital, "train_frac": train_frac,
        },
        "train_meta": train_meta,
        **sim,
    }
    out = OUT_DIR / f"poc__{symbol}__metrics.json"
    out.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Wrote %s — alpha=%.2f sharpe=%.2f rank_ic=%.4f trades=%d",
             out, sim["alpha_pct"], sim["sharpe_ann"],
             train_meta["rank_ic"], sim["n_trades"])
    return metrics


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--lookback", type=int, default=120)
    p.add_argument("--fwd", type=int, default=60)
    p.add_argument("--entry-threshold", type=float, default=0.002)
    p.add_argument("--sl-pct", type=float, default=0.06)
    p.add_argument("--tp-pct", type=float, default=0.15)
    p.add_argument("--max-hold-bars", type=int, default=60)
    p.add_argument("--fee-rate", type=float, default=0.0004)
    p.add_argument("--capital", type=float, default=1_000_000.0)
    p.add_argument("--train-frac", type=float, default=0.5)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    # Include existing SOLUSDT metrics (from R-1) into the summary table
    sol_path = OUT_DIR / "poc__SOLUSDT__metrics.json"
    if sol_path.exists():
        m = json.loads(sol_path.read_text())
        rows.append(_extract_row(m))
        log.info("Included pre-existing SOLUSDT metrics in summary.")

    for sym in args.symbols:
        try:
            m = run_one(
                sym,
                lookback=args.lookback, fwd=args.fwd,
                entry_threshold=args.entry_threshold,
                sl_pct=args.sl_pct, tp_pct=args.tp_pct,
                max_hold_bars=args.max_hold_bars,
                fee_rate=args.fee_rate, capital=args.capital,
                train_frac=args.train_frac,
            )
            rows.append(_extract_row(m))
        except Exception as exc:
            log.exception("Failed %s: %s", sym, exc)
            rows.append({"symbol": sym, "error": str(exc)})

    df = pd.DataFrame(rows)
    cols = ["symbol", "n_trades", "alpha_pct", "total_return_pct", "buy_hold_pct",
            "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor",
            "ic_pearson", "rank_ic", "rank_ic_p", "top_minus_bottom_decile_y",
            "oos_days"]
    df = df.reindex(columns=[c for c in cols if c in df.columns])
    out_csv = OUT_DIR / "r2_mini_summary.csv"
    df.to_csv(out_csv, index=False)
    log.info("Wrote %s", out_csv)

    print("\n=== R-2 mini summary ===")
    print(df.to_string(index=False))
    return 0


def _extract_row(m: dict) -> dict:
    tm = m.get("train_meta", {}) or {}
    return {
        "symbol": m.get("symbol"),
        "n_trades": m.get("n_trades"),
        "alpha_pct": m.get("alpha_pct"),
        "total_return_pct": m.get("total_return_pct"),
        "buy_hold_pct": m.get("buy_hold_pct"),
        "sharpe_ann": m.get("sharpe_ann"),
        "max_dd_pct": m.get("max_dd_pct"),
        "win_rate_pct": m.get("win_rate_pct"),
        "profit_factor": m.get("profit_factor"),
        "ic_pearson": tm.get("ic_pearson"),
        "rank_ic": tm.get("rank_ic"),
        "rank_ic_p": tm.get("rank_ic_p"),
        "top_minus_bottom_decile_y": tm.get("top_minus_bottom_decile_y"),
        "oos_days": m.get("oos_days"),
    }


if __name__ == "__main__":
    sys.exit(main())
