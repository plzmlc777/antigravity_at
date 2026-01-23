import logging
from typing import Dict, Type, Optional
from ..strategies.base import BaseStrategy
from ..strategies.time_momentum import TimeMomentumStrategy
from ..strategies.rsi import RSIStrategy

logger = logging.getLogger(__name__)

class StrategyRegistry:
    """
    Central registry for all trading strategies.
    Map strategy names (strings) to their corresponding class implementations.
    """
    _strategies: Dict[str, Type[BaseStrategy]] = {
        "time_momentum": TimeMomentumStrategy,
        "rsi": RSIStrategy,
    }

    @classmethod
    def get_strategy_class(cls, name: str) -> Optional[Type[BaseStrategy]]:
        if name not in cls._strategies:
            logger.warning(f"Strategy '{name}' not found in registry. Falling back to None.")
            return None
        return cls._strategies[name]

    @classmethod
    def register_strategy(cls, name: str, strategy_class: Type[BaseStrategy]):
        cls._strategies[name] = strategy_class
        logger.info(f"Registered new strategy: {name}")

    @classmethod
    def list_strategies(cls) -> list:
        return list(cls._strategies.keys())

strategy_registry = StrategyRegistry
