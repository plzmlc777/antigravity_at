
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models.live_trading import LiveTradeExecution, ExecutionStatus
from ..models.new_orders import StockOrder, OrderSide, OrderType
from ..adapters.kiwoom_real import KiwoomRealAdapter

logger = logging.getLogger(__name__)

class LiveContext:
    """
    Context for Live Trading Strategies.
    Mimics BacktestContext interface but executes against Real Adapter & DB.
    """
    def __init__(self, session_id: str, adapter: KiwoomRealAdapter, initial_capital: float = 0.0):
        self.session_id = session_id
        self.adapter = adapter
        self.initial_capital = initial_capital
        
        # State
        self.cash = initial_capital
        self.holdings = {} # {symbol: quantity} (Synced with Adapter)
        self.trades = [] # Keep local copy for strategy logic
        self.logs = []
        self.equity_curve = []
        
        # Real-time Price Cache (Updated by Engine)
        self.price_map = {} # {symbol: price}
        
        # Initial Balance Sync
        self._sync_balance()

    def get_current_price(self, symbol: str) -> float:
        """
        Returns latest price from cache. 
        Engine MUST update price_map before strategy runs.
        """
        return self.price_map.get(symbol, 0.0)

    def get_time(self) -> datetime:
        """Returns current real server time"""
        return datetime.now()

    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        return self._execute_order(symbol, OrderSide.BUY, quantity, price)

    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market") -> Dict[str, Any]:
        return self._execute_order(symbol, OrderSide.SELL, quantity, price)

    def _execute_order(self, symbol: str, side: OrderSide, quantity: float, price: float) -> Dict[str, Any]:
        """
        Core Execution Pipeline:
        1. Validate (StockOrder)
        2. DB Record (PENDING)
        3. Send to Adapter
        4. DB Update (SUBMITTED/FAILED)
        """
        db: Session = SessionLocal()
        try:
            current_price = self.get_current_price(symbol)
            exec_price = price if price > 0 else current_price
            
            # 1. Create & Validate Order Object
            order = StockOrder(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=exec_price if price > 0 else None,
                order_type=OrderType.LIMIT if price > 0 else OrderType.MARKET
            )
            order.validate()
            
            # 2. Pre-Execution DB Record
            db_exec = LiveTradeExecution(
                session_id=self.session_id,
                symbol=symbol,
                signal_type=side.value,
                signal_timestamp=self.get_time(),
                theoretical_price=current_price,
                requested_quantity=quantity,
                status=ExecutionStatus.PENDING
            )
            db.add(db_exec)
            db.commit() # Save ID
            db.refresh(db_exec)
            
            self.log(f"SIGNAL: {side.value} {quantity} {symbol} @ {exec_price}")
            
            # ... (Async bridge logic placeholder) ...
            
            self.log(f"Queued Order: {side.value} {symbol}")
            
            # Return a "Receipt" (Trade Dict) immediately
            trade_receipt = {
                "type": side.value.lower(),
                "symbol": symbol,
                "price": exec_price,
                "quantity": quantity,
                "time": self.get_time().isoformat(),
                "order_id": db_exec.id, # Internal DB ID
                "status": "queued"
            }
            self.trades.append(trade_receipt)
            return trade_receipt
            
        except Exception as e:
            self.log(f"ORDER ERROR: {e}")
            return {"status": "failed", "reason": str(e)}
        finally:
            db.close()

    def log(self, message: str):
        print(f"[LIVE] {message}")
        self.logs.append(f"[{self.get_time().strftime('%H:%M:%S')}] {message}")

    def _sync_balance(self):
        pass

    async def async_sync_balance(self):
        """Called by Engine to update state"""
        try:
            bal = await self.adapter.get_balance()
            if bal:
                self.cash = bal['cash']['KRW']
                simple_holdings = {}
                for sym, data in bal['holdings'].items():
                    simple_holdings[sym] = data['quantity']
                self.holdings = simple_holdings
        except Exception as e:
            logger.error(f"Balance Sync Error: {e}")

    async def process_queue(self):
        """
        Called by Engine to process PENDING orders in DB/Queue.
        This is where 'Async Adapter' is actually called.
        """
        db: Session = SessionLocal()
        try:
            # Find PENDING executions for this session
            pendings = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.PENDING
            ).all()
            
            for p in pendings:
                # Execute
                try:
                    res = None
                    if p.signal_type == "BUY":
                        res = await self.adapter.place_buy_order(p.symbol, p.theoretical_price, p.requested_quantity)
                    elif p.signal_type == "SELL":
                         res = await self.adapter.place_sell_order(p.symbol, p.theoretical_price, p.requested_quantity)
                    
                    if res:
                        p.status = ExecutionStatus.SUBMITTED
                        p.order_submitted_at = self.get_time()
                        # log result...
                        
                    db.commit()
                except Exception as e:
                    logger.error(f"Queue Process Error: {e}")
        except Exception as e:
            logger.error(f"Queue DB Error: {e}")
        finally:
            db.close()
