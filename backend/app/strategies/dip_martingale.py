from typing import Dict, Any, List, Optional
from datetime import datetime
from .base import BaseStrategy, IContext

class DipMartingaleStrategy(BaseStrategy):
    """
    Dip Martingale Strategy
    - Basic Idea: Buy when price dips from a reference point (e.g., daily open or peak).
    - Martingale: If price continues to drop, increase position size at fixed intervals to lower average price.
    - Profit Taking: Use Trailing Stop once a profit target is reached.
    - Risk Management: Max levels, HODL (Max Loss Protection)
    """

    def initialize(self):
        # Configuration parameters
        self.symbol = self.config.get("symbol", "UNKNOWN")
        self.dip_percent = self.config.get("dip_percent", 1.0) # Condition 1: Initial dip to enter (e.g., -1%)
        self.level_gap_percent = self.config.get("level_gap_percent", 2.0) # Condition 2: Gap between levels (e.g., -2%)
        self.max_levels = self.config.get("max_levels", 4) # Max levels (excluding level 0)
        self.lot_size_multiplier = self.config.get("lot_size_multiplier", 2.0) # Martingale multiplier (e.g., 1, 2, 4, 8)
        self.base_quantity = self.config.get("base_quantity", 1) # Starting quantity for Level 1

        self.trailing_start_percent = self.config.get("trailing_start_percent", 0.01) # 1% profit starts trailing
        self.trailing_stop_percent = self.config.get("trailing_stop_percent", 0.003) # 0.3% drop from peak triggers sell
        self.max_loss_percent = self.config.get("max_loss_percent", 0.10) # 10% total loss triggers HODL

        # Betting Strategy: "fixed" = reset to initial_capital each cycle, "compound" = keep accumulated P&L
        self.betting_strategy = self.config.get("betting_strategy", "fixed")

        # Safety margin: reserve this % of capital (not used for trading)
        self.safety_margin_percent = self.config.get("safety_margin_percent", 1.0)  # 1% safety margin

        # Cycle planning variables (calculated at cycle start)
        self.cycle_max_level = None  # Max affordable level for this cycle
        self.cycle_reference_price = None  # Price used for planning

        # State variables
        self.current_level = 0 # 0: None, 1: First Entry, 2: Second...
        self.reference_price = None # Point from which dip is measured (Cycle Start)
        self.peak_price = 0 # Highest price since entry for trailing stop
        self.average_price = 0
        self.total_quantity = 0
        self.trailing_active = False
        self.is_hodl = False
        self.last_trade_time = None
        self.current_trading_date = None
        self.entries = [] # List of entry records
        self.cycle_id = 0  # Unique cycle identifier for tracking

    def on_data(self, data: Dict[str, Any]):
        """Called on every price update"""
        current_time = self.context.get_time()
        current_date = current_time.date()
        current_price = data['close']
        self.last_price = current_price # Store for state
        symbol = self.symbol
        
        # 1. Reset cycle on new day (if no position)
        if self.current_trading_date != current_date:
            self.current_trading_date = current_date
            if self.current_level == 0:
                self.reference_price = None
                self.context.log(f"[DipMartingale] New day {current_date}. Resetting reference price.")
        
        # 2. Set Reference Price (Cycle Start)
        if self.reference_price is None:
            self.reference_price = current_price
            self.context.log(f"[DipMartingale] Cycle started for {symbol}. Ref: {self.reference_price:,.0f}")
            return

        # 3. Position Management (If holding)
        if self.current_level > 0 and self.total_quantity > 0:
            # Calculate return based on INITIAL CAPITAL (not position value)
            # This makes trailing_start_percent meaningful as "% of capital profit"
            initial_capital = getattr(self.context, 'initial_capital', 10000000)
            position_profit = (current_price - self.average_price) * self.total_quantity
            current_return = position_profit / initial_capital if initial_capital > 0 else 0

            # Update peak profit for trailing stop (also capital-based)
            current_peak_profit = (self.peak_price - self.average_price) * self.total_quantity if self.peak_price > 0 else 0
            if position_profit > current_peak_profit:
                self.peak_price = current_price

            # 3a. Check Trailing Stop Activation (based on capital return)
            if not self.trailing_active and current_return >= (self.trailing_start_percent / 100):
                self.trailing_active = True
                self.peak_price = current_price
                self.context.log(f"[DipMartingale] Trailing Stop ACTIVATED. Capital Return: {current_return*100:.2f}%")
            
            # 3b. Check Trailing Stop Liquidation (price-based drop from peak)
            if self.trailing_active:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price if self.peak_price > 0 else 0
                if drop_from_peak >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[DipMartingale] Trailing Stop TRIGGERED! Sell @ {current_price:,.0f} (Capital Return: {current_return*100:.2f}%)")
                    self._liquidate(current_price)
                    return

            # 3c. Check Max Loss Protection (HODL) - based on capital loss
            if not self.is_hodl and current_return <= -(self.max_loss_percent / 100):
                self.is_hodl = True
                self.context.log(f"[DipMartingale] CRITICAL: Capital Loss {current_return*100:.1f}%. HODL Mode Engaged.")
            
            # 3d. Check Martingale Multi-Entry (If candle drops n% from open)
            if self.current_level < self.max_levels and not self.trailing_active:
                next_level = self.current_level + 1
                # Check if current candle dropped n% from its open price
                candle_open = data.get('open', current_price)
                candle_drop = (candle_open - current_price) / candle_open if candle_open > 0 else 0

                if candle_drop >= (self.level_gap_percent / 100):
                    qty = self._calculate_quantity(next_level, current_price)
                    if qty > 0:
                        result = self.context.buy(symbol, qty, metadata={"level": next_level})
                        # Only update position state if buy succeeded
                        if result.get("status") != "failed":
                            self._add_position(current_price, qty, next_level)
                            self.context.log(f"[DipMartingale] L{next_level} Entry @ {current_price:,.0f} (Candle Drop: {candle_drop*100:.2f}%). Avg: {self.average_price:,.0f}")
                        else:
                            self.context.log(f"[DipMartingale] L{next_level} Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

        # 4. Initial Entry (Level 1) - When candle drops n% from its open
        elif self.current_level == 0:
            candle_open = data.get('open', current_price)
            candle_drop = (candle_open - current_price) / candle_open if candle_open > 0 else 0
            if candle_drop >= (self.dip_percent / 100):
                qty = self._calculate_quantity(1, current_price)  # Calculate with cycle planning
                result = self.context.buy(symbol, qty, metadata={"level": 1})
                # Only update position state if buy succeeded
                if result.get("status") != "failed":
                    self._add_position(current_price, qty, 1)
                    self.peak_price = current_price
                    self.context.log(f"[DipMartingale] L1 Initial Entry @ {current_price:,.0f} (Candle Drop: {candle_drop*100:.2f}%)")
                else:
                    self.context.log(f"[DipMartingale] L1 Initial Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

    def _add_position(self, price: float, quantity: int, level: int):
        new_total_qty = self.total_quantity + quantity
        self.average_price = ((self.average_price * self.total_quantity) + (price * quantity)) / new_total_qty
        self.total_quantity = new_total_qty
        self.current_level = level
        self.entries.append({"level": level, "price": price, "quantity": quantity, "time": str(self.context.get_time())})

    def _liquidate(self, price: float):
        self.cycle_id += 1  # Increment cycle ID before closing
        self.context.sell(self.symbol, self.total_quantity, metadata={"level": "CLOSE", "cycle_id": self.cycle_id})

        # Fixed betting mode: Reset cash to initial_capital for next cycle
        # Compound mode: Keep accumulated P&L (cash stays as-is)
        if self.betting_strategy == "fixed":
            self.context.reset_cycle_capital()

        self.current_level = 0
        self.total_quantity = 0
        self.average_price = 0
        self.peak_price = 0
        self.trailing_active = False
        self.is_hodl = False
        self.reference_price = None # Reset cycle
        self.entries = []
        self.cycle_max_level = None  # Reset cycle planning
        self.cycle_reference_price = None

    def _calculate_max_affordable_level(self, price: float) -> int:
        """Calculate the maximum level affordable with current capital.

        Returns the highest level where we can still afford all entries up to that level.
        Considers safety margin to reserve some capital.
        """
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
        """Calculate quantity for the given level.

        NEW LOGIC: On the final affordable level, invest ALL remaining capital
        to maximize position size and lower average price.

        - Levels 1 to (max_level - 1): Standard martingale (base_qty * multiplier^(level-1))
        - Final level (max_level): ALL remaining usable capital
        """
        # Get current price if not provided
        if price is None:
            price = getattr(self, 'last_price', 0)

        if price <= 0:
            return int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))

        # Calculate max affordable level for this cycle (only on L1 entry)
        if self.cycle_max_level is None or level == 1:
            self.cycle_max_level = self._calculate_max_affordable_level(price)
            self.cycle_reference_price = price
            self.context.log(f"[DipMartingale] Cycle Plan: Max affordable level = L{self.cycle_max_level} @ {price:,.0f}")

        # Determine effective max level (capped by config max_levels)
        effective_max_level = min(self.cycle_max_level, self.max_levels)

        # If this is the FINAL level, invest all remaining capital
        if level >= effective_max_level and effective_max_level > 0:
            available_cash = getattr(self.context, 'cash', 0)
            safety_reserve = available_cash * (self.safety_margin_percent / 100)
            usable_capital = available_cash - safety_reserve

            # Calculate how much we've already invested
            already_invested = self.average_price * self.total_quantity if self.total_quantity > 0 else 0

            # All remaining usable capital goes to this level
            remaining_capital = usable_capital  # Cash already excludes current positions
            max_qty = int(remaining_capital / price) if price > 0 else 0

            # Ensure at least the standard quantity
            standard_qty = int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))
            final_qty = max(max_qty, standard_qty)

            self.context.log(f"[DipMartingale] L{level} FINAL LEVEL: Investing remaining capital → {final_qty} shares")
            return final_qty

        # Standard martingale for non-final levels
        return int(self.base_quantity * (self.lot_size_multiplier ** (level - 1)))

    def get_state(self) -> Dict[str, Any]:
        cur_price = getattr(self, 'last_price', 0)
        dip_percent = (self.reference_price - cur_price) / self.reference_price if self.reference_price else 0

        # Calculate profit as % of initial capital (not position value)
        initial_capital = getattr(self.context, 'initial_capital', 10000000)
        position_profit = (cur_price - self.average_price) * self.total_quantity if self.average_price > 0 else 0
        profit_percent = position_profit / initial_capital if initial_capital > 0 else 0

        return {
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
            "target_dip": self.dip_percent / 100.0,
            "target_profit": self.trailing_start_percent / 100.0
        }
