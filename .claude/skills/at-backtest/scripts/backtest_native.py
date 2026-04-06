#!/usr/bin/env python3
"""
Native Backtest Engine — Backend와 100% 동일한 실행 경로.

StrategyAdapter 우회. 백엔드의 waterfall_engine.run_single_backtest()와
동일하게 strategy.on_data(candle)을 직접 호출한다.

핵심 차이: backtest.py (StrategyAdapter 경유) vs backtest_native.py (on_data 직접 호출)
- backtest.py: strategy._check_*_trigger() → Signal → BacktestExecutor.submit()
- backtest_native.py: strategy.on_data(candle) → context.buy/sell (BacktestContext)

Usage:
    python backtest_native.py --strategy rsi_martingale --symbol BTCUSDT --interval 1h --days 30
    python backtest_native.py --strategy rsi_martingale --symbol RIVERUSDT --interval 1m --days 7 --source db
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from metrics import calculate_metrics, format_results, BacktestResult


# ─── Lightweight BacktestContext (mirrors backend BacktestContext) ────

class BacktestContext:
    """
    백엔드 BacktestContext와 동일한 인터페이스.
    strategy.on_data()가 호출하는 buy/sell/log/get_time 등을 제공.
    """

    def __init__(self, feeds: Dict[str, List], initial_capital: float,
                 primary_symbol: str, leverage: int = 1):
        self.feeds = feeds
        self.initial_capital = initial_capital
        self.primary_symbol = primary_symbol
        self.leverage = leverage

        self.cash = initial_capital
        self.holdings: Dict[str, float] = defaultdict(float)
        self.avg_costs: Dict[str, float] = {}

        self.trades: List[Dict] = []
        self.equity_curve: List[Dict] = []
        self.current_timestamp: Optional[datetime] = None
        self._current_candle: Optional[Dict] = None
        self._current_index: int = 0

        # For futures
        self.margin_used: float = 0
        self.notional_cost: float = 0

    def get_time(self) -> datetime:
        return self.current_timestamp

    def get_current_price(self, symbol: str = None) -> float:
        if self._current_candle:
            return self._current_candle.get('close', 0)
        return 0

    def get_total_equity(self) -> float:
        """현재 에쿼티 = cash + holdings value."""
        equity = self.cash
        price = self.get_current_price()
        for sym, qty in self.holdings.items():
            if qty > 0:
                if self.leverage > 1:
                    unrealized = (price * qty) - self.notional_cost
                    equity += self.margin_used + unrealized
                else:
                    equity += qty * price
        return equity

    def buy(self, symbol: str, quantity: int, price: float = 0,
            order_type: str = "market", metadata: Dict = None,
            on_filled=None, **kwargs) -> Dict:

        exec_price = price if price > 0 else self.get_current_price(symbol)
        if exec_price <= 0 or quantity <= 0:
            if on_filled:
                on_filled(order_id="failed", filled_qty=0,
                          filled_price=0, metadata=metadata or {})
            return {"status": "failed"}

        cost = exec_price * quantity
        if self.leverage > 1:
            margin = cost / self.leverage
            self.cash -= margin
            self.margin_used += margin
            self.notional_cost += cost
        else:
            self.cash -= cost

        self.holdings[symbol] += quantity

        # Average cost update
        prev_qty = self.holdings[symbol] - quantity
        prev_cost = self.avg_costs.get(symbol, 0) * prev_qty
        self.avg_costs[symbol] = (prev_cost + exec_price * quantity) / self.holdings[symbol]

        trade_record = {
            "type": "buy", "symbol": symbol, "price": exec_price,
            "quantity": quantity, "timestamp": self.current_timestamp,
            "metadata": metadata or {},
        }
        self.trades.append(trade_record)

        if on_filled:
            on_filled(
                order_id=f"bt-{len(self.trades)}",
                filled_qty=quantity,
                filled_price=exec_price,
                metadata=metadata or {},
            )

        return {"status": "filled", "price": exec_price, "quantity": quantity}

    def sell(self, symbol: str, quantity: int, price: float = 0,
             order_type: str = "market", metadata: Dict = None,
             on_filled=None, **kwargs) -> Dict:

        exec_price = price if price > 0 else self.get_current_price(symbol)
        if exec_price <= 0 or quantity <= 0:
            if on_filled:
                on_filled(order_id="failed", filled_qty=0,
                          filled_price=0, metadata=metadata or {})
            return {"status": "failed"}

        if self.leverage > 1:
            revenue = exec_price * quantity
            pnl = revenue - self.notional_cost
            self.cash += self.margin_used + pnl
            self.margin_used = 0
            self.notional_cost = 0
        else:
            self.cash += exec_price * quantity

        self.holdings[symbol] -= quantity
        if self.holdings[symbol] <= 0:
            del self.holdings[symbol]
            self.avg_costs.pop(symbol, None)

        trade_record = {
            "type": "sell", "symbol": symbol, "price": exec_price,
            "quantity": quantity, "timestamp": self.current_timestamp,
            "metadata": metadata or {},
        }
        self.trades.append(trade_record)

        if on_filled:
            on_filled(
                order_id=f"bt-{len(self.trades)}",
                filled_qty=quantity,
                filled_price=exec_price,
                metadata=metadata or {},
            )

        return {"status": "filled", "price": exec_price, "quantity": quantity}

    def log(self, message: str):
        pass  # Silent in backtest

    def update_equity(self):
        equity = self.get_total_equity()
        self.equity_curve.append({
            "date": self.current_timestamp.strftime("%Y-%m-%d %H:%M")
                    if isinstance(self.current_timestamp, datetime) else str(self.current_timestamp),
            "equity": equity,
        })

    def reset_cycle_capital(self):
        """Fixed betting: 사이클 종료 시 cash를 initial_capital로 리셋."""
        self.cash = self.initial_capital

    def short(self, symbol: str, quantity: int, price: float = 0,
              order_type: str = "market", metadata: Dict = None,
              on_filled=None, **kwargs) -> Dict:
        """Short sell (futures). For backtest, same as sell logic."""
        return self.buy(symbol, quantity, price, order_type, metadata, on_filled, **kwargs)

    def close_position(self, symbol: str, metadata: Dict = None,
                       on_filled=None, **kwargs) -> Dict:
        """Close entire position."""
        qty = int(self.holdings.get(symbol, 0))
        if qty > 0:
            return self.sell(symbol, qty, metadata=metadata, on_filled=on_filled)
        return {"status": "no_position"}

    def get_futures_data(self, symbol: str = None) -> Dict:
        return {"leverage": self.leverage, "liquidation_price": 0}

    def get_history(self, symbol: str = None, count: int = 200) -> List[Dict]:
        sym = symbol or self.primary_symbol
        feed = self.feeds.get(sym, [])
        end = self._current_index + 1
        start = max(0, end - count)
        return feed[start:end]


# ─── Strategy Loader ────────────────────────────────────────────────

def _load_backend_strategy(strategy_name: str):
    """백엔드 전략 클래스를 직접 임포트."""
    project_root = Path(__file__).parent.parent.parent.parent.parent
    backend_path = str(project_root / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    # Load .env for database config (needed by StrategyRegistry imports)
    env_path = project_root / ".env"
    if env_path.exists():
        import os
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = val

    from app.core.strategy_registry import StrategyRegistry
    strategy_class = StrategyRegistry.get_strategy_class(strategy_name)
    if not strategy_class:
        raise ValueError(f"Strategy '{strategy_name}' not found in registry")
    return strategy_class


# ─── Native Backtest Runner ────────────────────────────────────────

def run_native_backtest(
    strategy_name: str,
    symbol: str,
    interval: str = "1d",
    days: int = 365,
    initial_capital: float = 10_000_000,
    config: Dict[str, Any] = None,
    from_date: str = None,
    to_date: str = None,
    source: str = "auto",
    futures: bool = False,
) -> BacktestResult:
    """
    백엔드 waterfall_engine.run_single_backtest()와 동일한 흐름으로 실행.
    """
    # 1. Load data
    if source == "exchange":
        from fetch_exchange import load_ohlcv_exchange
        df = load_ohlcv_exchange(symbol, interval, days, from_date, to_date, futures=futures)
    elif source == "db":
        from fetch_data import load_ohlcv
        df = load_ohlcv(symbol, interval, days, from_date, to_date)
    else:
        from fetch_exchange import load_ohlcv_auto
        df = load_ohlcv_auto(symbol, interval, days, from_date, to_date, source="auto", futures=futures)

    if df.empty:
        print(f"Error: No data for {symbol} ({interval}, {days}d)")
        return BacktestResult(strategy_id=strategy_name)

    candles = df.to_dict("records")

    # 2. Create context (same as backend)
    leverage = max(1, int((config or {}).get("leverage", 1)))
    feeds = {symbol: candles}
    context = BacktestContext(feeds, initial_capital, symbol, leverage=leverage)

    # 3. Create and initialize strategy (same as backend)
    p_config = (config or {}).copy()
    p_config['initial_capital'] = initial_capital
    p_config['symbol'] = symbol

    strategy_class = _load_backend_strategy(strategy_name)
    strat = strategy_class(context, p_config)
    if hasattr(strat, 'initialize'):
        strat.initialize()

    # 4. Simulation loop (same as backend waterfall_engine line 625-633)
    for i, candle in enumerate(candles):
        ts = candle['timestamp']
        if not isinstance(ts, datetime):
            ts = datetime.fromisoformat(str(ts))

        context.current_timestamp = ts
        context._current_candle = candle
        context._current_index = i

        try:
            strat.on_data(candle)
            context.update_equity()
        except Exception as e:
            pass  # Continue on error (same as backend)

    # 5. Force liquidation (same as backend)
    long_positions = defaultdict(float)
    for t in context.trades:
        sym = t['symbol']
        qty = t['quantity']
        if t['type'] == 'buy':
            long_positions[sym] += qty
        elif t['type'] == 'sell':
            long_positions[sym] -= qty

    for sym, qty in long_positions.items():
        if qty > 0:
            last_price = candles[-1]['close']
            context.sell(sym, int(qty), price=last_price,
                         metadata={"force_liquidated": True})

    # 6. Calculate metrics
    timestamps = [c['timestamp'] for c in candles]
    # Convert trade format for metrics (needs 'time' key, not 'timestamp')
    raw_trades_for_metrics = []
    for t in context.trades:
        rt = dict(t)
        if 'timestamp' in rt and 'time' not in rt:
            ts = rt['timestamp']
            rt['time'] = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        raw_trades_for_metrics.append(rt)

    result = calculate_metrics(
        [],  # trades (FIFO will be built from raw_trades)
        context.equity_curve,
        timestamps,
        initial_capital,
        strategy_name,
        raw_trades=raw_trades_for_metrics,
    )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Native Backtest - Backend과 100% 동일한 실행 경로"
    )
    parser.add_argument("--strategy", "-s", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--interval", "-i", default="1d")
    parser.add_argument("--days", "-d", type=int, default=365)
    parser.add_argument("--capital", "-c", type=float, default=10_000_000)
    parser.add_argument("--config", help="Strategy config JSON string")
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    parser.add_argument("--source", default="auto", choices=["exchange", "db", "auto"])
    parser.add_argument("--futures", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    config = json.loads(args.config) if args.config else {}

    print(f"Running NATIVE backtest: {args.strategy} / {args.symbol} ({args.interval}, {args.days}d)")
    print(f"Capital: {args.capital:,.0f} | Source: {args.source}")
    print()

    result = run_native_backtest(
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
            "max_drawdown": result.max_drawdown,
            "total_cycles": result.total_cycles,
            "profit_factor": result.profit_factor,
            "sharpe_ratio": result.sharpe_ratio,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_results(result))


if __name__ == "__main__":
    main()
