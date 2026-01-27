from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime

class IContext(ABC):
    """
    Interface for the execution context (Live or Backtest).
    Strategies interact with the market through this interface.
    """
    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        pass

    @abstractmethod
    def buy(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        pass

    @abstractmethod
    def sell(self, symbol: str, quantity: int, price: float = 0, order_type: str = "market", metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        pass

    @property
    @abstractmethod
    def holdings(self) -> Dict[str, int]:
        """Returns current holdings {symbol: quantity}"""
        pass
    
    @abstractmethod
    def log(self, message: str):
        pass

    @abstractmethod
    def get_time(self) -> datetime:
        pass

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        pass

class BaseStrategy(ABC):
    """
    Abstract Base Class for all strategies.
    """
    # Subclasses override with their parameter schema dict.
    # Format: {"fields": [{"name", "type", "label", "default", ...}]}
    # This is the Single Source of Truth for parameter metadata.
    PARAMETER_SCHEMA: Optional[Dict[str, Any]] = None

    def __init__(self, context: IContext, config: Dict[str, Any] = None):
        self.context = context
        self.config = config or {}

    @abstractmethod
    def initialize(self):
        """
        Called once at the beginning.
        """
        pass

    @abstractmethod
    def on_data(self, data: Dict[str, Any]):
        """
        Called on every data update (e.g., every minute or tick).
        :param data: Dictionary containing 'symbol', 'open', 'high', 'low', 'close', 'volume', 'timestamp'
        """
        pass

    def get_state(self) -> Dict[str, Any]:
        """
        Return the internal state of the strategy for visualization.
        """
        return {}
