#!/usr/bin/env python3
"""Unified CLI for PaperSession lifecycle.

Subcommands:
  create   Create a new session from a spec file (JSON)
  run      Run one cycle on one or more sessions (called by cron)
  status   List all sessions with status + KPIs
  compare  Compare 2+ sessions side-by-side
  show     Detail one session (config + recent cycles + trades)
  pause    Pause a session
  resume   Resume a paused session
  terminate  Mark session as terminated (no further cycles)

Examples:
  python -m scripts.paper_session_cli create --spec configs/sessions/122630_prod.json
  python -m scripts.paper_session_cli run --all
  python -m scripts.paper_session_cli status
  python -m scripts.paper_session_cli compare --ids abc123 def456
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import joblib
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.composer_framework import (  # noqa: E402
    PaperOrchestrator,
    PaperSession,
    RuntimeBundle,
    SessionStore,
    validate_spec,
)
from app.db.session import SessionLocal  # noqa: E402
from app.microstructure.kr_investor_flow import fetch_investor_flow  # noqa: E402
from app.pattern_scanner import PatternScanner  # noqa: E402
from app.pattern_scanner.resample import resample_ohlcv  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("paper_session_cli")

DEFAULT_STORE_ROOT = ROOT / "runs" / "paper_sessions"


# ────────────────────────────────────────── data loaders


def load_1m(symbol: str, days: int = 800) -> pd.DataFrame:
    db = SessionLocal()
    try:
        end = datetime.now().replace(second=0, microsecond=0)
        start = end - timedelta(days=days)
        sql = text("SELECT timestamp, open, high, low, close, volume FROM ohlcv "
                   "WHERE symbol = :sym AND time_frame = '1m' "
                   "AND timestamp >= :start ORDER BY timestamp")
        rows = db.execute(sql, {"sym": symbol, "start": start}).fetchall()
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        return df.dropna(subset=["open", "high", "low", "close", "volume"])
    finally:
        db.close()


def load_binance_funding(symbol: str, days: int = 400) -> pd.DataFrame:
    """Fetch all stored funding rate rows for symbol within last `days`.
    Returns empty DataFrame if table missing or no rows."""
    db = SessionLocal()
    try:
        start = datetime.now() - timedelta(days=days)
        sql = text(
            "SELECT symbol, funding_time, funding_rate, mark_price "
            "FROM binance_funding_rate "
            "WHERE symbol = :sym AND funding_time >= :start "
            "ORDER BY funding_time"
        )
        rows = db.execute(sql, {"sym": symbol, "start": start}).fetchall()
        if not rows:
            return pd.DataFrame(columns=["symbol", "funding_time", "funding_rate", "mark_price"])
        df = pd.DataFrame(rows, columns=["symbol", "funding_time", "funding_rate", "mark_price"])
        df["funding_time"] = pd.to_datetime(df["funding_time"])
        df["funding_rate"] = pd.to_numeric(df["funding_rate"])
        df["mark_price"] = pd.to_numeric(df["mark_price"])
        return df
    except Exception as exc:
        log.warning("load_binance_funding(%s) failed: %s", symbol, exc)
        return pd.DataFrame()
    finally:
        db.close()


def load_binance_oi(symbol: str, period: str = "1d", days: int = 60) -> pd.DataFrame:
    """Fetch stored OI hist rows for symbol+period within last `days`.
    Returns empty DataFrame if table missing or no rows."""
    db = SessionLocal()
    try:
        start = datetime.now() - timedelta(days=days)
        sql = text(
            "SELECT symbol, timestamp, interval_str, sum_open_interest, sum_open_interest_value "
            "FROM binance_open_interest_hist "
            "WHERE symbol = :sym AND interval_str = :p AND timestamp >= :start "
            "ORDER BY timestamp"
        )
        rows = db.execute(sql, {"sym": symbol, "p": period, "start": start}).fetchall()
        if not rows:
            return pd.DataFrame(columns=["symbol", "timestamp", "interval_str",
                                         "sum_open_interest", "sum_open_interest_value"])
        df = pd.DataFrame(rows, columns=["symbol", "timestamp", "interval_str",
                                         "sum_open_interest", "sum_open_interest_value"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["sum_open_interest"] = pd.to_numeric(df["sum_open_interest"])
        df["sum_open_interest_value"] = pd.to_numeric(df["sum_open_interest_value"])
        return df
    except Exception as exc:
        log.warning("load_binance_oi(%s) failed: %s", symbol, exc)
        return pd.DataFrame()
    finally:
        db.close()


def get_or_scan_signals(symbol: str, df_1m: pd.DataFrame) -> pd.DataFrame:
    days = (df_1m.index[-1] - df_1m.index[0]).days
    base = ROOT / "runs" / "pattern_scanner"
    for d in (days, 365, 364, 200, 600, 800, 540):
        p = base / f"{symbol}__{d}d__signals.joblib"
        if p.exists():
            return joblib.load(p)
    matches = list(base.glob(f"{symbol}__*d__signals.joblib"))
    if matches:
        return joblib.load(matches[0])
    log.info("No cached signals for %s — scanning %dd...", symbol, days)
    tensor = PatternScanner().scan(df_1m, symbol=symbol)
    base.mkdir(parents=True, exist_ok=True)
    joblib.dump(tensor, base / f"{symbol}__{days}d__signals.joblib", compress=3)
    return tensor


def build_runtime_bundle(symbol: str, eval_freq_minutes: int, sources_used: list[str]) -> RuntimeBundle:
    df_1m = load_1m(symbol)
    if eval_freq_minutes >= 1440:
        eval_tf = "1d"
    elif eval_freq_minutes == 240:
        eval_tf = "4h"
    elif eval_freq_minutes == 60:
        eval_tf = "1h"
    elif eval_freq_minutes == 15:
        eval_tf = "15m"
    elif eval_freq_minutes == 5:
        eval_tf = "5m"
    else:
        eval_tf = "1m"
    df_eval = resample_ohlcv(df_1m, eval_tf)

    bundle = RuntimeBundle(ohlcv_1m=df_1m, ohlcv_eval=df_eval)
    if "pattern" in sources_used:
        bundle.signals_df = get_or_scan_signals(symbol, df_1m)
    if "kr_flow" in sources_used:
        try:
            bundle.flow_df = fetch_investor_flow(symbol)
        except Exception as exc:
            log.warning("Failed to fetch KR flow for %s: %s", symbol, exc)
    if "binance_micro" in sources_used:
        m = ROOT / "runs" / "microstructure" / f"{symbol}_full_metrics.joblib"
        if m.exists():
            bundle.binance_metrics_5m = joblib.load(m)
    if "bn_funding_oi" in sources_used:
        funding_df = load_binance_funding(symbol)
        oi_df = load_binance_oi(symbol, period="1d")
        if len(funding_df) or len(oi_df):
            bundle.binance_funding_df = funding_df if len(funding_df) else None
            bundle.binance_oi_df = oi_df if len(oi_df) else None
        else:
            log.warning("bn_funding_oi requested but no funding/oi rows for %s", symbol)

    if "bn_funding_zscore" in sources_used:
        if bundle.binance_funding_df is None:
            funding_df = load_binance_funding(symbol)
            if len(funding_df):
                bundle.binance_funding_df = funding_df
            else:
                log.warning("bn_funding_zscore requested but no funding rows for %s", symbol)

    # Binance native sources sharing 5min metrics joblib
    needs_metrics_5m = any(s in sources_used for s in (
        "bn_smart_money", "bn_taker_flow", "bn_oi_dynamics",
        "bn_event_detector", "bn_cascade_reversal",
    ))
    if needs_metrics_5m and bundle.binance_metrics_5m is None:
        m = ROOT / "runs" / "microstructure" / f"{symbol}_full_metrics.joblib"
        if m.exists():
            bundle.binance_metrics_5m = joblib.load(m)
        else:
            log.warning("metrics_5m needed but joblib missing for %s", symbol)

    if "bn_book_depth" in sources_used:
        bd_path = ROOT / "runs" / "book_depth" / f"{symbol}_bookdepth.joblib"
        if bd_path.exists():
            bundle.book_depth_daily = joblib.load(bd_path)
        else:
            log.warning("bn_book_depth requested but joblib missing for %s", symbol)

    if "bn_premium" in sources_used:
        prem_path = ROOT / "runs" / "premium_index" / f"{symbol}_premium.joblib"
        if prem_path.exists():
            bundle.premium_df = joblib.load(prem_path)
        else:
            log.warning("bn_premium requested but joblib missing for %s", symbol)

    if "bn_cross_eth" in sources_used:
        # Load ETH eval ohlcv via 1m DB → resample
        try:
            eth_1m = load_1m("ETHUSDT")
            bundle.eth_ohlcv_eval = resample_ohlcv(eth_1m, eval_tf)
        except Exception as exc:
            log.warning("bn_cross_eth requested but ETH ohlcv load failed: %s", exc)

    return bundle


# ────────────────────────────────────────── subcommands


def cmd_create(args) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        log.error("Spec file not found: %s", spec_path)
        return 2
    with open(spec_path) as f:
        full_config = json.load(f)
    spec = full_config["pipeline_spec"]
    errs = validate_spec(spec)
    if errs:
        log.error("Spec validation failed:\n  %s", "\n  ".join(errs))
        return 2

    store = SessionStore(DEFAULT_STORE_ROOT)
    session = PaperSession(
        session_id="",  # auto
        name=full_config.get("name", spec_path.stem),
        symbol=full_config["symbol"],
        mode=full_config.get("mode", "paper"),
        pipeline_spec=spec,
        initial_capital=float(full_config.get("initial_capital", 1_000_000)),
        refit_interval_days=int(full_config.get("refit_interval_days", 30)),
        fee_rate=float(full_config.get("fee_rate", 0.00015)),
        notes=full_config.get("notes", ""),
    )
    store.save(session)
    print(f"Created session {session.session_id}: {session.name} ({session.symbol})")
    return 0


def cmd_run(args) -> int:
    store = SessionStore(DEFAULT_STORE_ROOT)
    sessions = store.list_all()
    if args.id:
        sessions = [s for s in sessions if s.session_id == args.id]
    elif not args.all:
        log.error("Must specify --id or --all")
        return 2
    sessions = [s for s in sessions if s.status == "active"]
    if not sessions:
        print("No active sessions to run")
        return 0

    orch = PaperOrchestrator(store)
    for s in sessions:
        sources_used = [src["type"] for src in s.pipeline_spec.get("sources", [])]
        eval_freq = s.pipeline_spec.get("config", {}).get("eval_freq_minutes", 1440)
        log.info("Running cycle: %s (%s)", s.session_id, s.name)
        try:
            bundle = build_runtime_bundle(s.symbol, eval_freq, sources_used)
            cycle = orch.run_cycle(s, bundle)
            print(f"  {s.session_id} {s.symbol}: pred={cycle.prediction:+.4f} "
                  f"action={cycle.action_kind} side={cycle.side_after} equity={cycle.equity_after:,.0f}")
        except Exception as exc:
            log.error("Cycle failed for %s: %s", s.session_id, exc)
    return 0


def cmd_status(args) -> int:
    store = SessionStore(DEFAULT_STORE_ROOT)
    sessions = store.list_all()
    if not sessions:
        print("No sessions yet")
        return 0

    print(f"{'ID':12s} {'Name':30s} {'Symbol':8s} {'Status':10s} {'Cycles':>7s} {'Trades':>7s} "
          f"{'Equity':>14s} {'Return':>9s}")
    print("-" * 110)
    for s in sessions:
        ret_str = f"{s.total_return_pct*100:+.2f}%"
        print(f"{s.session_id:12s} {s.name[:30]:30s} {s.symbol:8s} {s.status:10s} "
              f"{s.n_cycles:>7d} {s.n_trades:>7d} {s.final_equity:>14,.0f} {ret_str:>9s}")
    return 0


def cmd_show(args) -> int:
    store = SessionStore(DEFAULT_STORE_ROOT)
    s = store.load(args.id)
    print(f"=== {s.name} ({s.session_id}) ===")
    print(f"Symbol      : {s.symbol}")
    print(f"Mode/Status : {s.mode} / {s.status}")
    print(f"Created     : {s.created_at}")
    print(f"Capital     : {s.initial_capital:,.0f} → {s.final_equity:,.0f} ({s.total_return_pct*100:+.2f}%)")
    print(f"Position    : {s.side} qty={s.qty:.6f} entry={s.entry_price:.2f}")
    print(f"Cycles      : {s.n_cycles} (last: {s.last_cycle_ts})")
    print(f"Last fit    : {s.last_fit_ts}")
    print(f"Trades      : {s.n_trades}")
    print(f"\nPipeline spec:")
    print(json.dumps(s.pipeline_spec, indent=2))
    if args.recent:
        trades = store.read_trades(s.session_id)
        print(f"\nRecent trades ({len(trades)}):")
        for t in trades[-10:]:
            print(f"  {t['side']:5s} {t['entry_ts'][:10]} → {t['exit_ts'][:10]} "
                  f"@ {t['entry_price']:.2f}→{t['exit_price']:.2f}  "
                  f"return={t['return_pct']*100:+.2f}%  reason={t['exit_reason']}")
    return 0


def cmd_compare(args) -> int:
    store = SessionStore(DEFAULT_STORE_ROOT)
    ids = args.ids
    sessions = [store.load(i) for i in ids]
    print(f"{'Field':25s} | " + " | ".join(f"{s.session_id[:10]:14s}" for s in sessions))
    print("-" * (28 + 17 * len(sessions)))
    rows = [
        ("Name", lambda s: s.name[:14]),
        ("Symbol", lambda s: s.symbol),
        ("Status", lambda s: s.status),
        ("Cycles", lambda s: str(s.n_cycles)),
        ("Trades", lambda s: str(s.n_trades)),
        ("Final Equity", lambda s: f"{s.final_equity:,.0f}"),
        ("Total Return", lambda s: f"{s.total_return_pct*100:+.2f}%"),
        ("Side", lambda s: s.side),
    ]
    for label, fn in rows:
        print(f"{label:25s} | " + " | ".join(f"{fn(s):14s}" for s in sessions))
    return 0


def cmd_set_status(target: str):
    def _fn(args) -> int:
        store = SessionStore(DEFAULT_STORE_ROOT)
        s = store.load(args.id)
        s.status = target  # type: ignore[assignment]
        store.save(s)
        print(f"Session {s.session_id} marked {target}")
        return 0
    return _fn


# ────────────────────────────────────────── arg parsing


def main() -> int:
    p = argparse.ArgumentParser(prog="paper_session_cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new session from spec JSON")
    p_create.add_argument("--spec", required=True)
    p_create.set_defaults(func=cmd_create)

    # run
    p_run = sub.add_parser("run", help="Run one cycle")
    p_run.add_argument("--id", default=None)
    p_run.add_argument("--all", action="store_true")
    p_run.set_defaults(func=cmd_run)

    # status
    p_status = sub.add_parser("status", help="List all sessions")
    p_status.set_defaults(func=cmd_status)

    # show
    p_show = sub.add_parser("show", help="Show one session in detail")
    p_show.add_argument("--id", required=True)
    p_show.add_argument("--recent", action="store_true", help="show recent trades")
    p_show.set_defaults(func=cmd_show)

    # compare
    p_cmp = sub.add_parser("compare", help="Compare 2+ sessions")
    p_cmp.add_argument("--ids", nargs="+", required=True)
    p_cmp.set_defaults(func=cmd_compare)

    # state changes
    for verb, target in [("pause", "paused"), ("resume", "active"), ("terminate", "terminated")]:
        sp = sub.add_parser(verb)
        sp.add_argument("--id", required=True)
        sp.set_defaults(func=cmd_set_status(target))

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
