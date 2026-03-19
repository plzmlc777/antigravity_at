
from .config import DEFAULT_EXCHANGE
from .constants import AiMode, Margin
import asyncio
import logging
import traceback
from typing import List, Dict, Any, Callable
from datetime import datetime, timezone, timedelta
from ..models.live_trading import LiveBotSession, SessionStatus, ErrorType, ErrorSeverity
from ..core.live_context import LiveContext
from ..core.live_aggregator import CandleRealAggregator
from ..core.exchange_interface import ExchangeInterface
from ..core.futures_interface import FuturesInterface
from ..db.session import SessionLocal
from ..models.ohlcv import OHLCV
from ..core.strategy_registry import strategy_registry
from ..services.error_logger import error_logger

logger = logging.getLogger(__name__)

class LiveTradingEngine:
    """
    Orchestrates the Live Trading Loop.
    1. Polls Price (Tick).
    2. Updates Aggregator.
    3. Triggers Strategy (Candle Close).
    4. Processes Orders.
    """
    def __init__(self, session_id: str, adapter: ExchangeInterface):
        self.session_id = session_id
        # self.strategy_class = strategy_class # Now dynamic
        # self.strategy_config = strategy_config # Now dynamic
        self.adapter = adapter
        
        self.is_running = False
        self.orders_enabled = True
        self.interval_seconds = 1 # Poll interval
        
        # Components
        self.context: LiveContext = None
        self.strategy_instance = None
        self.aggregator: CandleRealAggregator = None
        self.symbol: str = ""
        
        # Real-time Event Listeners (List of callbacks)
        self.tick_listeners: List[Callable[[Dict], None]] = []
        self.candle_listeners: List[Callable[[Dict], None]] = []
        self.history_candles: List[Dict] = []
        
        # State
        self.last_price = 0
        self.last_accum_volume = -1

        # Exclusive mode
        self._is_exclusive = False
        self._account_id = None

        # AI Symbol Selection
        self._ai_switch_in_progress = False
        self._had_position = False  # Track if we ever had a position (for cycle completion detection)

        # Futures monitoring
        self._futures_monitor = None
        self._futures_refresh_task = None

        # Position sync with exchange
        self._last_position_sync_time: datetime = None
        self._position_sync_interval = 600  # seconds (10 minutes)

    def add_tick_listener(self, listener: Callable[[Dict], None]):
        self.tick_listeners.append(listener)

    def remove_tick_listener(self, listener: Callable[[Dict], None]):
        if listener in self.tick_listeners:
            self.tick_listeners.remove(listener)

    def add_candle_listener(self, listener: Callable[[Dict], None]):
        self.candle_listeners.append(listener)

    def remove_candle_listener(self, listener: Callable[[Dict], None]):
        if listener in self.candle_listeners:
            self.candle_listeners.remove(listener)

    async def initialize(self):
        """Setup Context, Strategy, Aggregator"""
        db = SessionLocal()
        try:
            session = db.query(LiveBotSession).filter_by(id=self.session_id).first()
            if not session:
                raise ValueError(f"Session {self.session_id} not found")
            
            self.symbol = session.symbol
            self.orders_enabled = session.orders_enabled
            self.is_paper = getattr(session, 'is_paper', True)
            initial_cap = session.initial_capital
            self._account_id = session.account_id

            # Detect exclusive mode from strategy config
            config = session.strategy_config or {}
            self._is_exclusive = config.get("execution_mode") == "exclusive"

            # 1. Strategy Resolution
            strategy_name = session.strategy_name
            self.strategy_name = strategy_name
            self.strategy_config = session.strategy_config
            StrategyClass = strategy_registry.get_strategy_class(strategy_name)
            if not StrategyClass:
                raise ValueError(f"Strategy '{strategy_name}' not found in registry")

            # 1.1 Get user_id and exchange_name from account
            user_id = None
            if session.account_id:
                from ..models.account import ExchangeAccount
                account = db.query(ExchangeAccount).filter_by(id=session.account_id).first()
                if account:
                    user_id = account.user_id
                    self.strategy_config['exchange_name'] = account.exchange_name or DEFAULT_EXCHANGE

            # 2. Context
            self.context = LiveContext(
                self.session_id, self.adapter,
                initial_capital=initial_cap,
                is_paper=self.is_paper,
                user_id=user_id,
                strategy_name=strategy_name,
                account_id=self._account_id
            )

            # Sync pause state to context (prevents PENDING accumulation)
            self.context.orders_paused = not self.orders_enabled

            # Wire exclusive mode gate (blocks buy if another session holds the lock)
            if self._is_exclusive:
                from .live_manager import live_manager
                acct_id = self._account_id
                sid = self.session_id
                self.context._exclusive_gate = lambda: live_manager.try_acquire_exclusive_lock(acct_id, sid)

            # 3. Strategy Instance
            self.strategy_instance = StrategyClass(self.context, self.strategy_config)
            self.strategy_instance.initialize()

            # 3.1 Cache tick execution flag
            self._tick_execution_enabled = (
                hasattr(self.strategy_instance, 'on_tick')
                and getattr(self.strategy_instance, 'tick_execution', 'candle') == 'tick'
            )
            if self._tick_execution_enabled:
                logger.info(f"Tick execution ENABLED for session {self.session_id}")

            # 3. Aggregator
            interval_str = self.strategy_config.get("interval", "1m")
            interval_minutes = self._parse_interval(interval_str)
            self.aggregator = CandleRealAggregator(self.symbol, interval_minutes=interval_minutes)
            logger.info(f"Aggregator interval: {interval_str} ({interval_minutes}min)")
            
            # 4. Sync Initial Balance
            await self.context.async_sync_balance()

            # 4.0 Futures initialization (leverage, margin type, monitor)
            if isinstance(self.adapter, FuturesInterface):
                leverage = config.get("leverage", 1)
                margin_type = config.get("margin_type", Margin.CROSSED)
                try:
                    await self.adapter.set_leverage(self.symbol, leverage)
                    await self.adapter.set_margin_type(self.symbol, margin_type)
                    logger.info(f"Futures init: {self.symbol} leverage={leverage}x, margin={margin_type}")
                except Exception as e:
                    logger.warning(f"Futures init warning: {e}")

                # Start FuturesMonitorService for risk monitoring
                try:
                    from ..services.futures_monitor import FuturesMonitorService
                    self._futures_monitor = FuturesMonitorService(
                        session_id=self.session_id,
                        symbol=self.symbol,
                        adapter=self.adapter,
                        context=self.context,
                        tick_listeners=self.tick_listeners,
                        user_id=user_id,
                        account_id=self._account_id,
                        strategy_name=strategy_name,
                    )
                    await self._futures_monitor.start()
                    logger.info(f"FuturesMonitor started for {self.symbol}")
                except Exception as e:
                    logger.error(f"FuturesMonitor start error: {e}")

            # 4.1 Capture Initial Capital if not set (Phase 3.5 Extension)
            if initial_cap <= 0:
                current_equity = self.context.get_total_equity()
                logger.info(f"Initial Capital not set. Capturing current equity as baseline: {current_equity}")
                self.context.initial_capital = current_equity
                
                # Persist to DB for consistency
                session.initial_capital = current_equity
                db.commit()
            
            # 5. Fetch Historical Data (Preload for Chart)
            # This allows the chart to show past context even if market is closed
            # Historical Data Fetch (with Retry)
            logger.info(f"Fetching historical minute candles for {self.symbol}...")
            history = []
            for attempt in range(3):
                try:
                    # Give it a bit of time if this is a cold start
                    if attempt > 0:
                        await asyncio.sleep(2.0)
                        
                    history = await asyncio.wait_for(
                        self.adapter.get_minute_candles(self.symbol, interval_minutes=1),
                        timeout=5.0
                    )
                    
                    if history:
                        self.history_candles = history
                        logger.info(f"Loaded {len(history)} historical candles (Attempt {attempt+1}).")
                        # Set initial price from last candle (for when market is closed)
                        if history:
                            last_candle = history[-1]
                            initial_price = last_candle.get('close', 0)
                            if initial_price > 0:
                                self.context.price_map[self.symbol] = initial_price
                                self.last_price = initial_price
                                logger.info(f"Initial price set from history: {initial_price}")
                        break
                    else:
                        logger.warning(f"History fetch returned empty (Attempt {attempt+1}). Retrying...")
                        
                except Exception as e:
                    logger.warning(f"History fetch failed (Attempt {attempt+1}): {e}")
            
            if not self.history_candles:
                 logger.error("Failed to load history after 3 attempts.")

            # 5.1 Preload strategy indicators from historical data
            # This allows RSI (and other indicators) to be available immediately
            # after PM2 restart, instead of waiting for rsi_period+1 candles.
            if self.history_candles and hasattr(self.strategy_instance, 'preload_history'):
                try:
                    self.strategy_instance.preload_history(self.history_candles)
                    logger.info(f"Strategy indicators preloaded from {len(self.history_candles)} historical candles.")
                except Exception as e:
                    logger.warning(f"Strategy history preload failed: {e}")

            # 6. Set initial config snapshot (for tick-level exits that may trade before first candle)
            self.context.set_config_snapshot(
                config=self.strategy_config,
                strategy_id=self.strategy_config.get("strategy_id", "unknown"),
                symbol=self.symbol
            )

            logger.info(f"Live Engine Initialized for {self.symbol}")

        finally:
            db.close()

    def get_history(self) -> List[Dict]:
        """Return loaded historical candles, filtering out corrupt entries."""
        return [c for c in self.history_candles
                if c.get("low", 0) > 0 and c.get("close", 0) > 0]

    async def run_loop(self):
        """Main Async Loop"""
        self.is_running = True
        logger.info("Starting Live Loop...")

        try:
            while self.is_running:
                loop_start = asyncio.get_running_loop().time()

                # Pure Event-Driven Mode (WebSocket)
                # We do NOT poll current price via REST API to avoid Rate Limits.
                # Data flows in via process_realtime_tick (Called by Adapter)
                await asyncio.sleep(1)

                # Periodic position sync: compare strategy internal state vs Kiwoom actual holdings
                now = datetime.now()
                if (self._last_position_sync_time is None or
                        (now - self._last_position_sync_time).total_seconds() >= self._position_sync_interval):
                    self._last_position_sync_time = now
                    asyncio.create_task(self._sync_position_with_exchange())
                
        except asyncio.CancelledError:
            logger.info("Live Loop Cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in run_loop: {e}", exc_info=True)
            error_logger.log_critical(
                error_type=ErrorType.SYSTEM_ERROR,
                message=f"Unexpected error in run_loop: {e}",
                session_id=self.session_id,
                symbol=self.symbol,
                exception=e,
                context={"is_running": self.is_running}
            )
        finally:
            self.is_running = False
            logger.info("Live Loop Stopped")

        self.last_accum_volume = -1
        self.last_price = 0
        
    async def _process_tick(self):
        # 1. Fetch Real-time Price
        tick_data = await self.adapter.get_current_price(self.symbol)
        price = tick_data.get('price', 0)
        volume = tick_data.get('volume', 0) # Accumulated Volume
        
        # Kiwoom sometimes returns 0 if market closed or error?
        # If 0, skip update but keep loop running
        if price <= 0:
            return

        # Ghost Tick Prevention:
        # If Price AND Volume are identical to last poll, it's a duplicate snapshot. Skip.
        if price == self.last_price and volume == self.last_accum_volume:
             # Only skip if we have valid initial state (volume != -1)
             if self.last_accum_volume != -1:
                 return

        await self._update_internals(price, volume, datetime.now())

    async def process_realtime_tick(self, tick_data: Dict):
        """
        Handle WebSocket Tick
        """
        price = tick_data.get('price', 0)
        volume = tick_data.get('volume', 0)

        # Reject invalid ticks
        if price <= 0:
            return

        # Deduplication
        if price == self.last_price and volume == self.last_accum_volume:
             if self.last_accum_volume != -1:
                 return

        # Use Server Timestamp if available, else Now
        ts_str = tick_data.get('timestamp')
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
            except:
                ts = datetime.now()
        else:
            ts = datetime.now()
            
        await self._update_internals(price, volume, ts)

    async def _update_internals(self, price: float, volume: int, now: datetime):
        # Normalize timestamp to KST (for consistent chart display across timezones)
        KST = timezone(timedelta(hours=9))
        if now.tzinfo is None:
            # Naive datetime: assume system local time → convert to KST
            now = now.astimezone(KST)
        else:
            # Aware datetime: convert to KST
            now = now.astimezone(KST)

        # Update State
        self.last_price = price
        self.last_accum_volume = volume

        
        # Update Context Price Map (for Strategy)
        self.context.price_map[self.symbol] = price
        
        # 2. Frontend Tick Emission (Real-time View)
        tick_event = {
            "type": "tick",
            "symbol": self.symbol,
            "price": price,
            "volume": volume,
            "time": now.isoformat()
        }
        for listener in self.tick_listeners:
            try:
                result = listener(tick_event)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception as e:
                logger.error(f"Error in tick listener: {e}")

        # 2.1 Strategy Status Emission
        try:
            strategy_status = {
                "type": "strategy_status",
                "data": self.strategy_instance.get_state()
            }
            for listener in self.tick_listeners:
                try:
                    result = listener(strategy_status)
                    if asyncio.iscoroutine(result):
                        asyncio.ensure_future(result)
                except:
                    pass
        except Exception as e:
            logger.error(f"Error emitting strategy status: {e}")
            
        # 2.2 Tick-Level Exit Check (when tick_execution='tick')
        if self._tick_execution_enabled and self.strategy_instance and self.is_running:
            try:
                exited = self.strategy_instance.on_tick(price, now)
                if exited and self.orders_enabled:
                    await self.context.process_queue()
            except Exception as e:
                logger.error(f"Tick exit check error: {e}")

        # 3. Aggregate -> Candle
        # Volume: Ideally we need 'tick volume' (delta).
        # Kiwoom 'get_current_price' usually gives 'accumulated volume' or we assume 1 tick volume if unknown.
        closed_candle, snapshot = self.aggregator.add_tick(price, 1, now) # Vol 1 placeholder
        
        # 4. Strategy Execution (On Candle Close)
        if closed_candle:
            logger.info(f"Candle Closed: {closed_candle['timestamp']}")

            # Skip corrupt candles (e.g., low=0 from WebSocket reconnection gaps)
            if closed_candle.get("low", 0) <= 0 or closed_candle.get("close", 0) <= 0:
                logger.warning(f"Skipping corrupt candle: {closed_candle}")
                return

            # Append to history so reconnecting clients get updated data
            self.history_candles.append(closed_candle)

            # Notify Frontend of confirmed candle
            candle_event = {
                "type": "candle",
                "data": closed_candle
            }
            for listener in self.candle_listeners:
                try:
                    result = listener(candle_event)
                    if asyncio.iscoroutine(result):
                        asyncio.ensure_future(result)
                except Exception as e:
                    logger.error(f"Error in candle listener: {e}")
            
            # Update Context Time
            self.context.current_timestamp = datetime.fromisoformat(closed_candle['timestamp'])
            
            # Run Strategy
            try:
                # Sync Balance before decision
                await self.context.async_sync_balance()
                
                # Check if context is linked (Safety)
                if not hasattr(self.strategy_instance, 'context') or self.strategy_instance.context is None:
                        self.strategy_instance.context = self.context

                # Set config snapshot for parameter versioning (before any trades)
                self.context.set_config_snapshot(
                    config=self.strategy_config,
                    strategy_id=self.strategy_config.get("strategy_id", "unknown"),
                    symbol=self.symbol
                )

                # Call Strategy with Correct Signature (single argument)
                self.strategy_instance.on_data(closed_candle)
                
                # 5. Process Orders
                if self.orders_enabled:
                    await self.context.process_queue()
                else:
                    logger.debug(f"Session {self.session_id}: Orders disabled, skipping order processing")

                # 5.1 Exclusive mode: release lock when cycle completes (position → 0)
                if self._is_exclusive and self.strategy_instance:
                    try:
                        state = self.strategy_instance.get_state()
                        if state.get("total_quantity", 0) == 0:
                            from .live_manager import live_manager
                            live_manager.release_exclusive_lock(self._account_id, self.session_id)
                    except Exception:
                        pass

                # 5.2 AI Symbol Selection: trigger on cycle completion (position >0 → 0)
                if self.strategy_instance and not self._ai_switch_in_progress:
                    try:
                        state = self.strategy_instance.get_state()
                        qty = state.get("total_quantity", 0)
                        if qty > 0:
                            if getattr(self, '_ai_skip_next_exit', False):
                                # Pipeline just completed while position was open.
                                # Don't count this position — wait for it to close first.
                                pass
                            else:
                                self._had_position = True
                        elif qty == 0:
                            if getattr(self, '_ai_skip_next_exit', False):
                                # Carry-over position has closed. Now reset for fresh cycle.
                                self._ai_skip_next_exit = False
                                self._had_position = False
                            elif self._had_position:
                                # Fresh cycle completed (entry → exit after last pipeline)
                                self._had_position = False
                                self._try_ai_symbol_switch(from_cycle=True)
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Strategy Execution Error: {e}")
                import traceback
                traceback.print_exc()
                error_logger.log_strategy_error(
                    message=f"Strategy Execution Error: {e}",
                    session_id=self.session_id,
                    symbol=self.symbol,
                    exception=e,
                    context={"strategy_name": self.strategy_name, "candle": closed_candle}
                )

            # 6. Persistence (Phase 3.5)
            try:
                self._save_candle(closed_candle)
            except Exception as e:
                logger.error(f"Candle Persistence Error: {e}")
                error_logger.log_error(
                    error_type=ErrorType.DB_ERROR,
                    message=f"Candle Persistence Error: {e}",
                    session_id=self.session_id,
                    symbol=self.symbol,
                    exception=e,
                    source_function="_save_candle"
                )

    @staticmethod
    def _parse_interval(interval_str: str) -> int:
        """Parse interval string (e.g. '1m', '5m', '1d') to minutes."""
        mapping = {"1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60, "1d": 1440}
        return mapping.get(interval_str, 1)

    def _save_candle(self, candle: Dict[str, Any]):
        """
        Save 1-minute candle to OHLCV table.
        """
        db = SessionLocal()
        try:
            timestamp = datetime.fromisoformat(candle['timestamp'])
            
            # Check exist (Upsert)
            existing = db.query(OHLCV).filter(
                OHLCV.symbol == self.symbol,
                OHLCV.timestamp == timestamp,
                OHLCV.time_frame == "1m"
            ).first()
            
            if existing:
                existing.open = candle['open']
                existing.high = candle['high']
                existing.low = candle['low']
                existing.close = candle['close']
                existing.volume = int(candle['volume'])
            else:
                new_candle = OHLCV(
                    symbol=self.symbol,
                    timestamp=timestamp,
                    time_frame="1m",
                    open=candle['open'],
                    high=candle['high'],
                    low=candle['low'],
                    close=candle['close'],
                    volume=int(candle['volume'])
                )
                db.add(new_candle)
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    async def liquidate_all(self) -> dict:
        """
        Force Close Position: Market sell all holdings.
        Paper mode: uses strategy internal state (total_quantity).
        Real mode: syncs with exchange API for actual holdings.
        Returns: dict with result info (symbol, qty, mode, market_closed, etc.)
        """
        logger.warning(f"FORCE CLOSE: Liquidating all holdings for session {self.session_id}")

        try:
            if self.is_paper:
                return await self._liquidate_paper()
            else:
                return await self._liquidate_real()
        except Exception as e:
            import traceback
            logger.error(f"FORCE CLOSE ERROR for session {self.session_id}: {e}\n{traceback.format_exc()}")
            raise

    async def _liquidate_paper(self) -> dict:
        """Paper mode force close: use strategy's internal position tracking."""
        if self.strategy_instance and hasattr(self.strategy_instance, 'total_quantity'):
            qty = self.strategy_instance.total_quantity
            if qty > 0:
                price = self.context.get_current_price(self.symbol)
                logger.info(f"FORCE CLOSE (PAPER): Selling {qty} shares of {self.symbol} @ {price:,.0f}")
                self.strategy_instance._liquidate(price)
                await self.context.process_queue()
                self._reset_strategy_state()
                return {"symbol": self.symbol, "qty": qty, "mode": "paper", "action": "sold"}
            else:
                logger.info(f"FORCE CLOSE (PAPER): No position in strategy state for {self.symbol}.")
                return {"symbol": self.symbol, "qty": 0, "mode": "paper", "action": "no_position"}
        else:
            logger.info(f"FORCE CLOSE (PAPER): No strategy instance or position tracking.")
            return {"symbol": self.symbol, "qty": 0, "mode": "paper", "action": "no_position"}

    async def _liquidate_real(self) -> dict:
        """Real mode force close: sync with exchange API and sell actual holdings."""
        from ..adapters.kiwoom_websocket import KiwoomWebSocket
        if not KiwoomWebSocket.is_market_open():
            logger.warning(f"FORCE CLOSE (REAL): Market is closed. Cannot liquidate {self.symbol}.")
            await self.context.async_sync_balance()
            qty = self.context.holdings.get(self.symbol, 0)
            return {"symbol": self.symbol, "qty": qty, "mode": "real", "action": "market_closed"}

        # Sync with exchange and sell actual holdings
        await self.context.async_sync_balance()
        qty = self.context.holdings.get(self.symbol, 0)
        if qty > 0:
            logger.info(f"FORCE CLOSE (REAL): Selling {qty} shares of {self.symbol} at Market Price")
            self.context.sell(self.symbol, qty, price=0)
            await self.context.process_queue()
            self._reset_strategy_state()
            return {"symbol": self.symbol, "qty": qty, "mode": "real", "action": "sold"}
        else:
            logger.info(f"FORCE CLOSE (REAL): No holdings found for {self.symbol}.")
            return {"symbol": self.symbol, "qty": 0, "mode": "real", "action": "no_position"}

    def _reset_strategy_state(self):
        """Reset strategy internal state so the next cycle starts clean."""
        if not self.strategy_instance:
            return
        strat = self.strategy_instance
        if not hasattr(strat, 'current_level'):
            return
        old_level = strat.current_level
        old_qty = getattr(strat, 'total_quantity', 0)
        strat.current_level = 0
        strat.total_quantity = 0
        strat.average_price = 0
        strat.peak_price = 0
        strat.trailing_active = False
        strat.reference_price = None
        strat.entries = []
        if hasattr(strat, 'is_hodl'):
            strat.is_hodl = False
        if hasattr(strat, 'cycle_max_level'):
            strat.cycle_max_level = None
        if hasattr(strat, 'cycle_reference_price'):
            strat.cycle_reference_price = None
        if hasattr(strat, 'cycle_start_time'):
            strat.cycle_start_time = None
        if hasattr(strat, '_resolved_base_qty'):
            strat._resolved_base_qty = None
        if hasattr(strat, '_pending_exit'):
            strat._pending_exit = False
        if hasattr(strat, '_pending_entry'):
            strat._pending_entry = False
        # Increment real cycle ID
        if hasattr(strat, 'real_cycle_id'):
            strat.real_cycle_id += 1
        # Reset capital for fixed betting mode
        if getattr(strat, 'betting_strategy', 'fixed') == 'fixed':
            self.context.reset_cycle_capital()
        logger.info(f"FORCE CLOSE: Strategy state reset. L{old_level}/{old_qty}qty -> L0/0qty. Cycle ID: {getattr(strat, 'real_cycle_id', '?')}")

    def stop(self):
        self.is_running = False
        # Stop FuturesMonitor if running
        if self._futures_monitor:
            asyncio.ensure_future(self._futures_monitor.stop())

    def toggle_mode(self, is_paper: bool):
        self.is_paper = is_paper
        if self.context:
            self.context.is_paper = is_paper
        logger.info(f"Session {self.session_id}: Mode toggled to {'PAPER' if is_paper else 'REAL'}")

    def toggle_tick_execution(self, mode: str):
        """Hot-swap tick execution mode ('tick' or 'candle') without stopping the session."""
        if mode not in ("tick", "candle"):
            raise ValueError(f"Invalid tick_execution mode: {mode}")
        old_mode = "tick" if self._tick_execution_enabled else "candle"
        self._tick_execution_enabled = (mode == "tick")
        if self.strategy_instance and hasattr(self.strategy_instance, 'tick_execution'):
            self.strategy_instance.tick_execution = mode
        logger.info(f"Session {self.session_id}: Tick execution {old_mode} -> {mode}")

    async def _run_ai_before_start(self):
        """Run AI symbol evaluation BEFORE trading starts. Blocks until complete.

        Called from start_session/restore_engine. If AI selects a new symbol,
        switch_session_symbol is called and this engine's symbol is updated
        before run_loop() begins.
        """
        try:
            self._ai_switch_in_progress = True
            db = SessionLocal()
            try:
                session = db.query(LiveBotSession).filter_by(id=self.session_id).first()
                if not session:
                    return
                search_conditions = getattr(session, 'ai_search_conditions', None)
                if not search_conditions:
                    return

                # Determine exchange type
                is_futures = False
                exchange_name = "Kiwoom"
                if session.account_id:
                    from ..models.account import ExchangeAccount
                    account = db.query(ExchangeAccount).filter_by(id=session.account_id).first()
                    if account:
                        exchange_name = account.exchange_name or "Kiwoom"
                        is_futures = "futures" in exchange_name.lower()

                session_info = {
                    "session_id": self.session_id,
                    "current_symbol": self.symbol,
                    "current_symbol_name": (session.strategy_config or {}).get("symbol_name", self.symbol),
                    "search_conditions": search_conditions,
                    "strategy_name": session.strategy_name,
                    "strategy_config": dict(session.strategy_config or {}),
                    "initial_capital": session.initial_capital,
                    "account_id": session.account_id,
                    "is_paper": session.is_paper,
                    "group_id": session.group_id,
                    "ai_optimize_params": getattr(session, 'ai_optimize_params', None),
                    "is_futures": is_futures,
                    "exchange_name": exchange_name,
                }
            finally:
                db.close()

            # Run the pipeline synchronously (await) — trading hasn't started yet
            from .ai_symbol_selection import AISymbolSelectionService
            service = AISymbolSelectionService.get_instance()

            new_symbol = await service.run_pipeline(
                session_id=session_info["session_id"],
                current_symbol=session_info["current_symbol"],
                search_conditions=session_info["search_conditions"],
                strategy_name=session_info["strategy_name"],
                strategy_config=session_info["strategy_config"],
                initial_capital=session_info["initial_capital"],
                account_id=session_info["account_id"],
                is_paper=session_info["is_paper"],
                group_id=session_info.get("group_id"),
                current_symbol_name=session_info.get("current_symbol_name"),
                ai_optimize_params=session_info.get("ai_optimize_params"),
                is_futures=session_info.get("is_futures", False),
                exchange_name=session_info.get("exchange_name", "Kiwoom"),
            )

            last_result = getattr(service, '_last_result', {}) or {}
            optimized_params = last_result.get('optimized_params')
            new_symbol_name = last_result.get('symbol_name')

            if new_symbol and new_symbol != self.symbol:
                logger.info(f"[AISymbol] Pre-start switch: {self.symbol} -> {new_symbol}")
                from .live_manager import live_manager
                await live_manager.switch_session_symbol(
                    session_id=self.session_id,
                    new_symbol=new_symbol,
                    new_symbol_name=new_symbol_name,
                    optimized_params=optimized_params,
                )
            elif optimized_params:
                logger.info(f"[AISymbol] Pre-start param optimization: {optimized_params}")
                from .live_manager import live_manager
                await live_manager.apply_optimized_params(
                    session_id=self.session_id,
                    optimized_params=optimized_params,
                )
            else:
                logger.info(f"[AISymbol] Pre-start: keeping {self.symbol}")

        except Exception as e:
            logger.error(f"[AISymbol] Pre-start evaluation failed: {e}", exc_info=True)
            # On failure, proceed with current symbol
        finally:
            self._ai_switch_in_progress = False

    async def _sync_position_with_exchange(self):
        """
        주기적으로 키움 실제 잔고와 전략 내부 포지션을 비교하여 불일치를 감지·보정.
        Source of Truth = 키움 API (get_balance).
        """
        if not self.strategy_instance or not self.context:
            return

        # 장 시간(09:00~15:30 KST)에만 실행
        now = datetime.now()
        if not (9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30)):
            return

        strategy_qty = getattr(self.strategy_instance, 'total_quantity', 0)

        # 전략이 포지션 없다고 생각하면 검사 불필요
        if strategy_qty <= 0:
            return

        try:
            balance = await self.adapter.get_balance()
            holdings = balance.get("holdings", {})
            actual_qty = holdings.get(self.symbol, {}).get("quantity", 0)

            # live_context._holdings도 최신 상태로 동기화
            self.context._holdings[self.symbol] = actual_qty

            if actual_qty == strategy_qty:
                return  # 일치 → 정상

            # 불일치 감지
            logger.error(
                f"[POSITION_SYNC] {self.symbol} 포지션 불일치: "
                f"strategy={strategy_qty}, kiwoom={actual_qty} → 키움 기준으로 보정"
            )

            # 키움 기준으로 전략 내부 상태 보정
            self.strategy_instance.total_quantity = actual_qty
            if actual_qty == 0:
                self.strategy_instance.current_level = 0
                self.strategy_instance.trailing_active = False
                self.strategy_instance.entries = []
                self.strategy_instance.average_price = 0
                self.strategy_instance.peak_price = 0
                self.strategy_instance._pending_exit = False

            # 텔레그램 알림
            try:
                from .telegram_service import send_telegram_notification
                from ..db.session import SessionLocal
                db = SessionLocal()
                try:
                    await send_telegram_notification(
                        db=db,
                        user_id=self.context._user_id,
                        notification_type="error",
                        account_id=self.context._account_id,
                        error_type="포지션 불일치 감지",
                        message=(
                            f"종목 {self.symbol}: 전략={strategy_qty}주, 키움={actual_qty}주\n"
                            f"키움 기준으로 자동 보정되었습니다."
                        ),
                        symbol=self.symbol,
                        strategy_name=self.strategy_name,
                    )
                finally:
                    db.close()
            except Exception as tg_err:
                logger.debug(f"[POSITION_SYNC] Telegram 알림 실패: {tg_err}")

        except Exception as e:
            logger.warning(f"[POSITION_SYNC] 잔고 조회 실패, 다음 주기에 재시도: {e}")

    def _try_ai_symbol_switch(self, from_cycle=False):
        """Check if AI symbol selection is enabled and trigger the pipeline.

        Args:
            from_cycle: True when called from cycle completion (position >0 → 0).
                        False when called from start/restore/resume triggers.
        """
        db = SessionLocal()
        try:
            session = db.query(LiveBotSession).filter_by(id=self.session_id).first()
            if not session:
                return
            if getattr(session, 'ai_symbol_mode', AiMode.STATIC) != AiMode.AI:
                return
            search_conditions = getattr(session, 'ai_search_conditions', None)
            if not search_conditions:
                return

            # Guard: After symbol switch, wait for cycle completion before re-evaluating
            if getattr(session, 'ai_awaiting_cycle', False):
                if from_cycle:
                    # Cycle completed after switch → clear flag and proceed
                    session.ai_awaiting_cycle = False
                    db.commit()
                    logger.info(f"[AISymbol] Session {self.session_id[:8]}: "
                                f"cycle completed after switch, proceeding with evaluation")
                else:
                    # Start/restore/resume trigger → skip (wait for cycle)
                    logger.info(f"[AISymbol] Session {self.session_id[:8]}: "
                                f"awaiting cycle completion, skipping trigger")
                    return

            # Determine exchange type
            is_futures = False
            exchange_name = "Kiwoom"
            if session.account_id:
                from ..models.account import ExchangeAccount
                account = db.query(ExchangeAccount).filter_by(id=session.account_id).first()
                if account:
                    exchange_name = account.exchange_name or "Kiwoom"
                    ex_name = exchange_name.lower()
                    is_futures = "futures" in ex_name

            # Capture session info before closing DB
            session_info = {
                "session_id": self.session_id,
                "current_symbol": self.symbol,
                "current_symbol_name": (session.strategy_config or {}).get("symbol_name", self.symbol),
                "search_conditions": search_conditions,
                "strategy_name": session.strategy_name,
                "strategy_config": dict(session.strategy_config or {}),
                "initial_capital": session.initial_capital,
                "account_id": session.account_id,
                "is_paper": session.is_paper,
                "group_id": session.group_id,
                "ai_optimize_params": getattr(session, 'ai_optimize_params', None),
                "is_futures": is_futures,
                "exchange_name": exchange_name,
            }
        finally:
            db.close()

        self._ai_switch_in_progress = True

        # Cycle completion always triggers solo pipeline (only this session needs re-eval)
        logger.info(f"[AISymbol] Triggering SOLO pipeline for session {self.session_id[:8]}")
        asyncio.create_task(self._run_solo_pipeline(session_info))

    async def _run_group_pipeline(self, session_info: dict):
        """Register with group pipeline coordinator. Actual execution managed by coordinator."""
        try:
            from .ai_symbol_selection import AISymbolSelectionService
            service = AISymbolSelectionService.get_instance()
            await service.request_group_evaluation(session_info)
        except Exception as e:
            logger.error(f"[AISymbol] Group pipeline error: {e}", exc_info=True)
        finally:
            self._ai_switch_in_progress = False
            self._set_pipeline_completed()

    async def _run_solo_pipeline(self, session_info: dict):
        """Per-session pipeline for ungrouped sessions."""
        try:
            from .ai_symbol_selection import AISymbolSelectionService
            service = AISymbolSelectionService.get_instance()

            new_symbol = await service.run_pipeline(
                session_id=session_info["session_id"],
                current_symbol=session_info["current_symbol"],
                search_conditions=session_info["search_conditions"],
                strategy_name=session_info["strategy_name"],
                strategy_config=session_info["strategy_config"],
                initial_capital=session_info["initial_capital"],
                account_id=session_info["account_id"],
                is_paper=session_info["is_paper"],
                group_id=session_info.get("group_id"),
                current_symbol_name=session_info.get("current_symbol_name"),
                ai_optimize_params=session_info.get("ai_optimize_params"),
                is_futures=session_info.get("is_futures", False),
                exchange_name=session_info.get("exchange_name", "Kiwoom"),
            )

            # Get optimized params from pipeline result (available even when symbol kept)
            last_result = getattr(service, '_last_result', {}) or {}
            optimized_params = last_result.get('optimized_params')
            new_symbol_name = last_result.get('symbol_name')

            if new_symbol and new_symbol != self.symbol:
                logger.info(f"[AISymbol] Switching: {self.symbol} -> {new_symbol}"
                            f"{f' (params: {optimized_params})' if optimized_params else ''}")
                from .live_manager import live_manager
                await live_manager.switch_session_symbol(
                    session_id=self.session_id,
                    new_symbol=new_symbol,
                    new_symbol_name=new_symbol_name,
                    optimized_params=optimized_params,
                )
                done_msg = f"종목 전환 완료: {self.symbol} → {new_symbol}"
                if optimized_params:
                    done_msg += f" (최적 파라미터: {optimized_params})"
                service._update_progress(
                    self.session_id, "done", done_msg,
                    new_symbol=new_symbol, optimized_params=optimized_params,
                )
                service._clear_progress(self.session_id)
            elif optimized_params:
                # Symbol kept but parameters optimized — apply params in-place
                logger.info(f"[AISymbol] Symbol kept ({self.symbol}), applying optimized params: {optimized_params}")
                from .live_manager import live_manager
                await live_manager.apply_optimized_params(
                    session_id=self.session_id,
                    optimized_params=optimized_params,
                )
            else:
                logger.info(f"[AISymbol] No switch needed for session {self.session_id[:8]}")
        except Exception as e:
            logger.error(f"[AISymbol] Pipeline error: {e}", exc_info=True)
        finally:
            self._ai_switch_in_progress = False
            # Always set ai_awaiting_cycle after pipeline completes (keep or switch)
            # This prevents immediate re-trigger from param changes resetting strategy state
            self._set_pipeline_completed()

    def _set_pipeline_completed(self):
        """Reset cycle tracking so trigger requires a fresh entry→exit after pipeline."""
        self._had_position = False
        # If strategy currently has a position, skip its exit to avoid false trigger
        has_position = False
        if self.strategy_instance:
            try:
                state = self.strategy_instance.get_state()
                has_position = state.get("total_quantity", 0) > 0
            except Exception:
                pass
        self._ai_skip_next_exit = has_position
        logger.info(f"[AISymbol] Session {self.session_id[:8]}: "
                    f"pipeline complete, cycle reset (skip_exit={has_position})")

    def toggle_orders(self, enabled: bool):
        self.orders_enabled = enabled
        # Sync pause gate to context
        if self.context:
            self.context.orders_paused = not enabled
        logger.info(f"Session {self.session_id}: Orders {'Enabled' if enabled else 'Disabled'}")

        # When pausing: cancel all PENDING orders to prevent them executing on resume/restart
        if not enabled:
            self._cancel_pending_orders()

    def _cancel_pending_orders(self):
        """Cancel all PENDING orders in DB for this session.

        Called when orders are paused to prevent stale PENDING records
        from executing on resume or PM2 restart.
        """
        from ..models.live_trading import LiveTradeExecution, ExecutionStatus
        db = SessionLocal()
        try:
            pending = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.PENDING,
            ).all()
            if pending:
                for p in pending:
                    p.status = ExecutionStatus.FAILED
                    p.error_reason = "Cancelled: orders paused"
                db.commit()
                logger.info(f"Session {self.session_id}: Cancelled {len(pending)} PENDING orders (pause)")
        except Exception as e:
            logger.error(f"Failed to cancel pending orders: {e}")
            db.rollback()
        finally:
            db.close()
