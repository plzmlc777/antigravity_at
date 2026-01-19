
import asyncio
import logging
import traceback
from typing import List, Dict, Any, Callable
from datetime import datetime
from ..models.live_trading import LiveBotSession, SessionStatus
from ..core.live_context import LiveContext
from ..core.live_aggregator import CandleRealAggregator
from ..adapters.kiwoom_real import KiwoomRealAdapter
from ..db.session import SessionLocal
from ..models.ohlcv import OHLCV

logger = logging.getLogger(__name__)

class LiveTradingEngine:
    """
    Orchestrates the Live Trading Loop.
    1. Polls Price (Tick).
    2. Updates Aggregator.
    3. Triggers Strategy (Candle Close).
    4. Processes Orders.
    """
    def __init__(self, session_id: str, strategy_class: Any, strategy_config: Dict, adapter: KiwoomRealAdapter):
        self.session_id = session_id
        self.strategy_class = strategy_class
        self.strategy_config = strategy_config
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
            initial_cap = session.initial_capital
            
            # 1. Context
            self.context = LiveContext(self.session_id, self.adapter, initial_capital=initial_cap)
            
            # 2. Strategy
            # Instantiate Strategy (context, config)
            self.strategy_instance = self.strategy_class(self.context, self.strategy_config)
            
            # 3. Aggregator
            # Parse interval from session (e.g. "1m" -> 1)
            # For now default to 1 minute
            self.aggregator = CandleRealAggregator(self.symbol, interval_minutes=1)
            
            # 4. Sync Initial Balance
            await self.context.async_sync_balance()
            
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
                        break
                    else:
                        logger.warning(f"History fetch returned empty (Attempt {attempt+1}). Retrying...")
                        
                except Exception as e:
                    logger.warning(f"History fetch failed (Attempt {attempt+1}): {e}")
            
            if not self.history_candles:
                 logger.error("Failed to load history after 3 attempts.")
                 
            logger.info(f"Live Engine Initialized for {self.symbol}")
            
        finally:
            db.close()

    def get_history(self) -> List[Dict]:
        """Return loaded historical candles"""
        return self.history_candles

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
                
        except asyncio.CancelledError:
            logger.info("Live Loop Cancelled")
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
            "time": now.isoformat()
        }
        for listener in self.tick_listeners:
            try:
                listener(tick_event)
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
                    listener(strategy_status)
                except:
                    pass
        except Exception as e:
            logger.error(f"Error emitting strategy status: {e}")
            
        # 3. Aggregate -> Candle
        # Volume: Ideally we need 'tick volume' (delta). 
        # Kiwoom 'get_current_price' usually gives 'accumulated volume' or we assume 1 tick volume if unknown.
        closed_candle, snapshot = self.aggregator.add_tick(price, 1, now) # Vol 1 placeholder
        
        # 4. Strategy Execution (On Candle Close)
        if closed_candle:
            logger.info(f"Candle Closed: {closed_candle['timestamp']}")
            
            # Notify Frontend of confirmed candle
            candle_event = {
                "type": "candle",
                "data": closed_candle
            }
            for listener in self.candle_listeners:
                try:
                    listener(candle_event)
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
                        
                # Call Strategy with Correct Signature (single argument)
                self.strategy_instance.on_data(closed_candle)
                
                # 5. Process Orders
                if self.orders_enabled:
                    await self.context.process_queue()
                else:
                    queue_size = len(self.context.order_queue)
                    if queue_size > 0:
                        logger.info(f"Session {self.session_id}: Skipping {queue_size} signals (Orders Disabled)")
                        self.context.order_queue.clear()
                
            except Exception as e:
                logger.error(f"Strategy Execution Error: {e}")
                import traceback
                traceback.print_exc()

            # 6. Persistence (Phase 3.5)
            try:
                self._save_candle(closed_candle)
            except Exception as e:
                 logger.error(f"Candle Persistence Error: {e}")

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

    async def liquidate_all(self):
        """
        Emergency Kill Switch: Market Sell everything and disable orders.
        """
        logger.warning(f"EMERGENCY: Liquidating all holdings for session {self.session_id}")
        
        # 1. Sync latest holdings
        await self.context.async_sync_balance()
        
        # 2. Find quantity
        qty = self.context.holdings.get(self.symbol, 0)
        
        if qty > 0:
            logger.info(f"EMERGENCY: Selling {qty} shares of {self.symbol} at Market Price")
            # 3. Market Sell
            self.context.sell(self.symbol, qty, price=0)
            
            # 4. Immediate execution (dont wait for candle close)
            await self.context.process_queue()
        else:
            logger.info(f"EMERGENCY: No holdings found for {self.symbol}. Only disabling orders.")
            
        # 5. Disable further orders
        self.toggle_orders(False)

    def stop(self):
        self.is_running = False

    def toggle_orders(self, enabled: bool):
        self.orders_enabled = enabled
        logger.info(f"Session {self.session_id}: Orders {'Enabled' if enabled else 'Disabled'}")
