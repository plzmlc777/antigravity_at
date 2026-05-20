#!/usr/bin/env python3
"""Backtest paper-seeded spec JSONs and emit Sharpe / MDD / WR / PF table.

Reads each `backend/configs/paper_sessions/*.json`, builds the same Pipeline
the live paper session uses, and runs a static train/test backtest via
`GenericBacktester.run_static(train_frac=0.5)`.

Output CSV: symbol, spec_name, fee, fwd, policy, threshold,
  n_trades, total_return_pct, buy_hold_pct, alpha_pct,
  win_rate, sharpe_ann, max_dd_pct, profit_factor.

Usage:
  python -m scripts.backtest_paper_specs              # all binance specs
  python -m scripts.backtest_paper_specs --kr         # only KR specs
  python -m scripts.backtest_paper_specs --pattern SOL  # filter by spec name
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.composer_framework import build_pipeline  # noqa: E402
from app.composer_framework.backtester import GenericBacktester  # noqa: E402
from app.composer_framework.signal_source import SourceContext  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING, format="%(message)s")

SPEC_DIR = ROOT / "configs" / "paper_sessions"
PATTERN_DIR = ROOT / "runs" / "pattern_scanner"
MICRO_DIR = ROOT / "runs" / "microstructure"
BOOK_DIR = ROOT / "runs" / "book_depth"
PREMIUM_DIR = ROOT / "runs" / "premium_index"
OUT_PATH = ROOT / "runs" / "paper_spec_backtest.csv"

KR_PREFIXES = ("000", "001", "002", "003", "004", "005", "006", "007", "008", "009",
               "01", "02", "03", "04", "05", "06", "07", "08", "09",
               "1", "2", "3")  # KR equity ticker pattern


def is_kr_symbol(sym: str) -> bool:
    return sym.isdigit() and len(sym) == 6


def load_ohlcv_eval(symbol: str) -> pd.DataFrame | None:
    db = SessionLocal()
    try:
        sql = text("""SELECT timestamp, open, high, low, close, volume FROM ohlcv
                      WHERE symbol = :s AND time_frame = '1m' ORDER BY timestamp""")
        rows = db.execute(sql, {"s": symbol}).fetchall()
    finally:
        db.close()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    return resample_ohlcv(df, "1d")


def load_runtime(symbol: str) -> dict:
    runtime: dict = {"symbol": symbol}
    # signals (any version)
    for p in sorted(PATTERN_DIR.glob(f"{symbol}__*d__signals.joblib")):
        runtime["signals_df"] = joblib.load(p)
        break
    # binance microstructure 5min metrics
    micro_p = MICRO_DIR / f"{symbol}_full_metrics.joblib"
    if micro_p.exists():
        runtime["binance_metrics_5m"] = joblib.load(micro_p)
    # book depth
    bd_p = BOOK_DIR / f"{symbol}_bookdepth.joblib"
    if bd_p.exists():
        runtime["book_depth_daily"] = joblib.load(bd_p)
    # premium
    prem_p = PREMIUM_DIR / f"{symbol}_premium.joblib"
    if prem_p.exists():
        runtime["premium_df"] = joblib.load(prem_p)
    # binance funding rate (for bn_funding_oi / bn_funding_zscore sources)
    try:
        from app.db.session import SessionLocal
        from sqlalchemy import text as _text
        with SessionLocal() as _s:
            rows = _s.execute(_text(
                "SELECT symbol, funding_time, funding_rate, mark_price "
                "FROM binance_funding_rate WHERE symbol = :sym ORDER BY funding_time"
            ), {"sym": symbol}).fetchall()
        if rows:
            df = pd.DataFrame(rows, columns=["symbol", "funding_time", "funding_rate", "mark_price"])
            df["funding_time"] = pd.to_datetime(df["funding_time"])
            df["funding_rate"] = pd.to_numeric(df["funding_rate"])
            df["mark_price"] = pd.to_numeric(df["mark_price"])
            runtime["binance_funding_df"] = df
    except Exception:
        pass  # tolerate missing table — only matters if spec actually requests it

    # binance funding rate UNIVERSE wide (for bn_funding_dispersion source)
    try:
        from app.db.session import SessionLocal
        from sqlalchemy import text as _text
        from scripts.paper_session_cli import (
            FUNDING_DISPERSION_UNIVERSE,
            load_binance_funding_universe,
        )
        wide = load_binance_funding_universe(FUNDING_DISPERSION_UNIVERSE)
        if len(wide):
            runtime["binance_funding_universe_df"] = wide
    except Exception:
        pass  # only matters if spec requests bn_funding_dispersion

    # leader symbol 5m ohlcv (for bn_cross_lead_lag source — default BTCUSDT)
    try:
        leader_eval = load_ohlcv_eval("BTCUSDT")
        if leader_eval is not None and len(leader_eval) > 0:
            runtime["leader_ohlcv_eval"] = leader_eval
    except Exception:
        pass  # only matters if spec requests bn_cross_lead_lag

    # leader symbol 1m raw ohlcv (for bn_btc_rv_highvol_long source — paradigm 69)
    try:
        db = SessionLocal()
        try:
            sql = text("""SELECT timestamp, open, high, low, close, volume FROM ohlcv
                          WHERE symbol = 'BTCUSDT' AND time_frame = '1m' ORDER BY timestamp""")
            rows = db.execute(sql).fetchall()
        finally:
            db.close()
        if rows:
            df_1m = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df_1m["timestamp"] = pd.to_datetime(df_1m["timestamp"])
            df_1m = df_1m.set_index("timestamp")
            for c in ("open", "high", "low", "close", "volume"):
                df_1m[c] = pd.to_numeric(df_1m[c])
            df_1m = df_1m.dropna(subset=["open", "high", "low", "close", "volume"])
            runtime["leader_ohlcv_1m"] = df_1m
    except Exception:
        pass  # only matters if spec requests bn_btc_rv_highvol_long
    return runtime


def backtest_one(spec_path: Path) -> dict | None:
    spec = json.loads(spec_path.read_text())
    name = spec.get("name", spec_path.stem)
    symbol = spec["symbol"]
    fee = float(spec.get("fee_rate", 0.0004))
    pipeline_spec = spec["pipeline_spec"]
    fwd = pipeline_spec.get("config", {}).get("forward_bars", 5)
    policy_type = pipeline_spec.get("policy", {}).get("type", "?")
    policy_kw = pipeline_spec.get("policy", {}).get("kwargs", {})
    threshold = policy_kw.get("entry_threshold", 0.005)

    df_eval = load_ohlcv_eval(symbol)
    if df_eval is None or len(df_eval) < 60:
        return {"spec": name, "symbol": symbol, "error": f"insufficient_data ({0 if df_eval is None else len(df_eval)} bars)"}

    runtime = load_runtime(symbol)
    runtime["ohlcv_eval"] = df_eval

    eval_freq = pipeline_spec.get("config", {}).get("eval_freq_minutes", 1440)
    ctx = SourceContext(symbol=symbol, eval_freq_minutes=eval_freq, ohlcv_eval=df_eval)

    try:
        pipeline = build_pipeline(pipeline_spec, runtime)
    except Exception as e:
        return {"spec": name, "symbol": symbol, "error": f"build_pipeline: {e}"}

    bt = GenericBacktester(initial_capital=1_000_000.0, size_pct=0.95, fee_rate=fee)
    try:
        kpi = bt.run_static(pipeline=pipeline, ctx=ctx, train_frac=0.5)
    except Exception as e:
        return {"spec": name, "symbol": symbol, "error": f"backtest: {e}"}

    return {
        "spec": name,
        "symbol": symbol,
        "fee": fee,
        "fwd": fwd,
        "policy": policy_type,
        "threshold": threshold,
        "n_trades": kpi.n_trades,
        "total_return_pct": round(kpi.total_return_pct * 100, 3),
        "buy_hold_pct": round(kpi.buy_hold_pct * 100, 3),
        "alpha_pct": round((kpi.total_return_pct - kpi.buy_hold_pct) * 100, 3),
        "win_rate_pct": round(kpi.win_rate * 100, 2),
        "sharpe_ann": round(kpi.sharpe_per_trade_annualized, 3),
        "max_dd_pct": round(kpi.max_drawdown_pct * 100, 3),
        "profit_factor": round(kpi.profit_factor, 3),
        "avg_win_pct": round(kpi.avg_win_pct * 100, 3),
        "avg_loss_pct": round(kpi.avg_loss_pct * 100, 3),
        "exit_reasons": kpi.exit_reasons,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kr", action="store_true", help="KR specs only (default: Binance only)")
    ap.add_argument("--all", action="store_true", help="Both KR and Binance")
    ap.add_argument("--pattern", default=None, help="Filter spec name substring")
    ap.add_argument("--out", default=str(OUT_PATH), help="Output CSV path")
    ap.add_argument("--include-subdirs", action="store_true",
                    help="Also include nested spec dirs (e.g. configs/paper_sessions/lifecycle/*.json)")
    args = ap.parse_args()

    paths = sorted(SPEC_DIR.glob("*.json"))
    if args.include_subdirs:
        paths += sorted(SPEC_DIR.glob("*/*.json"))
    if not args.all:
        if args.kr:
            paths = [p for p in paths if is_kr_symbol(json.loads(p.read_text()).get("symbol", ""))]
        else:
            paths = [p for p in paths if not is_kr_symbol(json.loads(p.read_text()).get("symbol", ""))]
    if args.pattern:
        paths = [p for p in paths if args.pattern.lower() in p.stem.lower()]

    print(f"Backtesting {len(paths)} spec(s) -> {args.out}", flush=True)
    print(f"  Settings: train_frac=0.5, capital=1,000,000\n", flush=True)
    rows = []
    for i, p in enumerate(paths, 1):
        t0 = datetime.utcnow()
        r = backtest_one(p)
        dt = (datetime.utcnow() - t0).total_seconds()
        if r is None:
            print(f"[{i}/{len(paths)}] {p.name}: SKIP (None) [{dt:.1f}s]", flush=True)
            continue
        if "error" in r:
            print(f"[{i}/{len(paths)}] {r.get('spec', p.stem)}: ERROR {r['error']} [{dt:.1f}s]", flush=True)
            rows.append(r)
            continue
        print(f"[{i}/{len(paths)}] {r['spec']}: trades={r['n_trades']:>3} "
              f"ret={r['total_return_pct']:>+7.2f}% bh={r['buy_hold_pct']:>+7.2f}% "
              f"alpha={r['alpha_pct']:>+7.2f}% sharpe={r['sharpe_ann']:>+6.2f} "
              f"mdd={r['max_dd_pct']:>+6.2f}% wr={r['win_rate_pct']:>5.1f}% "
              f"pf={r['profit_factor']:.2f} [{dt:.1f}s]", flush=True)
        rows.append(r)

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(out_p, index=False)
    print(f"\nSaved {len(df)} rows to {out_p}")

    # Print sorted top by alpha
    if "alpha_pct" in df.columns:
        ok = df.dropna(subset=["alpha_pct"]).sort_values("alpha_pct", ascending=False)
        print("\n=== Sorted by alpha_pct ===")
        cols = ["spec", "symbol", "n_trades", "alpha_pct", "sharpe_ann", "max_dd_pct", "win_rate_pct", "profit_factor"]
        avail = [c for c in cols if c in ok.columns]
        if not ok.empty:
            print(ok[avail].to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
