#!/usr/bin/env python3
"""
Standalone Backtest CLI — thin wrapper around backend WaterfallBacktestEngine.

Phase 3a.2 rewrite: this file used to contain a 2,500+ LOC standalone reimplementation
(strategies.py + execution_engine.py) that drifted from the backend's production
backtest engine. It now delegates to the single source of truth
(app.core.waterfall_engine.WaterfallBacktestEngine), wraps the raw candle loading
step, and layers the skill-side KPI enrichment (metrics.py) on top.

Usage:
    python backtest.py --strategy rsi_martingale --symbol BTCUSDT --interval 1h --days 30 --source exchange
    python backtest.py --strategy dip_martingale --symbol 005930 --interval 1d --days 365 --source db
    python backtest.py --strategy ema_momentum --symbol BTCUSDT --interval 1h --days 180 --json
    python backtest.py --list
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── Bootstrap: backend on sys.path + .env loaded ────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]  # .claude/skills/at-backtest/scripts → project root
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Load .env from project root (required by backend config.py at import time)
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k not in os.environ:
                    os.environ[_k] = _v

# Suppress backend strategy snapshot warnings (no session_id during CLI backtest)
import logging
logging.getLogger("strategies.martingale_base").setLevel(logging.ERROR)

from app.core.waterfall_engine import WaterfallBacktestEngine  # noqa: E402
from app.core.strategy_registry import StrategyRegistry  # noqa: E402
from metrics import BacktestResult, calculate_metrics, format_results  # noqa: E402


def _load_candles(
    symbol: str,
    interval: str,
    days: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    source: str = "auto",
    futures: bool = False,
):
    if source == "exchange":
        from fetch_exchange import load_ohlcv_exchange
        return load_ohlcv_exchange(symbol, interval, days, from_date, to_date, futures=futures)
    elif source == "db":
        from fetch_data import load_ohlcv
        return load_ohlcv(symbol, interval, days, from_date, to_date)
    else:  # auto
        from fetch_exchange import load_ohlcv_auto
        return load_ohlcv_auto(symbol, interval, days, from_date, to_date, source="auto", futures=futures)


def _detect_exchange_name(symbol: str, futures: bool) -> str:
    """Pick the backend exchange tag so Waterfall applies leverage rules correctly."""
    if futures:
        return "BinanceFutures"
    if symbol.endswith("USDT") or symbol.endswith("USDC") or symbol.endswith("BTC"):
        return "Binance"
    return "Kiwoom"


async def run_backtest_async(
    strategy_name: str,
    symbol: str,
    interval: str = "1d",
    days: int = 365,
    initial_capital: float = 10_000_000,
    config: Optional[Dict[str, Any]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    source: str = "auto",
    futures: bool = False,
) -> BacktestResult:
    """
    Execute one backtest via WaterfallBacktestEngine and enrich with skill KPIs.

    Flow:
      1. Load candles from skill fetcher (exchange API or DB).
      2. Look up strategy class from backend StrategyRegistry
         (which after Phase 1 points at .claude/skills/at-live-signal/scripts/strategies).
      3. Delegate to WaterfallBacktestEngine.run_single_backtest() — the same
         entry point production /v3-backtest uses.
      4. Pipe Waterfall's raw trades/equity_curve into metrics.calculate_metrics()
         to add monthly_return_compound, kpi_gap_pp, etc.
    """
    df = _load_candles(symbol, interval, days, from_date, to_date, source=source, futures=futures)
    if df.empty:
        print(f"Error: No data for {symbol} ({interval}, {days}d)", file=sys.stderr)
        return BacktestResult(strategy_id=strategy_name)

    candles = df.to_dict("records")

    strategy_class = StrategyRegistry.get_strategy_class(strategy_name)
    if strategy_class is None:
        raise ValueError(f"Strategy '{strategy_name}' not found in StrategyRegistry")

    exchange_name = _detect_exchange_name(symbol, futures)
    p_config = dict(config or {})

    # Multi-symbol support: load extra feeds for pair/hedge strategies
    extra_feeds = {}
    try:
        required_symbols = strategy_class.get_required_symbols(p_config) if hasattr(strategy_class, 'get_required_symbols') else []
        for extra_sym in required_symbols:
            if not extra_sym or extra_sym == symbol:
                continue
            extra_df = _load_candles(extra_sym, interval, days, from_date, to_date, source=source, futures=futures)
            if extra_df is not None and not extra_df.empty:
                extra_feeds[extra_sym] = extra_df.to_dict("records")
                print(f"  Loaded extra feed: {extra_sym} ({len(extra_feeds[extra_sym])} candles)", file=sys.stderr)
    except Exception as e:
        print(f"Warning: failed to load extra feeds: {e}", file=sys.stderr)
        extra_feeds = {}

    engine = WaterfallBacktestEngine(strategy_class, p_config, exchange_name=exchange_name)
    stats = await engine.run_single_backtest(
        config=p_config,
        feed=candles,
        initial_capital=int(initial_capital),
        symbol=symbol,
        optimize_mode=True,  # skip chart/ohlcv resampling — CLI doesn't need them
        rank=1,
        extra_feeds=extra_feeds if extra_feeds else None,
    )

    # Waterfall's _generate_stats already computed: total_return, win_rate, sharpe_ratio,
    # max_drawdown, stability_score, etc. It also exposes raw trades + equity_curve.
    trades = stats.get("trades", [])
    equity_curve = stats.get("equity_curve", [])
    timestamps = [c["timestamp"] for c in candles]

    # Normalize trade timestamps for metrics.py (expects 'time' key, ISO string).
    raw_trades_for_metrics: List[Dict[str, Any]] = []
    for t in trades:
        rt = dict(t)
        ts = rt.get("time") or rt.get("timestamp")
        if isinstance(ts, datetime):
            rt["time"] = ts.isoformat()
        elif ts is not None:
            rt["time"] = str(ts)
        raw_trades_for_metrics.append(rt)

    result = calculate_metrics(
        [],  # let metrics.py build its FIFO cycles from raw_trades
        equity_curve,
        timestamps,
        initial_capital,
        strategy_name,
        raw_trades=raw_trades_for_metrics,
    )
    return result


def run_backtest(
    strategy_name: str,
    symbol: str,
    **kwargs,
) -> BacktestResult:
    """Sync wrapper so callers don't need asyncio boilerplate."""
    return asyncio.run(run_backtest_async(strategy_name=strategy_name, symbol=symbol, **kwargs))


