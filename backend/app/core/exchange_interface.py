from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ExchangeInterface(ABC):
    """
    Abstract Base Class for all exchange adapters (Kiwoom, Binance, etc.)
    Ensures a unified interface for the Strategy Manager.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the exchange (e.g., 'KIWOOM', 'BINANCE')"""
        pass

    @abstractmethod
    def get_account_name(self) -> str:
        """Return the user-defined alias/name of the active account"""
        pass

    @abstractmethod
    async def get_current_price(self, symbol: str) -> Dict[str, Any]:
        """Get the current market price and name for a given symbol"""
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, Any]:
        """
        Get the current account balance.
        Returns a dictionary with currency/symbol as keys and amounts as values.
        """
        pass

    @abstractmethod
    async def place_buy_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a buy order"""
        pass

    @abstractmethod
    async def place_sell_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a sell order"""
        pass

    @abstractmethod
    async def get_outstanding_orders(self) -> list:
        """Get list of outstanding (unfilled) orders"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str, quantity: int, origin_order_id: str = "") -> Dict[str, Any]:
        """Cancel an order"""
        pass
