
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List, Any
import uuid
import time
import asyncio

# --- Enums for Type Safety ---
class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LIMIT = "STOP_LIMIT"

class OrderStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class AssetClass(str, Enum):
    STOCK = "STOCK"
    CRYPTO = "CRYPTO"
    FUTURE = "FUTURE"

# --- 1. Base Order Class (Abstract) ---
class BaseOrder(ABC):
    """
    Abstract Base Class for all orders.
    Encapsulates state, validation, and lifecycle management.
    """
    def __init__(
        self, 
        symbol: str, 
        side: OrderSide, 
        quantity: float, 
        price: Optional[float] = None, 
        order_type: OrderType = OrderType.LIMIT
    ):
        self.id = str(uuid.uuid4())
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.order_type = order_type
        
        # State
        self.status = OrderStatus.CREATED
        self.exchange_order_id: Optional[str] = None
        self.created_at = time.time()
        self.updated_at = time.time()
        
        self.fills: List[Dict[str, Any]] = [] # Track partial fills
        self.avg_fill_price: float = 0.0
        self.filled_quantity: float = 0.0
        
        self.message: str = "" # Success/Error message

    @property
    @abstractmethod
    def asset_class(self) -> AssetClass:
        pass

    def validate(self):
        """Common validation logic"""
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive. Got {self.quantity}")
        
        if self.order_type == OrderType.LIMIT and (self.price is None or self.price <= 0):
            raise ValueError("Limit orders must have a positive price.")
            
        self.status = OrderStatus.VALIDATED
        self.updated_at = time.time()

    def add_fill(self, fill_price: float, fill_qty: float, fill_id: str = None):
        """Updates state with execution result"""
        if fill_qty <= 0: return

        # Update Average Price
        total_value = (self.avg_fill_price * self.filled_quantity) + (fill_price * fill_qty)
        self.filled_quantity += fill_qty
        self.avg_fill_price = total_value / self.filled_quantity if self.filled_quantity > 0 else 0
        
        self.fills.append({
            "price": fill_price,
            "qty": fill_qty,
            "id": fill_id,
            "time": time.time()
        })
        
        # Update Status
        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
        else:
            self.status = OrderStatus.PARTIALLY_FILLED
            
        self.updated_at = time.time()
        
    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "status": self.status.value,
            "qty_req": self.quantity,
            "qty_filled": self.filled_quantity,
            "avg_price": self.avg_fill_price,
            "asset": self.asset_class.value
        }

# --- 2. Asset Specific Implementations ---

class StockOrder(BaseOrder):
    """Standard Equity Order (e.g. KOSPI/KOSDAQ)"""
    
    @property
    def asset_class(self) -> AssetClass:
        return AssetClass.STOCK
        
    def __init__(self, symbol: str, side: OrderSide, quantity: float, price: float = None, order_type: OrderType = OrderType.LIMIT, market: str = "KR"):
        super().__init__(symbol, side, quantity, price, order_type)
        self.market = market # KR, US, etc.

class FutureOrder(BaseOrder):
    """Derivatives Order with Leverage"""
    
    @property
    def asset_class(self) -> AssetClass:
        return AssetClass.FUTURE
        
    def __init__(self, symbol: str, side: OrderSide, quantity: float, price: float = None, leverage: int = 1):
        super().__init__(symbol, side, quantity, price)
        self.leverage = leverage

# --- 3. Execution System ---

class OrderExecutor:
    """
    Bridge that takes an Order Object and executes it via an Adapter.
    Decouples 'What to do' (Order) from 'How to do it' (Adapter).
    """
    def __init__(self, exchange_adapter):
        self.adapter = exchange_adapter

    async def execute(self, order: BaseOrder) -> BaseOrder:
        try:
            # 1. Validation
            if order.status == OrderStatus.CREATED:
                order.validate() # Ensure it's valid
                
            order.status = OrderStatus.PENDING
            
            # 2. Execution (In real impl, this calls adapter.place_order)
            # Since current adapter uses primitives, we map fields.
            
            print(f"[Executor] Sending {order.asset_class.value} Order: {order.side.value} {order.symbol} {order.quantity} @ {order.price}")
            
            if order.side == OrderSide.BUY:
                result = await self.adapter.place_buy_order(order.symbol, order.price or 0, order.quantity)
            else:
                result = await self.adapter.place_sell_order(order.symbol, order.price or 0, order.quantity)
                
            # 3. Post-Execution Update
            if result.get('status') == 'success' or result.get('order_no'):
                # In async/live systems, we might not get immediate fill.
                # But for synchronous adapters (mock/backtest), we might get fills immediately.
                
                order.exchange_order_id = str(result.get('order_no', ''))
                
                # If the adapter returns fill info immediately (Mock/Backtest often does)
                # We can update the order status
                # For now, let's assume PENDING unless we parse fill info
                pass 
                
            else:
                order.status = OrderStatus.REJECTED
                order.message = result.get('message', 'Unknown Error')

        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.message = str(e)
            
        return order
