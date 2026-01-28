from abc import abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
from .base import BaseStrategy, IContext


class MartingaleBase(BaseStrategy):
    """
    Base class for all Martingale-family strategies.
    Provides common position management, trailing stop, HODL protection,
    and cycle management. Subclasses only need to implement entry trigger logic.
    """

    # Common parameters shared by all martingale variants.
    # Subclasses should merge their own trigger-specific fields with these.
    COMMON_PARAMETER_FIELDS = [
        {"name": "interval", "type": "select", "label": "Interval",
         "default": "1m",
         "options": ["1m", "3m", "5m", "10m", "15m", "30m", "60m", "1d"],
         "description": "Chart candle interval",
         "show_in_table": False, "defaultOptRange": "1m, 5m, 15m, 60m"},
        {"name": "max_levels", "type": "number", "label": "Max Levels",
         "default": 4, "min": 1, "max": 100, "step": 1,
         "description": "Maximum martingale levels (excluding L0)",
         "show_in_table": True, "defaultOptRange": "3, 4, 5, 10"},
        {"name": "lot_size_multiplier", "type": "number", "label": "Pyramid Multiplier",
         "default": 2.0, "min": 1, "max": 10, "step": 0.5,
         "description": "Position size multiplier per level (1->2->4->8...)",
         "show_in_table": False, "defaultOptRange": "1.5, 2.0, 3.0"},
        {"name": "base_quantity", "type": "number", "label": "Base Qty",
         "default": 1, "min": 1, "max": 10000, "step": 1,
         "description": "Starting quantity for Level 1",
         "show_in_table": False, "defaultOptRange": "1, 5, 10"},
        {"name": "trailing_start_percent", "type": "number", "label": "Trail Start (%)",
         "default": 0.01, "min": 0.001, "max": 100, "step": 0.01,
         "description": "Profit % of capital to activate trailing stop",
         "show_in_table": True, "defaultOptRange": "0.5, 1.0, 5.0, 10.0, 20.0"},
        {"name": "trailing_stop_percent", "type": "number", "label": "Trail Stop (%)",
         "default": 0.003, "min": 0.001, "max": 50, "step": 0.001,
         "description": "Drop % from peak price to trigger sell",
         "show_in_table": True, "defaultOptRange": "0.1, 0.3, 0.5, 1.0"},
        {"name": "max_loss_percent", "type": "number", "label": "Max Loss (%)",
         "default": 0.10, "min": 0.01, "max": 1000, "step": 0.01,
         "description": "Capital loss % that triggers HODL mode",
         "show_in_table": False, "defaultOptRange": "5.0, 10.0, 20.0"},
        {"name": "betting_strategy", "type": "select", "label": "Betting Mode",
         "default": "fixed", "options": ["fixed", "compound"],
         "description": "fixed=reset capital each cycle, compound=keep accumulated P&L",
         "show_in_table": True},
        {"name": "safety_margin_percent", "type": "number", "label": "Safety Margin (%)",
         "default": 1.0, "min": 0, "max": 50, "step": 0.5,
         "description": "Reserve % of capital not used for trading",
         "show_in_table": False},
    ]

    # Subclasses must set PARAMETER_SCHEMA with their own trigger fields + COMMON_PARAMETER_FIELDS
    PARAMETER_SCHEMA = None

    def initialize(self):
        # Configuration parameters
        self.symbol = self.config.get("symbol", "UNKNOWN")
        self.max_levels = self.config.get("max_levels", 4)
        self.lot_size_multiplier = self.config.get("lot_size_multiplier",
            self.config.get("pyramid_multiplier", 2.0))  # backward-compat alias
        self.base_quantity = self.config.get("base_quantity", 1)

        self.trailing_start_percent = self.config.get("trailing_start_percent", 0.01)
        self.trailing_stop_percent = self.config.get("trailing_stop_percent", 0.003)
        self.max_loss_percent = self.config.get("max_loss_percent", 0.10)

        # Betting Strategy
        self.betting_strategy = self.config.get("betting_strategy",
            self.config.get("betting_mode", "fixed"))  # backward-compat alias

        # Safety margin: reserve this % of capital (not used for trading)
        self.safety_margin_percent = self.config.get("safety_margin_percent", 1.0)

        # Cycle planning variables (calculated at cycle start)
        self.cycle_max_level = None
        self.cycle_reference_price = None

        # State variables
        self.current_level = 0
        self.reference_price = None
        self.peak_price = 0
        self.average_price = 0
        self.total_quantity = 0
        self.trailing_active = False
        self.is_hodl = False
        self.last_trade_time = None
        self.current_trading_date = None
        self.entries = []
        self.paper_cycle_id = 0
        self.real_cycle_id = 0

        # Hook for subclass-specific initialization
        self._initialize_trigger()

    def _initialize_trigger(self):
        """Override in subclasses to initialize trigger-specific state."""
        pass

    @abstractmethod
    def _check_entry_trigger(self, data: Dict[str, Any]) -> bool:
        """Check if L1 initial entry condition is met. Return True to buy."""
        pass

    @abstractmethod
    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """Check if L2+ additional entry condition is met. Return True to buy."""
        pass

    def _on_candle(self, data: Dict[str, Any]):
        """Called on every candle before any logic. Override for indicator updates (e.g., RSI)."""
        pass

    def on_data(self, data: Dict[str, Any]):
        """Called on every price update"""
        self._on_candle(data)
        current_time = self.context.get_time()
        current_date = current_time.date()
        current_price = data['close']
        self.last_price = current_price
        symbol = self.symbol

        # 1. Reset cycle on new day (if no position)
        if self.current_trading_date != current_date:
            self.current_trading_date = current_date
            if self.current_level == 0:
                self.reference_price = None
                self.context.log(f"[{self._log_prefix}] New day {current_date}. Resetting reference price.")

        # 2. Set Reference Price (Cycle Start)
        if self.reference_price is None:
            self.reference_price = current_price
            self.context.log(f"[{self._log_prefix}] Cycle started for {symbol}. Ref: {self.reference_price:,.0f}")
            return

        # 3. Position Management (If holding)
        if self.current_level > 0 and self.total_quantity > 0:
            initial_capital = getattr(self.context, 'initial_capital', 10000000)
            position_profit = (current_price - self.average_price) * self.total_quantity
            current_return = position_profit / initial_capital if initial_capital > 0 else 0

            # Update peak profit for trailing stop
            current_peak_profit = (self.peak_price - self.average_price) * self.total_quantity if self.peak_price > 0 else 0
            if position_profit > current_peak_profit:
                self.peak_price = current_price

            # 3a. Check Trailing Stop Activation
            if not self.trailing_active and current_return >= (self.trailing_start_percent / 100):
                self.trailing_active = True
                self.peak_price = current_price
                self.context.log(f"[{self._log_prefix}] Trailing Stop ACTIVATED. Capital Return: {current_return*100:.2f}%")

            # 3b. Check Trailing Stop Liquidation
            if self.trailing_active:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price if self.peak_price > 0 else 0
                if drop_from_peak >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[{self._log_prefix}] Trailing Stop TRIGGERED! Sell @ {current_price:,.0f} (Capital Return: {current_return*100:.2f}%)")
                    self._liquidate(current_price)
                    return

            # 3c. Check Max Loss Protection (HODL)
            if not self.is_hodl and current_return <= -(self.max_loss_percent / 100):
                self.is_hodl = True
                self.context.log(f"[{self._log_prefix}] CRITICAL: Capital Loss {current_return*100:.1f}%. HODL Mode Engaged.")

            # 3d. Check Additional Entry (L2+)
            if self.current_level < self.max_levels and not self.trailing_active:
                if self._check_additional_trigger(data):
                    next_level = self.current_level + 1
                    qty = self._calculate_quantity(next_level, current_price)
                    if qty > 0:
                        result = self.context.buy(symbol, qty, metadata={"level": next_level})
                        if result.get("status") != "failed":
                            self._add_position(current_price, qty, next_level)
                            self.context.log(f"[{self._log_prefix}] L{next_level} Entry @ {current_price:,.0f}. Avg: {self.average_price:,.0f}")
                        else:
                            self.context.log(f"[{self._log_prefix}] L{next_level} Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

        # 4. Initial Entry (Level 1)
        elif self.current_level == 0:
            if self._check_entry_trigger(data):
                qty = self._calculate_quantity(1, current_price)
                result = self.context.buy(symbol, qty, metadata={"level": 1})
                if result.get("status") != "failed":
                    self._add_position(current_price, qty, 1)
                    self.peak_price = current_price
                    self.context.log(f"[{self._log_prefix}] L1 Initial Entry @ {current_price:,.0f}")
                else:
                    self.context.log(f"[{self._log_prefix}] L1 Initial Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

    @property
    def _log_prefix(self) -> str:
        """Log prefix for this strategy. Override in subclass if needed."""
        return "Martingale"

    def _add_position(self, price: float, quantity: int, level: int):
        new_total_qty = self.total_quantity + quantity
        self.average_price = ((self.average_price * self.total_quantity) + (price * quantity)) / new_total_qty
        self.total_quantity = new_total_qty
        self.current_level = level
        self.entries.append({"level": level, "price": price, "quantity": quantity, "time": str(self.context.get_time())})

    def _liquidate(self, price: float):
        is_paper = getattr(self.context, 'is_paper', True)
        if is_paper:
            self.paper_cycle_id += 1
            cycle_id = self.paper_cycle_id
        else:
            self.real_cycle_id += 1
            cycle_id = self.real_cycle_id
        self.context.sell(self.symbol, self.total_quantity, metadata={"level": "CLOSE", "cycle_id": cycle_id, "is_paper": is_paper})

        if self.betting_strategy == "fixed":
            self.context.reset_cycle_capital()

        self.current_level = 0
        self.total_quantity = 0
        self.average_price = 0
        self.peak_price = 0
        self.trailing_active = False
        self.is_hodl = False
        self.reference_price = None
        self.entries = []
        self.cycle_max_level = None
        self.cycle_reference_price = None

    def _calculate_max_affordable_level(self, price: float) -> int:
        available_cash = getattr(self.context, 'cash', 0)
        safety_reserve = available_cash * (self.safety_margin_percent / 100)
        usable_capital = available_cash - safety_reserve

        if price <= 0 or usable_capital <= 0:
            return 0

        cumulative_cost = 0
        max_level = 0

        for level in range(1, self.max_levels + 1):
            qty = int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))
            level_cost = qty * price
            cumulative_cost += level_cost

            if cumulative_cost <= usable_capital:
                max_level = level
            else:
                break

        return max_level

    def _calculate_quantity(self, level: int, price: float = None) -> int:
        if price is None:
            price = getattr(self, 'last_price', 0)

        if price <= 0:
            return int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))

        if self.cycle_max_level is None or level == 1:
            self.cycle_max_level = self._calculate_max_affordable_level(price)
            self.cycle_reference_price = price
            self.context.log(f"[{self._log_prefix}] Cycle Plan: Max affordable level = L{self.cycle_max_level} @ {price:,.0f}")

        effective_max_level = min(self.cycle_max_level, self.max_levels)

        if level >= effective_max_level and effective_max_level > 0:
            available_cash = getattr(self.context, 'cash', 0)
            safety_reserve = available_cash * (self.safety_margin_percent / 100)
            usable_capital = available_cash - safety_reserve

            remaining_capital = usable_capital
            max_qty = int(remaining_capital / price) if price > 0 else 0

            standard_qty = int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))
            final_qty = max(max_qty, standard_qty)

            self.context.log(f"[{self._log_prefix}] L{level} FINAL LEVEL: Investing remaining capital → {final_qty} shares")
            return final_qty

        return int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))

    def get_state(self) -> Dict[str, Any]:
        cur_price = getattr(self, 'last_price', 0)
        dip_percent = (self.reference_price - cur_price) / self.reference_price if self.reference_price else 0

        initial_capital = getattr(self.context, 'initial_capital', 10000000)
        position_profit = (cur_price - self.average_price) * self.total_quantity if self.average_price > 0 else 0
        profit_percent = position_profit / initial_capital if initial_capital > 0 else 0

        return {
            "strategy_id": self._strategy_id,
            "current_level": self.current_level,
            "max_levels": self.max_levels,
            "average_price": self.average_price,
            "total_quantity": self.total_quantity,
            "peak_price": self.peak_price,
            "trailing_active": self.trailing_active,
            "is_hodl": self.is_hodl,
            "reference_price": self.reference_price,
            "symbol": self.symbol,
            "current_price": cur_price,
            "dip_percent": dip_percent,
            "profit_percent": profit_percent,
            "target_profit": self.trailing_start_percent / 100.0,
            "entries": self.entries,
            "paper_cycle_id": self.paper_cycle_id,
            "real_cycle_id": self.real_cycle_id,
            "cycle_id": self.paper_cycle_id if getattr(self.context, 'is_paper', True) else self.real_cycle_id,
        }

    @property
    def _strategy_id(self) -> str:
        """Override in subclass to return strategy registry ID."""
        return "martingale_base"
