import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict, Type, Optional, Any
from strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

# Modules to skip during auto-discovery (not strategy classes)
_SKIP_MODULES = {'base', 'martingale_base', '__init__'}


def _find_strategy_class(module) -> Optional[Type[BaseStrategy]]:
    """Find the first concrete BaseStrategy subclass in a module."""
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (isinstance(attr, type)
                and issubclass(attr, BaseStrategy)
                and attr is not BaseStrategy
                and attr.__module__ == module.__name__):
            return attr
    return None


class StrategyRegistry:
    """
    Central registry for all trading strategies.
    Supports lazy auto-discovery: new strategy files are loaded on demand
    without requiring a PM2 restart.
    """
    _strategies: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def _try_load(cls, name: str) -> Optional[Type[BaseStrategy]]:
        """Try to dynamically import a strategy module by name (filename = strategy_id)."""
        try:
            mod = importlib.import_module(f"strategies.{name}")
            strategy_class = _find_strategy_class(mod)
            if strategy_class:
                cls._strategies[name] = strategy_class
                logger.info(f"Auto-loaded strategy: {name} -> {strategy_class.__name__}")
                return strategy_class
            else:
                logger.warning(f"Module 'strategies.{name}' has no BaseStrategy subclass")
        except ImportError as e:
            logger.debug(f"Strategy module '{name}' not found: {e}")
        except Exception as e:
            logger.warning(f"Failed to load strategy module '{name}': {e}")
        return None

    @classmethod
    def _discover_all(cls):
        """Scan strategies/ directory and register any new strategy files."""
        import inspect
        strategies_dir = Path(inspect.getfile(BaseStrategy)).parent

        for module_info in pkgutil.iter_modules([str(strategies_dir)]):
            if module_info.name in _SKIP_MODULES or module_info.name.startswith('_'):
                continue
            if module_info.name not in cls._strategies:
                cls._try_load(module_info.name)

    @classmethod
    def get_strategy_class(cls, name: str) -> Optional[Type[BaseStrategy]]:
        """Get strategy class by name. Auto-loads from file if not yet registered."""
        if name in cls._strategies:
            return cls._strategies[name]
        # Lazy load: try importing the module
        strategy_class = cls._try_load(name)
        if not strategy_class:
            logger.warning(f"Strategy '{name}' not found in registry or as module.")
        return strategy_class

    @classmethod
    def register_strategy(cls, name: str, strategy_class: Type[BaseStrategy]):
        cls._strategies[name] = strategy_class
        logger.info(f"Registered new strategy: {name}")

    @classmethod
    def list_strategies(cls) -> list:
        """List all strategies, including newly added files."""
        cls._discover_all()
        return list(cls._strategies.keys())

    @classmethod
    def get_parameter_schema(cls, name: str) -> Optional[dict]:
        """Get PARAMETER_SCHEMA from a registered strategy class."""
        strategy_class = cls._strategies.get(name)
        if not strategy_class:
            strategy_class = cls._try_load(name)
        if strategy_class:
            return getattr(strategy_class, 'PARAMETER_SCHEMA', None)
        return None

    @classmethod
    def reload_strategy(cls, name: str) -> Optional[Type[BaseStrategy]]:
        """Force-reimport a strategy module (for when its file was modified)."""
        module_name = f"strategies.{name}"
        import sys
        if module_name in sys.modules:
            try:
                mod = importlib.reload(sys.modules[module_name])
                strategy_class = _find_strategy_class(mod)
                if strategy_class:
                    cls._strategies[name] = strategy_class
                    logger.info(f"Reloaded strategy: {name} -> {strategy_class.__name__}")
                    return strategy_class
            except Exception as e:
                logger.warning(f"Failed to reload strategy '{name}': {e}")
        return cls._try_load(name)

    @classmethod
    def get_all_parameter_schemas(cls) -> Dict[str, dict]:
        """Returns {strategy_id: schema_dict} for all strategies with schemas."""
        cls._discover_all()
        schemas = {}
        for name, strategy_class in cls._strategies.items():
            schema = getattr(strategy_class, 'PARAMETER_SCHEMA', None)
            if schema:
                schemas[name] = schema
        return schemas


# Eagerly load known strategies at import time (for fast startup)
StrategyRegistry._discover_all()

strategy_registry = StrategyRegistry
