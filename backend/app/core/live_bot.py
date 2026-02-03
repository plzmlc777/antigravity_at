import logging
import asyncio
from datetime import datetime
from ..models.live_trading import LiveBotSession, LiveTradeExecution, ExecutionStatus
from ..db.session import SessionLocal
from ..strategies.base import BaseStrategy, IContext
from ..core.exchange_interface import ExchangeInterface
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class LiveBot(IContext):
    """
    Robust Real-Time Trading Wrapper around a Strategy.
    Acts as the IContext for the Strategy.
    """
    def __init__(self, session_id: str, adapter: ExchangeInterface, interval_sec: int):
        self.session_id = session_id
        self.adapter = adapter
        self.interval_sec = interval_sec
        self.strategy: Optional[BaseStrategy] = None # Set later
        self.is_running = False
        self.is_paused = False
        
        # Candle Building State
        self.current_candle = None
        self.candle_start_time = None
        self.last_known_price = 0
        
        # Context State for Strategy
        self.cash = 0 # Will be synced from DB/live_session
        self.holdings = {} # symbol -> qty. To be synced.
        self.trades = [] # History for strategy context

    def set_strategy(self, strategy: BaseStrategy):
        self.strategy = strategy
        # Load initial capital from session if needed
        # self.cash = ... from session


        # Start Polling Loop (Safe MVP)
        if self.strategy:
             # Sync basic state if possible
             self.strategy.initialize()
             asyncio.create_task(self._poll_market_data())
        else:
             logger.error(f"[LiveBot {self.session_id}] Cannot start without strategy set!")

    async def _poll_market_data(self):
        logger.info(f"[LiveBot {self.session_id}] Polling Loop Active (Interval: 1s)")
        while self.is_running:
            try:
                if not self.strategy: break
                
                # Fetch Real Price
                price_info = await self.adapter.get_current_price(self.strategy.symbol) 
                
                current_price = price_info.get('price', 0)
                if current_price > 0:
                    self.last_known_price = current_price
                    await self.on_tick(current_price, datetime.now().timestamp())

                
            except Exception as e:
                logger.error(f"[LiveBot {self.session_id}] Polling Error: {e}")
            
            await asyncio.sleep(1) # Frequency 1s

    async def stop(self):
        self.is_running = False
        logger.info(f"[LiveBot {self.session_id}] Stopped")

    async def pause(self):
        self.is_paused = True
        logger.info(f"[LiveBot {self.session_id}] Paused (Data collecting, Trading stopped)")

    async def resume(self):
        self.is_paused = False
        logger.info(f"[LiveBot {self.session_id}] Resumed")

    async def on_tick(self, price: float, timestamp: float):
        """
        Ingest real-time price, build minute candles, and feed Strategy.
        """
        if not self.is_running: return

        # 1. Initialize Candle
        ts_minute = (int(timestamp) // self.interval_sec) * self.interval_sec
        
        if self.candle_start_time is None:
            self.candle_start_time = ts_minute
            self.current_candle = {
                'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0, 
                'timestamp': datetime.fromtimestamp(ts_minute)
            }
        
        # 2. Check Candle Closure
        if ts_minute > self.candle_start_time:
            # Previous Candle Closed -> Process Strategy
            closed_candle = self.current_candle
            # Strategy on_data call
            if self.strategy:
                # Format to what Strategy Expects (Dict)
                 self.strategy.on_data(closed_candle)

            # Start New Candle
            self.candle_start_time = ts_minute
            self.current_candle = {
                'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0, 
                'timestamp': datetime.fromtimestamp(ts_minute)
            }
        else:
            # Update Current Candle
            if self.current_candle:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price
                # Volume logic omitted (tick volume approx)

    # --- IContext Implementation ---
    def get_time(self) -> datetime:
        return datetime.now()

    def get_current_price(self, symbol: str) -> float:
        return self.last_known_price

    def log(self, message: str):
        logger.info(f"[STRATEGY {self.session_id}] {message}")
        # Optional: Save to DB logs if needed

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        """
        Triggered by Strategy.
        Executes Real Buy.
        """
        if self.is_paused:
            self.log("Buy Signal Ignored (PAUSED)")
            return {}
            
        # We need to await execution, but IContext is sync?
        # Check BaseStrategy. If methods are sync, we have a problem.
        # BaseStrategy methods are abstract.
        # If Strategy calls self.context.buy() in a synchronous method (on_data),
        # we must use asyncio.create_task or run_until_complete?
        # Ideally Strategy.on_data is async allowed?
        # Checked BaseStrategy: on_data is NOT async def.
        # BUT we are running inside _poll_market_data which IS async.
        # So we can just schedule the execution task.
        
        asyncio.create_task(self._execute_signal_safely({
            'type': 'BUY', 'symbol': symbol, 'quantity': quantity
        }, self.last_known_price, datetime.now()))
        return {'status': 'submitted'}

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        if self.is_paused:
            self.log("Sell Signal Ignored (PAUSED)")
            return {}

        asyncio.create_task(self._execute_signal_safely({
            'type': 'SELL', 'symbol': symbol, 'quantity': quantity
        }, self.last_known_price, datetime.now()))
        return {'status': 'submitted'}

    async def _execute_signal_safely(self, signal, price, timestamp):
        """
        State Machine: Signal -> PreCheck -> Order -> Verify
        """
        async with self.execution_lock:
            db = SessionLocal()
            try:
                # 1. Log PENDING Execution
                execution = LiveTradeExecution(
                    session_id=self.session_id,
                    signal_type=signal['type'], # BUY/SELL
                    signal_timestamp=timestamp,
                    theoretical_price=price,
                    status=ExecutionStatus.PENDING
                )
                db.add(execution)
                db.commit()
                db.refresh(execution)
                
                # 2. Pre-Flight Check (Balance, etc)
                # ... check balance ...
                
                # 3. Submit Order
                execution.order_submitted_at = datetime.utcnow()
                execution.status = ExecutionStatus.SUBMITTED
                db.commit()
                
                # Call Adapter
                if signal['type'] == 'BUY':
                    result = await self.adapter.place_buy_order(signal['symbol'], price, signal['quantity'])
                else:
                    result = await self.adapter.place_sell_order(signal['symbol'], price, signal['quantity'])
                
                # 4. Handle Result
                if result.get('status') == 'success':
                    # Ideally we verify fill instantly or poll later.
                    # For MVP, assume filled if market order success
                    execution.status = ExecutionStatus.FILLED
                    execution.order_filled_at = datetime.utcnow()
                    execution.executed_price = price # Placeholder, better to get from result
                    execution.filled_quantity = signal['quantity']
                else:
                    execution.status = ExecutionStatus.FAILED
                    execution.error_reason = result.get('message', 'Unknown Error')
                
                db.commit()
                
            except Exception as e:
                logger.error(f"Execution Error: {e}")
                # Update DB to FAILED if possible
            finally:
                db.close()