def _list_strategies() -> Dict[str, str]:
    """Enumerate strategies the backend registry knows about."""
    try:
        names = StrategyRegistry.list_strategies()
    except Exception as e:
        return {"_error": str(e)}
    out: Dict[str, str] = {}
    for name in names:
        cls = StrategyRegistry.get_strategy_class(name)
        desc = ""
        if cls is not None:
            schema = getattr(cls, "PARAMETER_SCHEMA", None) or {}
            desc = schema.get("description") or schema.get("name") or (cls.__doc__ or "").split("\n", 1)[0].strip()
        out[name] = desc
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Standalone backtest CLI — thin wrapper around backend Waterfall engine"
    )
    parser.add_argument("--strategy", "-s", help="Strategy name (e.g., dip_martingale)")
    parser.add_argument("--symbol", help="Symbol (e.g., 005930, BTCUSDT)")
    parser.add_argument("--interval", "-i", default="1d", help="Candle interval (default: 1d)")
    parser.add_argument("--days", "-d", type=int, default=365, help="Days of data (default: 365)")
    parser.add_argument("--capital", "-c", type=float, default=10_000_000, help="Initial capital")
    parser.add_argument("--config", help="Strategy config as JSON string")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--source", default="auto", choices=["exchange", "db", "auto"],
        help="Data source: exchange (API), db (PostgreSQL), auto (exchange→db fallback)",
    )
    parser.add_argument("--futures", action="store_true", help="Use futures API for exchange source")
    parser.add_argument("--list", action="store_true", help="List available strategies")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.list:
        print("Available strategies:")
        for name, desc in _list_strategies().items():
            print(f"  {name:20s} {desc}")
        return

    if not args.strategy or not args.symbol:
        parser.error("--strategy and --symbol are required")

    config = json.loads(args.config) if args.config else {}

    print(f"Running backtest: {args.strategy} / {args.symbol} ({args.interval}, {args.days}d)")
    print(f"Capital: {args.capital:,.0f} | Source: {args.source}" + (" (futures)" if args.futures else ""))
    if config:
        print(f"Config: {json.dumps(config)}")
    print()

    result = run_backtest(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        config=config,
        from_date=args.from_date,
        to_date=args.to_date,
        source=args.source,
        futures=args.futures,
    )

    if args.json:
        output = {
            "strategy_id": result.strategy_id,
            "total_return": result.total_return,
            "win_rate": result.win_rate,
            "recent_10_win_rate": result.recent_10_win_rate,
            "max_drawdown": result.max_drawdown,
            "total_cycles": result.total_cycles,
            "avg_pnl": result.avg_pnl,
            "max_profit": result.max_profit,
            "max_loss": result.max_loss,
            "profit_factor": result.profit_factor,
            "sharpe_ratio": result.sharpe_ratio,
            "activity_rate": result.activity_rate,
            "total_days": result.total_days,
            "monthly_return_compound": result.monthly_return_compound,
            "monthly_return_arithmetic": result.monthly_return_arithmetic,
            "kpi_gap_pp": result.kpi_gap_pp,
            "volatility_drag_warning": result.volatility_drag_warning,
            "avg_holding_time": result.avg_holding_time,
            "stability_score": result.stability_score,
            "acceleration_score": result.acceleration_score,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(result))


if __name__ == "__main__":
    main()
