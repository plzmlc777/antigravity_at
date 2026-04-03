#!/usr/bin/env python3
"""
Standalone Backtest Engine
기존 BacktestEngine과 동일한 로직을 독립 실행 가능한 형태로 구현.
API 없이 PostgreSQL 직접 조회 → 전략 실행 → 성과 분석.

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
    3. 캔들 루프 (on_data 시뮬레이션)
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

    # 3. Simulation loop
    # API BacktestContext 동일: cash는 음수 허용 (Fixed Betting 지원)
    cash = initial_capital
    holdings = 0.0  # quantity held
    trades: List[Trade] = []
    raw_trades = []  # API 동일 FIFO 매칭용 개별 매매 기록
    equity_curve = []

    # Track current trading date for daily reset (mirrors API engine)
    current_trading_date = None

    for i, candle in enumerate(candles):
        ts = candle["timestamp"]
        if not isinstance(ts, datetime):
            ts = datetime.fromisoformat(str(ts))

        current_price = candle["close"]

        # --- Strategy logic (mirrors MartingaleBase.on_data exactly) ---

        # 0. Indicator update hook (e.g., RSI, EMA calculations)
        if hasattr(strategy, '_on_candle'):
            strategy._on_candle(candle)

        # 1. Daily reset of reference_price (API 엔진과 동일)
        current_date = ts.date() if isinstance(ts, datetime) else None
        if current_date and current_trading_date != current_date:
            current_trading_date = current_date
            if strategy.current_level == 0:
                if hasattr(strategy, 'reference_price'):
                    strategy.reference_price = None

        # A. Check exits if holding
        exited = False
        if strategy.current_level > 0:
            # A1. Strategy-based exit
            should_strategy_exit = strategy._check_exit_trigger(candle)

            if should_strategy_exit:
                # Record sell for FIFO matching (API 동일)
                sell_qty = strategy.total_quantity
                raw_trades.append({"type": "sell", "price": current_price,
                                   "quantity": sell_qty, "time": ts.isoformat(),
                                   "cycle_start_equity": strategy._cycle_start_equity})
                trade = _execute_exit(strategy, current_price, ts, cash)
                cash += trade.total_quantity * current_price
                holdings = 0
                trades.append(trade)
                if hasattr(strategy, '_trigger_armed'):
                    strategy._trigger_armed = True
                exited = True
            else:
                # A2. Price-based exits (trailing, max_loss, timeout)
                exit_reason = strategy.check_exits(current_price, ts)
                if exit_reason:
                    sell_qty = strategy.total_quantity
                    raw_trades.append({"type": "sell", "price": current_price,
                                       "quantity": sell_qty, "time": ts.isoformat(),
                                       "cycle_start_equity": strategy._cycle_start_equity})
                    trade = _execute_exit(strategy, current_price, ts, cash)
                    cash += trade.total_quantity * current_price
                    holdings = 0
                    trades.append(trade)
                    if hasattr(strategy, '_trigger_armed'):
                        strategy._trigger_armed = True
                    exited = True
                else:
                    # A3. Additional entry (L2+)
                    # API 엔진: trailing_active일 때 추가 진입 차단
                    if (strategy.current_level < strategy.config["max_buy_count"]
                            and not strategy.trailing_active):
                        should_add = False

                        if strategy.config["additional_buy_mode"] == "step":
                            should_add = strategy._check_step_trigger(current_price)
                        else:
                            should_add = strategy._check_additional_trigger(candle)

                        if should_add and strategy._check_require_lower(current_price):
                            next_level = strategy.current_level + 1
                            qty = strategy.calculate_quantity(
                                next_level, current_price, cash, initial_capital
                            )
                            # API: cash check는 _calculate_quantity 내부에서만 (외부 체크 제거)
                            # API BacktestContext.buy()는 음수 cash 허용
                            if qty > 0:
                                cost = current_price * qty
                                cash -= cost
                                holdings += qty
                                strategy.add_entry(next_level, current_price, qty, ts)
                                raw_trades.append({"type": "buy", "price": current_price,
                                                   "quantity": qty, "time": ts.isoformat()})

        # B. L1 entry if no position
        # API on_data(): exit 후 return → 같은 캔들에서 재진입 불가
        if not exited and strategy.current_level == 0:
            direction = strategy._check_entry_trigger(candle)
            if direction:
                strategy.is_short = (direction == "short")
                strategy._cycle_start_equity = cash + holdings * current_price

                qty = strategy.calculate_quantity(1, current_price, cash, initial_capital)
                # API: 외부 cash check 없음 (BacktestContext.buy는 음수 cash 허용)
                if qty > 0:
                    cost = current_price * qty
                    cash -= cost
                    holdings += qty
                    strategy.add_entry(1, current_price, qty, ts)
                    raw_trades.append({"type": "buy", "price": current_price,
                                       "quantity": qty, "time": ts.isoformat()})
                    # API 엔진: L1 진입 시 peak_price를 진입가로 설정
                    strategy.peak_price = current_price

        # C. Update equity curve
        equity = cash + holdings * current_price
        equity_curve.append({
            "date": ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime) else str(ts),
            "equity": equity,
        })

    # Close any open position at end
    if strategy.current_level > 0:
        final_price = candles[-1]["close"]
        final_ts = candles[-1]["timestamp"]
        if not isinstance(final_ts, datetime):
            final_ts = datetime.fromisoformat(str(final_ts))

        sell_qty = strategy.total_quantity
        raw_trades.append({"type": "sell", "price": final_price,
                           "quantity": sell_qty, "time": final_ts.isoformat(),
                           "force_liquidated": True})
        trade = _execute_exit(strategy, final_price, final_ts, cash)
        cash += trade.total_quantity * final_price
        holdings = 0
        trades.append(trade)

        # Update last equity point
        equity_curve[-1]["equity"] = cash

    # 4. Calculate metrics (FIFO matching — API _analyze_trades와 동일)
    timestamps = [c["timestamp"] for c in candles]
    result = calculate_metrics(trades, equity_curve, timestamps, initial_capital, strategy_name,
                               raw_trades=raw_trades)

    return result


def _execute_exit(
    strategy: MartingaleStrategy,
    price: float,
    time: datetime,
    cash: float,
) -> Trade:
    """포지션 청산 실행."""
    return strategy.close_position(price, time)


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
