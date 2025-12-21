from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseStrategy(ABC):
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the strategy with configuration.
        config: Dictionary containing strategy parameters (e.g., periods, thresholds).
        """
        self.config = config

    @abstractmethod
    def calculate_signals(self, market_data: Dict[str, Any]) -> str:
        """
        Analyze market data and return a signal.
        market_data: Dictionary containing prices, volumes, etc.
        Return: 'buy', 'sell', or 'hold'
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the strategy name."""
        pass
