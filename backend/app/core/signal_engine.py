"""
Signal-based Backtest Engine (v2)
기존 WaterfallBacktestEngine과 동일한 실행 경로를 사용하면서
buy/sell 호출을 Signal로 캡처하는 엔진.

병행 검증 후 기존 엔진을 대체할 예정.

Architecture:
    Strategy.on_data(candle)
        ↓ context.buy/sell 호출
    Monkey-patched WaterfallBacktestContext
        ├── Signal 기록 (캡처)
        └── 원본 buy/sell 실행 (WaterfallBacktestContext)
        ↓
    SignalBacktestEngine
        ├── WaterfallBacktestEngine.run_single_backtest() 사용
        └── Signal 데이터 추가 반환
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from .config import DEFAULT_EXCHANGE, DEFAULT_INITIAL_CAPITAL


# =============================================================================
# Signal Data
# =============================================================================

@dataclass
class CapturedSignal:
    """캡처된 매매 시그널."""
    side: str           # "buy", "sell", "short", "close_short"
    symbol: str
    quantity: float
    price: float
    order_type: str     # "market", "limit", "stop_market", etc.
    timestamp: datetime
    candle_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 실행 결과
    executed: bool = False
    exec_price: float = 0.0
    exec_quantity: float = 0.0


# =============================================================================
# Signal Capture via Monkey-Patching
# =============================================================================

def attach_signal_capture(context) -> List[CapturedSignal]:
    """
    WaterfallBacktestContext의 buy/sell/short/close_position 메서드를
    래핑하여 Signal을 캡처합니다. 원본 메서드 동작은 그대로 유지.

    Returns: captured_signals 리스트 (context에서 참조 가능)
    """
    captured_signals: List[CapturedSignal] = []
    context._captured_signals = captured_signals

    original_buy = context.buy
    original_sell = context.sell
    original_short = getattr(context, 'short', None)
    original_close = getattr(context, 'close_position', None)

    def _get_timestamp():
        try:
            return context.get_time()
        except Exception:
            return datetime.now()

    def _get_price(symbol):
        try:
            return context.get_current_price(symbol)
        except Exception:
            return 0

    def wrapped_buy(symbol, quantity, price=0, order_type="market",
                    metadata=None, on_filled=None, **kwargs):
        signal = CapturedSignal(
            side="buy", symbol=symbol, quantity=quantity,
            price=price if price > 0 else _get_price(symbol),
            order_type=order_type, timestamp=_get_timestamp(),
            candle_index=getattr(context, 'current_index', 0),
            metadata=metadata or {},
        )
        result = original_buy(symbol, quantity, price, order_type, metadata, on_filled, **kwargs)
        if result.get("status") != "failed" and result.get("status") != "pending":
            signal.executed = True
            signal.exec_price = result.get("price", signal.price)
            signal.exec_quantity = result.get("quantity", quantity)
        captured_signals.append(signal)
        return result

    def wrapped_sell(symbol, quantity, price=0, order_type="market",
                     metadata=None, on_filled=None, **kwargs):
        signal = CapturedSignal(
            side="sell", symbol=symbol, quantity=quantity,
            price=price if price > 0 else _get_price(symbol),
            order_type=order_type, timestamp=_get_timestamp(),
            candle_index=getattr(context, 'current_index', 0),
            metadata=metadata or {},
        )
        result = original_sell(symbol, quantity, price, order_type, metadata, on_filled, **kwargs)
        if result.get("status") != "failed" and result.get("status") != "pending":
            signal.executed = True
            signal.exec_price = result.get("price", signal.price)
            signal.exec_quantity = result.get("quantity", quantity)
        captured_signals.append(signal)
        return result

    def wrapped_short(symbol, quantity, price=0, order_type="market",
                      metadata=None, on_filled=None, **kwargs):
        signal = CapturedSignal(
            side="short", symbol=symbol, quantity=quantity,
            price=price if price > 0 else _get_price(symbol),
            order_type=order_type, timestamp=_get_timestamp(),
            candle_index=getattr(context, 'current_index', 0),
            metadata=metadata or {},
        )
        result = original_short(symbol, quantity, price, order_type, metadata, on_filled, **kwargs)
        if result.get("status") != "failed" and result.get("status") != "pending":
            signal.executed = True
            signal.exec_price = result.get("price", signal.price)
            signal.exec_quantity = result.get("quantity", quantity)
        captured_signals.append(signal)
        return result

    def wrapped_close_position(symbol, metadata=None):
        pre_count = len(captured_signals)
        result = original_close(symbol, metadata)
        # close_position internally calls sell/buy which are already wrapped
        # Only add a signal if nothing was captured (fallback)
        if len(captured_signals) == pre_count:
            signal = CapturedSignal(
                side="close_position", symbol=symbol, quantity=0,
                price=_get_price(symbol), order_type="market",
                timestamp=_get_timestamp(),
                candle_index=getattr(context, 'current_index', 0),
                metadata=metadata or {},
                executed=result.get("status") != "failed",
            )
            captured_signals.append(signal)
        return result

    context.buy = wrapped_buy
    context.sell = wrapped_sell
    if original_short:
        context.short = wrapped_short
    if original_close:
        context.close_position = wrapped_close_position

    return captured_signals


# =============================================================================
# SignalBacktestEngine
# =============================================================================

class SignalBacktestEngine:
    """
    Signal 기반 백테스트 엔진 (v2).
    WaterfallBacktestEngine과 동일한 실행 경로를 사용하여 결과 동일성 보장.
    추가로 캡처된 시그널 데이터를 반환.
    """

    def __init__(self, strategy_class, config: Dict = None, exchange_name: str = DEFAULT_EXCHANGE):
        self.strategy_class = strategy_class
        self.config = config or {}
        self.exchange_name = exchange_name

    async def run(self, symbol: str = "TEST", duration_days: int = 1,
                  from_date: str = None, interval: str = "1m",
                  initial_capital: int = DEFAULT_INITIAL_CAPITAL,
                  exchange_name: str = None, to_date: str = None):
        from .waterfall_engine import WaterfallBacktestEngine
        from ..services.market_data_factory import get_market_data_service

        exchange = exchange_name or self.exchange_name

        # 1. Fetch Data (v1과 동일)
        data_service = get_market_data_service(exchange)
        raw_feed = await data_service.get_candles(symbol, interval=interval, days=duration_days, to_date=to_date)

        if not raw_feed:
            return self._empty_result()

        if from_date:
            filtered = [c for c in raw_feed if c['timestamp'] >= from_date]
            if filtered:
                raw_feed = filtered
        raw_feed.sort(key=lambda x: x['timestamp'])

        # 2. WaterfallBacktestEngine 생성 + Signal 캡처 주입
        engine = WaterfallBacktestEngine(self.strategy_class, {}, exchange_name=exchange)

        # Monkey-patch: run_single_backtest 내부에서 context 생성 후 signal 캡처 주입
        original_run = engine.run_single_backtest
        captured_signals_ref = [None]  # Mutable reference

        async def patched_run(config, feed, initial_capital, symbol, optimize_mode=False, rank=1):
            from .waterfall_engine import BacktestContext as WaterfallContext, is_futures_exchange

            if not feed:
                return engine._empty_result(["No data provided"])

            # 1. Create context (same as original)
            leverage = 1
            if is_futures_exchange(engine._exchange_name):
                leverage = max(1, int(config.get('leverage', 1)))
            feeds = {symbol: feed}
            context = WaterfallContext(feeds, initial_capital=initial_capital, primary_symbol=symbol, leverage=leverage)
            context.current_rank = rank
            context.optimize_mode = optimize_mode

            # 2. Inject signal capture
            captured_signals_ref[0] = attach_signal_capture(context)

            # 3. Create and initialize strategy
            p_config = config.copy()
            p_config['initial_capital'] = initial_capital
            p_config['symbol'] = symbol
            p_config['exchange_name'] = engine._exchange_name

            strat = engine.strategy_class(context, p_config)
            if hasattr(strat, 'initialize'):
                strat.initialize()

            # 4. Run simulation (same as original)
            for candle in feed:
                context.current_timestamp = candle['timestamp']
                try:
                    if hasattr(context, 'process_pending_orders'):
                        context.process_pending_orders(candle)
                    strat.on_data(candle)
                    context.update_equity()
                except Exception:
                    pass

            # 5. Force liquidation at end (same as original)
            long_positions = {}
            short_positions = {}
            for t in context.trades:
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

            last_candle = feed[-1] if feed else None
            if last_candle:
                close_price = last_candle['close']
                for sym, net in long_positions.items():
                    if net > 0:
                        context.sell(sym, int(net), price=close_price,
                                     metadata={"reason": "end_of_backtest_liquidation"})
                        context.update_equity()
                for sym, net in short_positions.items():
                    if net > 0:
                        try:
                            context.close_position(sym, metadata={"reason": "end_of_backtest_liquidation"})
                        except Exception:
                            context.buy(sym, int(net), price=close_price,
                                        metadata={"reason": "end_of_backtest_liquidation"})
                        context.update_equity()

            # 6. Calculate stats (reuse engine methods)
            stats = engine._generate_stats(context, feed, optimize_mode=optimize_mode)

            # Add metadata (same as original run_single_backtest)
            from .data_schemas import EQUITY_VALUE_KEY
            final_equity = context.equity_curve[-1][EQUITY_VALUE_KEY] if context.equity_curve else initial_capital
            stats['symbol'] = symbol
            stats['initial_capital'] = initial_capital
            stats['final_equity'] = final_equity
            stats['return_pct'] = ((final_equity - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
            stats['pnl'] = final_equity - initial_capital
            stats['trades_count'] = len(context.trades)
            stats['equity_curve'] = context.equity_curve
            stats['rank'] = rank
            stats['config'] = p_config

            return stats

        engine.run_single_backtest = patched_run

        # 3. Run (same as v1 _run_unified_backtest single mode)
        result = await engine.run_single_backtest(
            config=self.config,
            feed=raw_feed,
            initial_capital=initial_capital,
            symbol=symbol,
        )

        # 4. Append signal data
        signals = captured_signals_ref[0] or []
        buy_signals = [s for s in signals if s.side == "buy"]
        sell_signals = [s for s in signals if s.side in ("sell", "close_short", "close_position")]

        signal_summary = [
            {
                "side": s.side, "symbol": s.symbol,
                "quantity": s.exec_quantity if s.executed else s.quantity,
                "price": s.exec_price if s.executed else s.price,
                "order_type": s.order_type,
                "timestamp": s.timestamp.isoformat() if isinstance(s.timestamp, datetime) else str(s.timestamp),
                "executed": s.executed,
                "metadata": s.metadata,
            }
            for s in signals
        ]

        result["engine"] = "signal_v2"
        result["signals"] = signal_summary
        result["signal_count"] = {
            "buy": len(buy_signals),
            "sell": len(sell_signals),
            "total": len(signals),
            "executed": len([s for s in signals if s.executed]),
        }

        return result

    def _empty_result(self):
        return {
            "engine": "signal_v2",
            "logs": ["No data collected"],
            "total_return": "0%", "win_rate": "0%", "max_drawdown": "0%",
            "activity_rate": "0%", "total_cycles": 0,
            "signals": [],
            "signal_count": {"buy": 0, "sell": 0, "total": 0, "executed": 0},
            "chart_data": [], "ohlcv_data": [],
        }
