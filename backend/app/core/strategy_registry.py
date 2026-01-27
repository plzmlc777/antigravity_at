import logging
from typing import Dict, Type, Optional, Any
from ..strategies.base import BaseStrategy
from ..strategies.time_momentum import TimeMomentumStrategy
from ..strategies.rsi import RSIStrategy
from ..strategies.dip_martingale import DipMartingaleStrategy

logger = logging.getLogger(__name__)

class StrategyRegistry:
    """
    Central registry for all trading strategies.
    Map strategy names (strings) to their corresponding class implementations.
    """
    _strategies: Dict[str, Type[BaseStrategy]] = {
        "time_momentum": TimeMomentumStrategy,
        "rsi": RSIStrategy,
        "dip_martingale": DipMartingaleStrategy,
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

    @classmethod
    def get_parameter_schema(cls, name: str) -> Optional[dict]:
        """Get PARAMETER_SCHEMA from a registered strategy class."""
        strategy_class = cls._strategies.get(name)
        if strategy_class:
            return getattr(strategy_class, 'PARAMETER_SCHEMA', None)
        return None

    @classmethod
    def get_all_parameter_schemas(cls) -> Dict[str, dict]:
        """Returns {strategy_id: schema_dict} for all strategies with schemas."""
        schemas = {}
        for name, strategy_class in cls._strategies.items():
            schema = getattr(strategy_class, 'PARAMETER_SCHEMA', None)
            if schema:
                schemas[name] = schema
        return schemas

strategy_registry = StrategyRegistry
