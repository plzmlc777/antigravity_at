#!/usr/bin/env python3
"""
Standalone Backtest Engine
기존 BacktestEngine과 동일한 로직을 독립 실행 가능한 형태로 구현.
API 없이 PostgreSQL 직접 조회 -> 전략 실행 -> 성과 분석.

v2: ExecutionEngine 기반 리팩토링.
    전략 -> Signal -> BacktestExecutor 구조로 분리.

Usage:
    python backtest.py --strategy dip_martingale --symbol 005930 --interval 1d --days 365
    python backtest.py --strategy ema_momentum --symbol BTCUSDT --interval 1h --days 180
    python backtest.py --list
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add script directory to path
sys.path.insert(0, str(Path(__file__).parent))

from fetch_data import load_ohlcv
from strategies import get_strategy, list_strategies, MartingaleStrategy, Trade
from metrics import calculate_metrics, format_results, BacktestResult
from execution_engine import BacktestExecutor, StrategyAdapter


def run_backtest(
    strategy_name: str,
    symbol: str,
    interval: str = "1d",
    days: int = 365,
    initial_capital: float = 10_000_000,
    config: Dict[str, Any] = None,
    from_date: str = None,
    to_date: str = None,
) -> BacktestResult:
    """
    독립 백테스트 실행. 기존 BacktestEngine.run()과 동일한 흐름.

    1. DB에서 OHLCV 로드
    2. 전략 초기화
    3. Signal -> ExecutionEngine 루프
    4. 성과 분석
    """

    # 1. Load data
    df = load_ohlcv(symbol, interval, days=days, from_date=from_date, to_date=to_date)
    if df.empty:
        print(f"Error: No data for {symbol} ({interval}, {days}d)")
        return BacktestResult(strategy_id=strategy_name)

    candles = df.to_dict("records")

    # 2. Initialize strategy
    strategy = get_strategy(strategy_name, config)
    strategy._initialize_trigger()

    # us_market_follow: 미국 지수 데이터 프리로드
    if hasattr(strategy, 'preload_us_data'):
        strategy.preload_us_data(days=max(days, 365))

    # 3. Create executor and adapter
    leverage = max(1, int((config or {}).get("leverage", 1)))
    executor = BacktestExecutor(
        initial_capital=initial_capital,
        leverage=leverage,
        config=config,
    )
    adapter = StrategyAdapter(strategy)

    # 4. Simulation loop
    for i, candle in enumerate(candles):
        ts = candle["timestamp"]
        if not isinstance(ts, datetime):
            ts = datetime.fromisoformat(str(ts))

        current_price = candle["close"]

        # A. Process pending orders (LIMIT/STOP from previous candles)
        executor.on_candle(candle, strategy, ts)

        # B. Get signals from strategy
        signals = adapter.process_candle(candle, ts, current_price, executor)

        # C. Execute signals
        adapter.execute_signals(signals, executor, ts, current_price)

        # D. Record equity curve
        executor.record_equity(current_price, ts)

    # 5. Force liquidate any open position
    if strategy.current_level > 0:
        final_price = candles[-1]["close"]
        final_ts = candles[-1]["timestamp"]
        if not isinstance(final_ts, datetime):
            final_ts = datetime.fromisoformat(str(final_ts))

        executor._last_trade = None
        executor.force_liquidate(strategy, final_price, final_ts)
        if executor._last_trade is not None:
            adapter._trades.append(executor._last_trade)

        # Update last equity point
        if executor.equity_curve:
            executor.equity_curve[-1]["equity"] = executor.cash

    # 6. Calculate metrics (FIFO matching -- API _analyze_trades와 동일)
    timestamps = [c["timestamp"] for c in candles]
    result = calculate_metrics(
        adapter.trades,
        executor.equity_curve,
        timestamps,
        initial_capital,
        strategy_name,
        raw_trades=executor.raw_trades,
    )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Standalone Backtest Engine - 기존 BacktestEngine과 동일한 결과를 독립 실행"
    )
    parser.add_argument("--strategy", "-s", help="Strategy name (e.g., dip_martingale)")
    parser.add_argument("--symbol", help="Symbol (e.g., 005930, BTCUSDT)")
    parser.add_argument("--interval", "-i", default="1d", help="Candle interval (default: 1d)")
    parser.add_argument("--days", "-d", type=int, default=365, help="Days of data (default: 365)")
    parser.add_argument("--capital", "-c", type=float, default=10_000_000, help="Initial capital")
    parser.add_argument("--config", help="Strategy config as JSON string")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--list", action="store_true", help="List available strategies")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.list:
        print("Available strategies:")
        for name, desc in list_strategies().items():
            print(f"  {name:20s} {desc}")
        return

    if not args.strategy or not args.symbol:
        parser.error("--strategy and --symbol are required")

    config = json.loads(args.config) if args.config else {}

    print(f"Running backtest: {args.strategy} / {args.symbol} ({args.interval}, {args.days}d)")
    print(f"Capital: {args.capital:,.0f}")
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
            "avg_holding_time": result.avg_holding_time,
            "stability_score": result.stability_score,
            "acceleration_score": result.acceleration_score,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(result))


if __name__ == "__main__":
    main()
