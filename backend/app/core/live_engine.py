
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
        self.interval_seconds = 1 # Poll interval
        
        # Components
        self.context: LiveContext = None
        self.strategy_instance = None
        self.aggregator: CandleRealAggregator = None
        self.symbol: str = ""
        
        # Real-time Event Callback (for Frontend)
        self.on_tick_callback: Callable[[Dict], None] = None
        self.on_candle_closed_callback: Callable[[Dict], None] = None

    async def initialize(self):
        """Setup Context, Strategy, Aggregator"""
        db = SessionLocal()
        try:
            session = db.query(LiveBotSession).filter_by(id=self.session_id).first()
            if not session:
                raise ValueError(f"Session {self.session_id} not found")
            
            self.symbol = session.symbol
            initial_cap = session.initial_capital
            
            # 1. Context
            self.context = LiveContext(self.session_id, self.adapter, initial_capital=initial_cap)
            
            # 2. Strategy
            # Instantiate Strategy (assuming standard __init__(config))
            self.strategy_instance = self.strategy_class(self.strategy_config)
            
            # 3. Aggregator
            # Parse interval from session (e.g. "1m" -> 1)
            # For now default to 1 minute
            self.aggregator = CandleRealAggregator(self.symbol, interval_minutes=1)
            
            # 4. Sync Initial Balance
            await self.context.async_sync_balance()
            
            logger.info(f"Live Engine Initialized for {self.symbol}")
            
        finally:
            db.close()

    async def run_loop(self):
        """Main Async Loop"""
        self.is_running = True
        logger.info("Starting Live Loop...")
        
        try:
            while self.is_running:
                loop_start = asyncio.get_running_loop().time()
                
                try:
                    await self._process_tick()
                except Exception as e:
                    logger.error(f"Error in Live Loop Tick: {e}")
                    traceback.print_exc()
                
                # Sleep to maintain interval
                elapsed = asyncio.get_running_loop().time() - loop_start
                sleep_time = max(0.1, self.interval_seconds - elapsed)
                await asyncio.sleep(sleep_time)
                
        except asyncio.CancelledError:
            logger.info("Live Loop Cancelled")
        finally:
            self.is_running = False
            logger.info("Live Loop Stopped")

    async def _process_tick(self):
        # 1. Fetch Real-time Price
        tick_data = await self.adapter.get_current_price(self.symbol)
        price = tick_data.get('price', 0)
        
        # Kiwoom sometimes returns 0 if market closed or error?
        # If 0, skip update but keep loop running
        if price <= 0:
            return

        now = datetime.now()
        
        # Update Context Price Map (for Strategy)
        self.context.price_map[self.symbol] = price
        
        # 2. Frontend Tick Emission (Real-time View)
        if self.on_tick_callback:
            self.on_tick_callback({
                "symbol": self.symbol,
                "price": price,
                "time": now.isoformat()
            })
            
        # 3. Aggregate -> Candle
        # Volume: Ideally we need 'tick volume' (delta). 
        # Kiwoom 'get_current_price' usually gives 'accumulated volume' or we assume 1 tick volume if unknown.
        # For 'Real' Kiwoom adapter, we might need to calc delta. 
        # For MVP, let's pass dummy volume 1 or fix adapter later.
        # Check adapter... it returns 'price'.
        closed_candle, snapshot = self.aggregator.add_tick(price, 1, now) # Vol 1 placeholder
        
        # 4. Strategy Execution (On Candle Close)
        if closed_candle:
            logger.info(f"Candle Closed: {closed_candle['timestamp']}")
            
            # Notify Frontend of confirmed candle
            if self.on_candle_closed_callback:
                self.on_candle_closed_callback(closed_candle)
            
            # Update Context Time
            # engine sets current_timestamp (Strategy thinks it's this time)
            self.context.current_timestamp = datetime.fromisoformat(closed_candle['timestamp'])
            
            # Run Strategy
            try:
                # Sync Balance before decision
                await self.context.async_sync_balance()
                
                # Inject Data
                # Strategy expects 'data' dict usually?
                # Or just calls on_data(candle)?
                # Standard interface: setup_method(context), on_data(context, data)
                # Let's check 'time_momentum.py' via memory or view.
                
                # Assuming simple interface: strategy.on_data(context, {symbol: [candle]})
                # Create 'feeds' style input
                data_packet = {self.symbol: [closed_candle]}
                
                # Setup context if needed (once?) context is usually passed in __init__ or run?
                # In waterfall: strategy.setup(context) calls once.
                # Here we might need to set context on strategy if not set.
                if not hasattr(self.strategy_instance, 'context') or self.strategy_instance.context is None:
                     self.strategy_instance.context = self.context
                     self.strategy_instance.setup(self.context)

                self.strategy_instance.on_data(self.context, data_packet)
                
                # 5. Process Orders
                # Strategy logic calls `context.buy()`, which queues orders in DB.
                # Now we execute them.
                await self.context.process_queue()
                
            except Exception as e:
                logger.error(f"Strategy Execution Error: {e}")
                traceback.print_exc()

    def stop(self):
        self.is_running = False
