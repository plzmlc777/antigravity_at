"""
Signal-based Backtest Engine (v2→v3 통합)

SignalInterceptContext + ExecutionEngine 기반 백테스트 엔진.
WaterfallBacktestEngine과 동일한 실행 경로를 사용하면서
시그널을 캡처하고 ExecutionEngine으로 필터링 가능.

Architecture:
    Strategy.on_data(candle)
        ↓ context.buy/sell 호출
    SignalInterceptContext (signal_context.py)
        ↓ Signal 생성 → ExecutionEngine.evaluate()
    WaterfallBacktestContext (실제 실행)
        ↓ 결과 + 시그널 데이터 반환
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from .config import DEFAULT_EXCHANGE, DEFAULT_INITIAL_CAPITAL
from .execution_engine import (
    IExecutionEngine, PassthroughExecutor, FilterChainExecutor,
    Signal, SignalSide,
)
from .signal_context import SignalInterceptContext


class SignalBacktestEngine:
    """
    Signal 기반 백테스트 엔진.
    WaterfallBacktestEngine 실행 경로 + SignalInterceptContext로 시그널 캡처.
    """

    def __init__(self, strategy_class, config: Dict = None,
                 exchange_name: str = DEFAULT_EXCHANGE,
                 execution_engine: IExecutionEngine = None):
        self.strategy_class = strategy_class
        self.config = config or {}
        self.exchange_name = exchange_name
        self.execution_engine = execution_engine or PassthroughExecutor()

    async def run(self, symbol: str = "TEST", duration_days: int = 1,
                  from_date: str = None, interval: str = "1m",
                  initial_capital: int = DEFAULT_INITIAL_CAPITAL,
                  exchange_name: str = None, to_date: str = None):
        from .waterfall_engine import (
            WaterfallBacktestEngine,
            BacktestContext as WaterfallContext,
            is_futures_exchange,
        )
        from ..services.market_data_factory import get_market_data_service
        from .data_schemas import EQUITY_VALUE_KEY

        exchange = exchange_name or self.exchange_name

        # 1. Fetch Data
        data_service = get_market_data_service(exchange)
        raw_feed = await data_service.get_candles(
            symbol, interval=interval, days=duration_days, to_date=to_date
        )

        if not raw_feed:
            return self._empty_result()

        if from_date:
            filtered = [c for c in raw_feed if c['timestamp'] >= from_date]
            if filtered:
                raw_feed = filtered
        raw_feed.sort(key=lambda x: x['timestamp'])

        # 2. Create real context (WaterfallBacktestContext)
        leverage = 1
        if is_futures_exchange(exchange):
            leverage = max(1, int(self.config.get('leverage', 1)))
        feeds = {symbol: raw_feed}
        real_context = WaterfallContext(
            feeds, initial_capital=initial_capital,
            primary_symbol=symbol, leverage=leverage,
        )

        # 3. Wrap with SignalInterceptContext
        context = SignalInterceptContext(real_context, self.execution_engine)

        # 4. Create and run strategy
        p_config = self.config.copy()
        p_config['initial_capital'] = initial_capital
        p_config['symbol'] = symbol
        p_config['exchange_name'] = exchange

        strat = self.strategy_class(context, p_config)
        if hasattr(strat, 'initialize'):
            strat.initialize()

        for candle in raw_feed:
            real_context.current_timestamp = candle['timestamp']
            try:
                context.process_pending_orders(candle)
                strat.on_data(candle)
                context.update_equity()
            except Exception:
                pass

        # 5. Force liquidation at end
        self._force_liquidation(context, real_context, raw_feed)

        # 6. Calculate stats
        engine = WaterfallBacktestEngine(self.strategy_class, {}, exchange_name=exchange)
        stats = engine._generate_stats(real_context, raw_feed)

        final_equity = (
            real_context.equity_curve[-1][EQUITY_VALUE_KEY]
            if real_context.equity_curve else initial_capital
        )
        stats['symbol'] = symbol
        stats['initial_capital'] = initial_capital
        stats['final_equity'] = final_equity
        stats['return_pct'] = (
            (final_equity - initial_capital) / initial_capital * 100
            if initial_capital > 0 else 0
        )
        stats['pnl'] = final_equity - initial_capital
        stats['trades_count'] = len(real_context.trades)
        stats['equity_curve'] = real_context.equity_curve
        stats['config'] = p_config

        # 7. Append signal data
        stats['engine'] = 'signal_v3'
        stats['signal_stats'] = context.get_signal_stats()
        stats['engine_stats'] = self.execution_engine.get_stats()

        return stats

    def _force_liquidation(self, context, real_context, feed):
        """End-of-backtest position liquidation."""
        long_positions = {}
        short_positions = {}
        for t in real_context.trades:
            sym = t['symbol']
            qty = t['quantity']
            if t['type'] == 'buy':
                long_positions[sym] = long_positions.get(sym, 0) + qty
            elif t['type'] == 'sell':
                long_positions[sym] = long_positions.get(sym, 0) - qty
            elif t['type'] == 'short':
                short_positions[sym] = short_positions.get(sym, 0) + qty
            elif t['type'] == 'close_short':
                short_positions[sym] = short_positions.get(sym, 0) - qty

        if not feed:
            return

        close_price = feed[-1]['close']
        for sym, net in long_positions.items():
            if net > 0:
                context.sell(sym, int(net), price=close_price,
                             metadata={"reason": "end_of_backtest_liquidation"})
                context.update_equity()
        for sym, net in short_positions.items():
            if net > 0:
                try:
                    context.close_position(sym,
                                           metadata={"reason": "end_of_backtest_liquidation"})
                except Exception:
                    context.buy(sym, int(net), price=close_price,
                                metadata={"reason": "end_of_backtest_liquidation"})
                context.update_equity()

    def _empty_result(self):
        return {
            "engine": "signal_v3",
            "logs": ["No data collected"],
            "total_return": "0%", "win_rate": "0%", "max_drawdown": "0%",
            "activity_rate": "0%", "total_cycles": 0,
            "signal_stats": {}, "engine_stats": {},
            "chart_data": [], "ohlcv_data": [],
        }
