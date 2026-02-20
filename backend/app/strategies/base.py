from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import copy


def customize_fields(fields, overrides):
    """Override defaults in parameter fields.

    Args:
        fields: List of field dicts (e.g., BaseStrategy.COMMON_PARAMETER_FIELDS)
        overrides: Dict of {field_name: {attr: value, ...}} to override

    Returns:
        Deep-copied list with overrides applied.
    """
    result = copy.deepcopy(fields)
    for field in result:
        name = field.get("name")
        if name in overrides:
            field.update(overrides[name])
    return result

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
    
    def short(self, symbol: str, quantity: float, price: float = 0, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Open a short position (futures only). Default raises NotImplementedError."""
        raise NotImplementedError("short() requires a futures-enabled context")

    def close_position(self, symbol: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Close entire position (futures only). Default raises NotImplementedError."""
        raise NotImplementedError("close_position() requires a futures-enabled context")

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
    # Common parameters shared by ALL strategies.
    # Subclasses merge their own trigger-specific fields with these.
    # Use customize_fields() to override defaults for a specific strategy.
    COMMON_PARAMETER_FIELDS = [
        # ── Common Parameters ──
        {"name": "interval", "type": "select", "label": "Interval",
         "default": "1m",
         "options": ["1m", "3m", "5m", "10m", "15m", "30m", "60m", "1d"],
         "description": "Chart candle interval",
         "group": "common",
         "show_in_table": False, "defaultOptRange": "1m, 5m, 15m, 60m"},
        {"name": "trailing_start_percent", "type": "number", "label": "Trail Start (%)",
         "default": 0.01, "min": 0.001, "max": 100, "step": 0.01,
         "description": "Profit % of capital to activate trailing stop",
         "group": "common",
         "show_in_table": True, "defaultOptRange": "0.5, 1.0, 5.0, 10.0, 20.0"},
        {"name": "trailing_stop_percent", "type": "number", "label": "Trail Stop (%)",
         "default": 0.003, "min": 0.001, "max": 50, "step": 0.001,
         "description": "Drop % from peak price to trigger sell",
         "group": "common",
         "show_in_table": True, "defaultOptRange": "0.1, 0.3, 0.5, 1.0"},
        {"name": "max_loss_percent", "type": "number", "label": "Stop Loss (%)",
         "default": 0.10, "min": 0.01, "max": 1000, "step": 0.01,
         "description": "Capital loss % that triggers forced sell",
         "group": "common",
         "show_in_table": False, "defaultOptRange": "5.0, 10.0, 20.0"},
        {"name": "betting_strategy", "type": "select", "label": "Betting Mode",
         "default": "fixed", "options": ["fixed", "compound"],
         "description": "fixed=reset capital each cycle, compound=keep accumulated P&L",
         "group": "common",
         "show_in_table": True},
        {"name": "safety_margin_percent", "type": "number", "label": "Safety Margin (%)",
         "default": 1.0, "min": 0, "max": 50, "step": 0.5,
         "description": "Reserve % of capital not used for trading",
         "group": "common",
         "show_in_table": False},
        {"name": "cycle_max_hours", "type": "number", "label": "Cycle Max Hours",
         "default": 0, "min": 0, "max": 720, "step": 1,
         "description": "Force close cycle after N hours (0=unlimited)",
         "group": "common",
         "show_in_table": False, "defaultOptRange": "0, 4, 8, 24, 48"},
        # ── Position Sizing (Martingale) ──
        {"name": "qty_mode", "type": "select", "label": "Qty Mode",
         "default": "fixed",
         "options": ["fixed", "percent"],
         "description": "fixed=share count per level, percent=% of capital per level",
         "group": "martingale",
         "show_in_table": False},
        {"name": "base_quantity", "type": "number", "label": "Base Qty",
         "default": 1, "min": 1, "max": 10000, "step": 1,
         "description": "fixed mode: number of shares, percent mode: % of capital (e.g. 5=5%)",
         "group": "martingale",
         "show_in_table": False, "defaultOptRange": "1, 5, 10"},
        {"name": "use_martingale", "type": "select", "label": "Martingale",
         "default": "on", "options": ["off", "on"],
         "description": "Enable multi-level averaging down (off=single entry only)",
         "group": "martingale",
         "show_in_table": True},
        {"name": "max_buy_count", "type": "number", "label": "Max Buys",
         "default": 4, "min": 1, "max": 100, "step": 1,
         "description": "Maximum buy count (1=single entry, 2+=averaging down)",
         "group": "martingale",
         "show_in_table": True, "defaultOptRange": "1, 3, 4, 5, 10",
         "visible_when": {"use_martingale": {"eq": "on"}}},
        {"name": "lot_size_multiplier", "type": "number", "label": "Pyramid Multiplier",
         "default": 2.0, "min": 1, "max": 10, "step": 0.5,
         "description": "Position size multiplier per level (1->2->4->8...)",
         "group": "martingale",
         "show_in_table": False, "defaultOptRange": "1.5, 2.0, 3.0",
         "visible_when": {"use_martingale": {"eq": "on"}, "max_buy_count": {"gt": 1}}},
        {"name": "last_level_allin", "type": "select", "label": "Last Level All-In",
         "default": "off", "options": ["off", "on"],
         "description": "Use all remaining capital on final level (off=standard martingale qty)",
         "group": "martingale",
         "show_in_table": False,
         "visible_when": {"use_martingale": {"eq": "on"}, "max_buy_count": {"gt": 1}}},
        {"name": "require_lower_price", "type": "select", "label": "Require Lower Price",
         "default": "off", "options": ["off", "on"],
         "description": "L2+ entry only when current price < last entry price (off=buy at any price)",
         "group": "martingale",
         "show_in_table": True,
         "visible_when": {"use_martingale": {"eq": "on"}, "max_buy_count": {"gt": 1}}},
        # ── Additional Buy Mode (Step-down auto-buy) ──
        {"name": "additional_buy_mode", "type": "select", "label": "Add Buy Mode",
         "default": "trigger",
         "options": ["trigger", "step"],
         "description": "trigger=use strategy signal for L2+, step=auto-buy on N% price drop",
         "group": "martingale",
         "show_in_table": True,
         "visible_when": {"use_martingale": {"eq": "on"}, "max_buy_count": {"gt": 1}}},
        {"name": "additional_buy_step", "type": "number", "label": "Step Drop (%)",
         "default": 2.0, "min": 0.1, "max": 50, "step": 0.1,
         "description": "Price drop % from reference to trigger next buy level",
         "group": "martingale",
         "show_in_table": True, "defaultOptRange": "1.0, 2.0, 3.0, 5.0",
         "visible_when": {"use_martingale": {"eq": "on"}, "max_buy_count": {"gt": 1}, "additional_buy_mode": {"eq": "step"}}},
        {"name": "additional_buy_step_ref", "type": "select", "label": "Step Reference",
         "default": "last_entry",
         "options": ["last_entry", "avg_price", "initial_entry"],
         "description": "Reference price for step calculation: last_entry=last buy price, avg_price=average cost, initial_entry=first buy price",
         "group": "martingale",
         "show_in_table": False,
         "visible_when": {"use_martingale": {"eq": "on"}, "max_buy_count": {"gt": 1}, "additional_buy_mode": {"eq": "step"}}},
    ]

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
