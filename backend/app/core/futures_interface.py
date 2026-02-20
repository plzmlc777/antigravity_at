"""
Futures Interface - Extended ABC for futures-specific operations.
Inherits from ExchangeInterface, adds leverage, short, margin, funding rate.
"""

from abc import abstractmethod
from typing import Dict, Any
from .exchange_interface import ExchangeInterface


class FuturesInterface(ExchangeInterface):
    """
    Abstract interface for futures exchanges (Binance USDM, etc.).
    Extends ExchangeInterface with futures-specific operations.

    Spot adapters implement ExchangeInterface only.
    Futures adapters implement FuturesInterface (which includes all spot methods).
    LiveContext checks isinstance(adapter, FuturesInterface) for futures features.
    """

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol (1-125x)."""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Dict[str, Any]:
        """
        Get current position for a symbol.
        Returns: {
            "symbol": str,
            "side": "LONG" | "SHORT" | "BOTH",
            "quantity": float,       # Positive for LONG, negative for SHORT
            "entry_price": float,
            "unrealized_pnl": float,
            "leverage": int,
            "margin_type": str,      # "CROSSED" or "ISOLATED"
            "liquidation_price": float,
        }
        """
        pass

    @abstractmethod
    async def place_short_order(self, symbol: str, price: float, quantity: float) -> Dict[str, Any]:
        """Place a short sell order (open short position)."""
        pass

    @abstractmethod
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close entire position for a symbol (market order with reduceOnly)."""
        pass

    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> float:
        """Get current funding rate for a symbol."""
        pass

    @abstractmethod
    async def set_margin_type(self, symbol: str, margin_type: str) -> Dict[str, Any]:
        """Set margin type: 'CROSSED' or 'ISOLATED'."""
        pass
