import random
import asyncio
from typing import Dict, Any
from ..core.exchange_interface import ExchangeInterface

class KiwoomMockAdapter(ExchangeInterface):
    """
    Mock Adapter for Kiwoom API.
    Simulates API logic for testing without actual Windows/OCX environment.
    """
    
    def __init__(self):
        self.holdings = {"005930": 10, "000660": 5} # Samsung, Hynix
        self.balance = {"KRW": 10000000}
        
    def get_name(self) -> str:
        return "KIWOOM (MOCK)"

    def get_account_name(self) -> str:
        return "MOCK_ACCOUNT"

    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        # Simulate network delay
        await asyncio.sleep(0.1)
        
        # Mock price generation (Samsung Electronics approx 70k, others random)
        base_price = 70000 if symbol == "005930" else 10000
        fluctuation = random.uniform(-0.02, 0.02) # +/- 2%
        price = round(base_price * (1 + fluctuation), 0)
        
        return {
            "symbol": symbol,
            "price": float(price),
            "name": "Samsung Elec (Mock)" if symbol == "005930" else f"Mock Stock {symbol}"
        }

    async def get_balance(self) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "cash": self.balance,
            "holdings": self.holdings
        }

    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        await asyncio.sleep(0.2)
        
        # Handle Market Order (Price = 0)
        executed_price = price
        if executed_price == 0:
            price_info = await self.get_current_price(symbol)
            executed_price = price_info["price"]

        cost = executed_price * quantity
        if self.balance["KRW"] < cost:
            return {"status": "failed", "message": "Insufficient funds"}
        
        self.balance["KRW"] -= cost
        self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
        return {
            "status": "success",
            "order_id": f"ORD-{random.randint(1000, 9999)}",
            "symbol": symbol,
            "side": "buy",
            "price": executed_price,
            "quantity": quantity
        }

    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        await asyncio.sleep(0.2)
        
        # Handle Market Order (Price = 0)
        executed_price = price
        if executed_price == 0:
            price_info = await self.get_current_price(symbol)
            executed_price = price_info["price"]

        if self.holdings.get(symbol, 0) < quantity:
            return {"status": "failed", "message": "Insufficient holdings"}
            
        revenue = executed_price * quantity
        self.holdings[symbol] -= quantity
        if self.holdings[symbol] == 0:
            del self.holdings[symbol]
        self.balance["KRW"] += revenue
        
        return {
            "status": "success",
            "order_id": f"ORD-{random.randint(1000, 9999)}",
            "symbol": symbol,
            "side": "sell",
            "price": executed_price,
            "quantity": quantity
        }
