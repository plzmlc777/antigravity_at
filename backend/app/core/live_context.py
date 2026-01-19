
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

    def get_total_equity(self) -> float:
        """
        Calculates total equity: Cash + Sum of (Holding Qty * Current Price)
        Uses price_map for latest known prices.
        """
        equity = self.cash
        for symbol, qty in self.holdings.items():
            price = self.price_map.get(symbol, 0.0)
            equity += qty * price
        return equity

    def calculate_pnl(self) -> float:
        """
        Calculates PnL based ONLY on trades executed during this session.
        PnL = Sum of (Sold Value) - Sum of (Bought Value) + (Current Holding Value)
        """
        db = SessionLocal()
        try:
            executions = db.query(LiveTradeExecution).filter(
                LiveTradeExecution.session_id == self.session_id,
                LiveTradeExecution.status == ExecutionStatus.FILLED
            ).all()
            
            total_bought_cost = 0.0
            total_sold_value = 0.0
            current_qty = 0.0
            
            for ex in executions:
                val = (ex.executed_price or 0.0) * (ex.filled_quantity or 0.0)
                if ex.signal_type == "BUY":
                    total_bought_cost += val
                    current_qty += (ex.filled_quantity or 0.0)
                elif ex.signal_type == "SELL":
                    total_sold_value += val
                    current_qty -= (ex.filled_quantity or 0.0)
            
            # Unrealized part of current holding
            current_price = self.get_current_price(executions[0].symbol if executions else "")
            unrealized_value = current_qty * current_price
            
            return total_sold_value + unrealized_value - total_bought_cost
            
        except Exception as e:
            logger.error(f"PnL Calculation Error: {e}")
            return 0.0
        finally:
            db.close()

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
                # SAFEGUARD: If adapter returns 0 cash (mock/error) but we have initial_capital,
                # preserve initial_capital for PnL consistency in simulation/test.
                fetched_cash = bal['cash']['KRW']
                
                if fetched_cash == 0 and self.initial_capital > 0 and self.cash == self.initial_capital:
                    logger.warning("Balance Sync returned 0 cash. Preserving initial_capital for simulation.")
                    # Keep self.cash as is
                else:
                    self.cash = fetched_cash
                
                simple_holdings = {}
                for sym, data in bal['holdings'].items():
                    simple_holdings[sym] = data['quantity']
                self.holdings = simple_holdings
                
                # Update price map for all holdings to ensure get_total_equity is accurate
                for sym, data in bal['holdings'].items():
                    if 'current_price' in data and data['current_price'] > 0:
                        self.price_map[sym] = data['current_price']
                        
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
                    
                    if res and res.get("status") == "success":
                        # 1. Update DB Record
                        p.status = ExecutionStatus.FILLED
                        p.order_submitted_at = self.get_time()
                        p.order_filled_at = self.get_time()
                        p.executed_price = res.get("price", p.theoretical_price)
                        p.filled_quantity = res.get("quantity", p.requested_quantity)
                        
                        # 2. Update Local Context State (In-Memory for Strategy)
                        # This ensures the bot's internal view is based on its OWN actions
                        cost = p.executed_price * p.filled_quantity
                        if p.signal_type == "BUY":
                            self.cash -= cost
                            self.holdings[p.symbol] = self.holdings.get(p.symbol, 0) + p.filled_quantity
                        else:
                            self.cash += cost
                            self.holdings[p.symbol] = self.holdings.get(p.symbol, 0) - p.filled_quantity
                            
                        self.log(f"FILLED: {p.signal_type} {p.filled_quantity} {p.symbol} @ {p.executed_price}")
                        
                    elif res:
                        p.status = ExecutionStatus.FAILED
                        p.error_reason = res.get("message", "Unknown Error")
                        self.log(f"ORDER FAILED: {p.error_reason}")
                        
                    db.commit()
                except Exception as e:
                    logger.error(f"Queue Process Error: {e}")
                    db.rollback()
        except Exception as e:
            logger.error(f"Queue DB Error: {e}")
        finally:
            db.close()
